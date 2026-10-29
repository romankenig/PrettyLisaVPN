// SPDX-License-Identifier: MIT
package hysteria1

import (
	"context"
	"crypto/tls"
	"net"
	"strconv"
	"sync"

	"github.com/xtls/xray-core/common"
	"github.com/xtls/xray-core/common/buf"
	xnet "github.com/xtls/xray-core/common/net"
	"github.com/xtls/xray-core/common/net/cnc"
	"github.com/xtls/xray-core/common/session"
	"github.com/xtls/xray-core/common/task"
	"github.com/xtls/xray-core/core"
	"github.com/xtls/xray-core/features/routing"
	"github.com/xtls/xray-core/features/stats"
	"github.com/xtls/xray-core/transport"
	"github.com/xtls/xray-core/transport/internet"
)

func init() {
	common.Must(common.RegisterConfig((*Config)(nil), func(ctx context.Context, value interface{}) (interface{}, error) {
		c := value.(*Config)
		if c.Port == 0 || c.Port > 65535 || len(c.Secret) < 16 || len(c.Secret) > 128 {
			return nil, errProtocol
		}
		if c.Server {
			return &serverFeature{config: c, core: core.MustFromContext(ctx)}, nil
		}
		client, err := NewClient(net.JoinHostPort(c.Address, strconv.Itoa(int(c.Port))), c.Secret, c.ServerName, c.CertificatePin,
			func(ctx context.Context) (net.PacketConn, error) {
				return internet.ListenSystemPacket(ctx, &net.UDPAddr{IP: net.IPv4zero}, nil)
			})
		if err != nil {
			return nil, err
		}
		return &outbound{Client: client}, nil
	}))
}

type outbound struct{ *Client }

func (o *outbound) Process(ctx context.Context, link *transport.Link, _ internet.Dialer) error {
	obs := session.OutboundsFromContext(ctx)
	if len(obs) == 0 {
		return errProtocol
	}
	ob := obs[len(obs)-1]
	target := ob.Target
	if !target.IsValid() {
		return errProtocol
	}
	ob.Name = "hysteria1"
	ob.CanSpliceCopy = 3
	network := "tcp"
	if target.Network == xnet.Network_UDP {
		network = "udp"
	}
	conn, err := o.Dial(ctx, network, target.NetAddr())
	if err != nil {
		return err
	}
	defer conn.Close()
	stop := context.AfterFunc(ctx, func() { _ = conn.Close() })
	defer stop()
	reader := buf.NewReader(conn)
	if network == "udp" {
		reader = buf.NewPacketReader(conn)
	}
	return task.Run(ctx,
		func() error {
			err := buf.Copy(link.Reader, &buf.SequentialWriter{Writer: conn})
			if network == "tcp" {
				_ = conn.(*streamConn).Stream.Close()
			}
			return err
		},
		task.OnSuccess(func() error { return buf.Copy(reader, link.Writer) }, task.Close(link.Writer)))
}

type serverFeature struct {
	config *Config
	core   *core.Instance
	mu     sync.Mutex
	server *Server
}

func (*serverFeature) Type() interface{} { return (*serverFeature)(nil) }
func (s *serverFeature) Start() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.server != nil {
		return errProtocol
	}
	c := s.config
	cert, err := tls.X509KeyPair([]byte(c.Certificate), []byte(c.Key))
	if err != nil {
		return errProtocol
	}
	manager, ok := s.core.GetFeature(stats.ManagerType()).(stats.Manager)
	if !ok {
		return errProtocol
	}
	up, err := manager.GetOrRegisterCounter("inbound>>>authorized>>>traffic>>>uplink")
	if err != nil {
		return err
	}
	down, err := manager.GetOrRegisterCounter("inbound>>>authorized>>>traffic>>>downlink")
	if err != nil {
		return err
	}
	packet, err := net.ListenPacket("udp", net.JoinHostPort(c.Address, strconv.Itoa(int(c.Port))))
	if err != nil {
		return err
	}
	server, err := NewServer(packet, cert, c.Secret, func(ctx context.Context, network, address string) (net.Conn, error) {
		dest, err := xnet.ParseDestination(network + ":" + address)
		if err != nil {
			return nil, errProtocol
		}
		if network == "tcp" {
			dispatcher := s.core.GetFeature(routing.DispatcherType()).(routing.Dispatcher)
			link, err := dispatcher.Dispatch(ctx, dest)
			if err != nil {
				return nil, err
			}
			return &halfConn{Conn: cnc.NewConnection(cnc.ConnectionInputMulti(link.Writer), cnc.ConnectionOutputMulti(link.Reader)), writer: link.Writer}, nil
		}
		return core.Dial(ctx, s.core, dest)
	}, func(uplink bool, n int) {
		if uplink {
			up.Add(int64(n))
		} else {
			down.Add(int64(n))
		}
	})
	if err != nil {
		_ = packet.Close()
		return err
	}
	s.server = server
	return nil
}

type halfConn struct {
	net.Conn
	writer buf.Writer
}

func (c *halfConn) CloseWrite() error { return common.Close(c.writer) }
func (s *serverFeature) Close() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.server != nil {
		return s.server.Close()
	}
	return nil
}
