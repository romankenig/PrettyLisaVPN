// SPDX-License-Identifier: MIT
package sstp

import (
	"context"
	"net"
	"net/netip"
	"strconv"
	"sync"

	xnet "github.com/xtls/xray-core/common/net"
	xtun "github.com/xtls/xray-core/proxy/tun"
)

// Network connects an authenticated SSTP session to the existing in-memory IP
// stack. It never creates a second host interface or changes routes or DNS.
type Network struct {
	session *Session
	stack   xtun.Stack
	cancel  context.CancelFunc
	once    sync.Once
}

type packetDevice struct {
	session *Session
	traffic func(bool, int)
}

func (*packetDevice) Start() error          { return nil }
func (*packetDevice) Name() (string, error) { return "sstp-memory", nil }
func (*packetDevice) Index() (int, error)   { return 0, nil }
func (d *packetDevice) Close() error        { return d.session.Close() }
func (d *packetDevice) ReadPacket([]byte) ([]byte, error) {
	p, err := d.session.ReadPacket()
	if err == nil && d.traffic != nil {
		d.traffic(true, len(p))
	}
	return p, err
}
func (d *packetDevice) WritePacket(header, payload []byte) error {
	p := make([]byte, len(header)+len(payload))
	copy(p, header)
	copy(p[len(header):], payload)
	err := d.session.WritePacket(p)
	if err == nil && d.traffic != nil {
		d.traffic(false, len(p))
	}
	return err
}

func NewNetwork(s *Session, handler xtun.ConnectionHandler, traffic func(bool, int)) (*Network, error) {
	ctx, cancel := context.WithCancel(context.Background())
	address := netip.AddrFrom4([4]byte{172, 30, 252, 2})
	if s.server {
		address = netip.AddrFrom4([4]byte{172, 30, 252, 1})
	}
	stack, err := xtun.NewStack(ctx, xtun.StackOptions{Tun: &packetDevice{session: s, traffic: traffic}, MTU: MTU, Addresses: []netip.Addr{address}, Remote: true}, handler)
	if err != nil {
		cancel()
		_ = s.Close()
		return nil, err
	}
	n := &Network{session: s, stack: stack, cancel: cancel}
	if err = stack.Start(); err != nil {
		_ = n.Close()
		return nil, err
	}
	go func() { <-s.Done(); _ = n.Close() }()
	return n, nil
}
func (n *Network) Close() error {
	n.once.Do(func() { n.cancel(); _ = n.session.Close(); _ = n.stack.Close() })
	return nil
}
func (n *Network) Done() <-chan struct{} { return n.session.Done() }

func (n *Network) dialIP(ctx context.Context, network string, address netip.AddrPort) (net.Conn, error) {
	if !address.Addr().Is4() || address.Port() == 0 {
		return nil, ErrProtocol
	}
	if network == "tcp" {
		return n.stack.DialTCP(ctx, address)
	}
	if network != "udp" {
		return nil, ErrProtocol
	}
	conn, err := n.stack.DialUDP()
	if err != nil {
		return nil, err
	}
	return &xnet.PacketConnWrapper{PacketConn: conn, Dest: net.UDPAddrFromAddrPort(address)}, nil
}

func (n *Network) DialContext(ctx context.Context, network, address string) (net.Conn, error) {
	if endpoint, err := netip.ParseAddrPort(address); err == nil {
		return n.dialIP(ctx, network, endpoint)
	}
	host, portText, err := net.SplitHostPort(address)
	if err != nil {
		return nil, ErrProtocol
	}
	port, err := strconv.ParseUint(portText, 10, 16)
	if err != nil || port == 0 {
		return nil, ErrProtocol
	}
	// Go's resolver receives only a tunnel-backed dialer, never the system path.
	resolver := net.Resolver{PreferGo: true, Dial: func(ctx context.Context, network, _ string) (net.Conn, error) {
		return n.dialIP(ctx, network, netip.AddrPortFrom(netip.AddrFrom4([4]byte{1, 1, 1, 1}), 53))
	}}
	addresses, err := resolver.LookupNetIP(ctx, "ip4", host)
	if err != nil || len(addresses) == 0 {
		return nil, ErrProtocol
	}
	return n.dialIP(ctx, network, netip.AddrPortFrom(addresses[0].Unmap(), uint16(port)))
}
