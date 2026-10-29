// SPDX-License-Identifier: MIT
package softether

import (
	"context"
	"crypto/tls"
	"net"
	"strconv"
	"sync"

	"github.com/xtls/xray-core/common"
	"github.com/xtls/xray-core/common/buf"
	xnet "github.com/xtls/xray-core/common/net"
	"github.com/xtls/xray-core/common/session"
	"github.com/xtls/xray-core/common/task"
	"github.com/xtls/xray-core/core"
	"github.com/xtls/xray-core/features/routing"
	"github.com/xtls/xray-core/features/stats"
	xtun "github.com/xtls/xray-core/proxy/tun"
	"github.com/xtls/xray-core/transport"
	"github.com/xtls/xray-core/transport/internet"
)

func init() {
	common.Must(common.RegisterConfig((*Config)(nil), func(ctx context.Context, value interface{}) (interface{}, error) {
		c := value.(*Config)
		if c.Port == 0 || c.Port > 65535 || len(c.Secret) < 16 || len(c.Secret) > 128 || net.ParseIP(c.Address) == nil {
			return nil, ErrProtocol
		}
		owned, cancel := context.WithCancel(context.Background())
		if c.Server {
			return &serverFeature{config: c, core: core.MustFromContext(ctx), ctx: owned, cancel: cancel, connections: make(map[net.Conn]struct{})}, nil
		}
		return &outbound{config: c, ctx: owned, cancel: cancel}, nil
	}))
}

type outbound struct {
	config  *Config
	ctx     context.Context
	cancel  context.CancelFunc
	mu      sync.Mutex
	network *Network
}

func (o *outbound) Close() error {
	o.cancel()
	o.mu.Lock()
	defer o.mu.Unlock()
	if o.network != nil {
		return o.network.Close()
	}
	return nil
}
func (o *outbound) connect(ctx context.Context) (*Network, error) {
	o.mu.Lock()
	defer o.mu.Unlock()
	if o.ctx.Err() != nil {
		return nil, net.ErrClosed
	}
	if o.network != nil {
		select {
		case <-o.network.Done():
			_ = o.network.Close()
		default:
			return o.network, nil
		}
	}
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	stop := context.AfterFunc(o.ctx, cancel)
	defer stop()
	c := o.config
	s, err := Dial(ctx, net.JoinHostPort(c.Address, strconv.Itoa(int(c.Port))), c.Secret, c.ServerName, c.CertificatePin,
		func(ctx context.Context, network, address string) (net.Conn, error) {
			dest, err := xnet.ParseDestination(network + ":" + address)
			if err != nil {
				return nil, ErrProtocol
			}
			return internet.DialSystem(ctx, dest, nil)
		})
	if err != nil {
		return nil, err
	}
	n, err := NewNetwork(s, nil, nil)
	if err != nil {
		return nil, err
	}
	if o.ctx.Err() != nil {
		_ = n.Close()
		return nil, net.ErrClosed
	}
	o.network = n
	return n, nil
}
func (o *outbound) Process(ctx context.Context, link *transport.Link, _ internet.Dialer) error {
	obs := session.OutboundsFromContext(ctx)
	if len(obs) == 0 || !obs[len(obs)-1].Target.IsValid() {
		return ErrProtocol
	}
	ob := obs[len(obs)-1]
	ob.Name, ob.CanSpliceCopy = "softether", 3
	n, err := o.connect(ctx)
	if err != nil {
		return err
	}
	network := "tcp"
	if ob.Target.Network == xnet.Network_UDP {
		network = "udp"
	}
	conn, err := n.DialContext(ctx, network, ob.Target.NetAddr())
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
		func() error { return buf.Copy(link.Reader, &buf.SequentialWriter{Writer: conn}) },
		task.OnSuccess(func() error { return buf.Copy(reader, link.Writer) }, task.Close(link.Writer)))
}

type serverFeature struct {
	config      *Config
	core        *core.Instance
	ctx         context.Context
	cancel      context.CancelFunc
	mu          sync.Mutex
	listener    net.Listener
	connections map[net.Conn]struct{}
	wg          sync.WaitGroup
}

func (*serverFeature) Type() interface{} { return (*serverFeature)(nil) }
func (s *serverFeature) Start() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.ctx.Err() != nil || s.listener != nil {
		return ErrProtocol
	}
	c := s.config
	cert, err := tls.X509KeyPair([]byte(c.Certificate), []byte(c.Key))
	if err != nil {
		return ErrProtocol
	}
	manager, ok := s.core.GetFeature(stats.ManagerType()).(stats.Manager)
	if !ok {
		return ErrProtocol
	}
	up, err := manager.GetOrRegisterCounter("inbound>>>authorized>>>traffic>>>uplink")
	if err != nil {
		return err
	}
	down, err := manager.GetOrRegisterCounter("inbound>>>authorized>>>traffic>>>downlink")
	if err != nil {
		return err
	}
	l, err := net.Listen("tcp", net.JoinHostPort(c.Address, strconv.Itoa(int(c.Port))))
	if err != nil {
		return err
	}
	s.listener = l
	s.wg.Add(1)
	go func() {
		defer s.wg.Done()
		for {
			raw, err := l.Accept()
			if err != nil {
				return
			}
			s.mu.Lock()
			if s.ctx.Err() != nil || len(s.connections) >= 4 {
				s.mu.Unlock()
				_ = raw.Close()
				continue
			}
			s.connections[raw] = struct{}{}
			s.wg.Add(1)
			s.mu.Unlock()
			go func() {
				defer s.wg.Done()
				defer func() { _ = raw.Close(); s.mu.Lock(); delete(s.connections, raw); s.mu.Unlock() }()
				session, err := Accept(s.ctx, raw, cert, c.Secret)
				if err != nil {
					return
				}
				ctx, cancel := context.WithCancel(s.ctx)
				defer cancel()
				n, err := NewNetwork(session, &routeHandler{ctx: ctx, dispatcher: s.core.GetFeature(routing.DispatcherType()).(routing.Dispatcher)}, func(uplink bool, size int) {
					if uplink {
						up.Add(int64(size))
					} else {
						down.Add(int64(size))
					}
				})
				if err != nil {
					return
				}
				defer n.Close()
				select {
				case <-n.Done():
				case <-s.ctx.Done():
				}
			}()
		}
	}()
	return nil
}
func (s *serverFeature) Close() error {
	s.cancel()
	s.mu.Lock()
	if s.listener != nil {
		_ = s.listener.Close()
	}
	for conn := range s.connections {
		_ = conn.Close()
	}
	s.mu.Unlock()
	s.wg.Wait()
	return nil
}

type routeHandler struct {
	ctx        context.Context
	dispatcher routing.Dispatcher
}

func (h *routeHandler) HandleConnection(conn net.Conn, dest xnet.Destination) {
	defer conn.Close()
	ctx, cancel := context.WithCancel(h.ctx)
	defer cancel()
	stop := context.AfterFunc(ctx, func() { _ = conn.Close() })
	defer stop()
	ctx = session.ContextWithInbound(ctx, &session.Inbound{Name: "softether", Tag: "authorized", CanSpliceCopy: 3, Source: xnet.DestinationFromAddr(conn.RemoteAddr())})
	ctx = session.ContextWithContent(ctx, &session.Content{})
	writer := buf.NewWriter(conn)
	if dest.Network == xnet.Network_TCP {
		writer = &xtun.TCPWriter{Writer: writer}
	}
	_ = h.dispatcher.DispatchLink(ctx, dest, &transport.Link{Reader: &buf.TimeoutWrapperReader{Reader: buf.NewReader(conn)}, Writer: writer})
}
