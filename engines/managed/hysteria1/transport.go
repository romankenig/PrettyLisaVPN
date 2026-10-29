// SPDX-License-Identifier: MIT
package hysteria1

import (
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"io"
	"net"
	"os"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	quic "github.com/apernet/quic-go"
)

const handshakeTimeout = 10 * time.Second

func quicConfig() *quic.Config {
	return &quic.Config{EnableDatagrams: true, HandshakeIdleTimeout: handshakeTimeout,
		MaxIdleTimeout: 90 * time.Second, KeepAlivePeriod: 20 * time.Second,
		MaxIncomingStreams: 128, MaxIncomingUniStreams: -1,
		InitialStreamReceiveWindow: 512 * 1024, MaxStreamReceiveWindow: 4 * 1024 * 1024,
		InitialConnectionReceiveWindow: 1024 * 1024, MaxConnectionReceiveWindow: 8 * 1024 * 1024}
}

// A pin replaces the system root store, never hostname, expiry or chain checks.
// The server sends its CA along with the leaf. No caller can disable validation.
func clientTLS(name, pin string) (*tls.Config, error) {
	c := &tls.Config{ServerName: name, MinVersion: tls.VersionTLS13, NextProtos: []string{"hysteria"}}
	if pin == "" {
		return c, nil
	}
	expected, err := hex.DecodeString(pin)
	if err != nil || len(expected) != sha256.Size {
		return nil, errProtocol
	}
	c.InsecureSkipVerify = true // Replaced by mandatory full verification below.
	c.VerifyConnection = func(state tls.ConnectionState) error {
		if len(state.PeerCertificates) < 1 {
			return errProtocol
		}
		roots, intermediates := x509.NewCertPool(), x509.NewCertPool()
		found := false
		for _, cert := range state.PeerCertificates {
			sum := sha256.Sum256(cert.Raw)
			if subtle.ConstantTimeCompare(sum[:], expected) == 1 {
				roots.AddCert(cert)
				found = true
			} else {
				intermediates.AddCert(cert)
			}
		}
		if !found {
			return errProtocol
		}
		_, err := state.PeerCertificates[0].Verify(x509.VerifyOptions{DNSName: name, Roots: roots, Intermediates: intermediates})
		return err
	}
	return c, nil
}

type streamConn struct {
	*quic.Stream
	conn *quic.Conn
	once sync.Once
}

func (s *streamConn) LocalAddr() net.Addr  { return s.conn.LocalAddr() }
func (s *streamConn) RemoteAddr() net.Addr { return s.conn.RemoteAddr() }
func (s *streamConn) Close() error {
	s.once.Do(func() { s.CancelRead(0); _ = s.Stream.Close() })
	return nil
}
func closeStream(s *quic.Stream) { s.CancelRead(0); s.CancelWrite(0); _ = s.Close() }

type peer struct {
	conn     *quic.Conn
	mu       sync.Mutex
	sessions map[uint32]chan datagram
	packetID atomic.Uint32
}

func newPeer(conn *quic.Conn) *peer {
	return &peer{conn: conn, sessions: make(map[uint32]chan datagram)}
}
func (p *peer) receive() {
	for {
		raw, err := p.conn.ReceiveDatagram(p.conn.Context())
		if err != nil {
			return
		}
		d, err := decodeDatagram(raw)
		if err != nil {
			continue
		}
		p.mu.Lock()
		ch := p.sessions[d.session]
		p.mu.Unlock()
		if ch != nil {
			select {
			case ch <- d:
			default:
			}
		}
	}
}
func (p *peer) register(id uint32) (chan datagram, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	if len(p.sessions) >= 64 || p.sessions[id] != nil {
		return nil, errProtocol
	}
	ch := make(chan datagram, 64)
	p.sessions[id] = ch
	return ch, nil
}
func (p *peer) remove(id uint32) { p.mu.Lock(); delete(p.sessions, id); p.mu.Unlock() }
func (p *peer) send(id uint32, host string, port uint16, data []byte) error {
	if len(data) > 65507 {
		return errProtocol
	}
	fragmentSize := min(maxDatagram, 1100-14-len(host))
	if fragmentSize < 1 {
		return errProtocol
	}
	count := (len(data) + fragmentSize - 1) / fragmentSize
	if count == 0 {
		count = 1
	}
	message := uint16(p.packetID.Add(1))
	if message == 0 {
		message = uint16(p.packetID.Add(1))
	}
	for i := 0; i < count; i++ {
		start, end := i*fragmentSize, min((i+1)*fragmentSize, len(data))
		raw, err := (datagram{session: id, host: host, port: port, id: message, index: uint8(i), count: uint8(count), data: data[start:end]}).encode()
		if err != nil {
			return err
		}
		if err = p.conn.SendDatagram(raw); err != nil {
			return err
		}
	}
	return nil
}

// Client owns every connection and protected packet socket. Reconnect replaces
// a dead QUIC peer, without allowing a closed instance to reopen a socket.
type Client struct {
	ctx             context.Context
	cancel          context.CancelFunc
	mu              sync.Mutex
	address, secret string
	tls             *tls.Config
	listen          func(context.Context) (net.PacketConn, error)
	peer            *peer
	packet          net.PacketConn
}

func NewClient(address, secret, name, pin string, listen func(context.Context) (net.PacketConn, error)) (*Client, error) {
	tc, err := clientTLS(name, pin)
	if err != nil {
		return nil, err
	}
	ctx, cancel := context.WithCancel(context.Background())
	return &Client{ctx: ctx, cancel: cancel, address: address, secret: secret, tls: tc, listen: listen}, nil
}
func (c *Client) Close() error {
	c.cancel()
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.peer != nil {
		_ = c.peer.conn.CloseWithError(0, "")
	}
	if c.packet != nil {
		_ = c.packet.Close()
	}
	return nil
}
func (c *Client) connect(ctx context.Context) (*peer, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.ctx.Err() != nil {
		return nil, net.ErrClosed
	}
	if c.peer != nil && c.peer.conn.Context().Err() == nil {
		return c.peer, nil
	}
	if c.packet != nil {
		_ = c.packet.Close()
		c.packet = nil
	}
	ctx, cancel := context.WithTimeout(ctx, handshakeTimeout)
	defer cancel()
	stop := context.AfterFunc(c.ctx, cancel)
	defer stop()
	addr, err := net.ResolveUDPAddr("udp", c.address)
	if err != nil {
		return nil, errProtocol
	}
	packet, err := c.listen(ctx)
	if err != nil {
		return nil, err
	}
	conn, err := quic.Dial(ctx, packet, addr, c.tls, quicConfig())
	if err != nil {
		_ = packet.Close()
		return nil, err
	}
	fail := func() (*peer, error) { _ = conn.CloseWithError(1, ""); _ = packet.Close(); return nil, errProtocol }
	s, err := conn.OpenStreamSync(ctx)
	if err != nil {
		return fail()
	}
	_ = s.SetDeadline(time.Now().Add(handshakeTimeout))
	if hello(s, c.secret) != nil || readHelloResponse(s) != nil {
		return fail()
	}
	_ = s.SetDeadline(time.Time{})
	c.peer, c.packet = newPeer(conn), packet
	go c.peer.receive()
	return c.peer, nil
}
func (c *Client) Dial(ctx context.Context, network, address string) (net.Conn, error) {
	if network != "tcp" && network != "udp" {
		return nil, errProtocol
	}
	p, err := c.connect(ctx)
	if err != nil {
		return nil, err
	}
	ctx, cancel := context.WithTimeout(ctx, handshakeTimeout)
	defer cancel()
	s, err := p.conn.OpenStreamSync(ctx)
	if err != nil {
		return nil, err
	}
	_ = s.SetDeadline(time.Now().Add(handshakeTimeout))
	if request(s, network == "udp", address) != nil {
		closeStream(s)
		return nil, errProtocol
	}
	id, err := readResponse(s)
	if err != nil {
		closeStream(s)
		return nil, err
	}
	_ = s.SetDeadline(time.Time{})
	base := &streamConn{Stream: s, conn: p.conn}
	if network == "tcp" {
		return base, nil
	}
	host, raw, err := net.SplitHostPort(address)
	if err != nil {
		closeStream(s)
		return nil, errProtocol
	}
	port, err := strconv.ParseUint(raw, 10, 16)
	if err != nil || port == 0 {
		closeStream(s)
		return nil, errProtocol
	}
	ch, err := p.register(id)
	if err != nil {
		closeStream(s)
		return nil, err
	}
	u := &udpConn{streamConn: base, peer: p, id: id, host: host, port: uint16(port), ch: ch, done: make(chan struct{}), changed: make(chan struct{})}
	go func() { _, _ = io.Copy(io.Discard, s); _ = u.Close() }()
	return u, nil
}

type udpConn struct {
	*streamConn
	peer          *peer
	id            uint32
	host          string
	port          uint16
	ch            chan datagram
	done, changed chan struct{}
	once          sync.Once
	mu            sync.Mutex
	readMu        sync.Mutex
	rd, wd        time.Time
	fragments     assembly
}

func (u *udpConn) Close() error {
	u.once.Do(func() { close(u.done); u.peer.remove(u.id); closeStream(u.Stream) })
	return nil
}
func (u *udpConn) Read(b []byte) (int, error) {
	u.readMu.Lock()
	defer u.readMu.Unlock()
	for {
		u.mu.Lock()
		deadline, changed := u.rd, u.changed
		u.mu.Unlock()
		var timeout <-chan time.Time
		var timer *time.Timer
		if !deadline.IsZero() {
			timer = time.NewTimer(time.Until(deadline))
			timeout = timer.C
		}
		select {
		case <-u.done:
			if timer != nil {
				timer.Stop()
			}
			return 0, net.ErrClosed
		case <-u.peer.conn.Context().Done():
			if timer != nil {
				timer.Stop()
			}
			return 0, net.ErrClosed
		case <-timeout:
			return 0, os.ErrDeadlineExceeded
		case <-changed:
			if timer != nil {
				timer.Stop()
			}
			continue
		case d := <-u.ch:
			if timer != nil {
				timer.Stop()
			}
			if d.host != u.host || d.port != u.port {
				continue
			}
			data, ok := u.fragments.accept(d)
			if !ok {
				continue
			}
			if len(data) > len(b) {
				return 0, io.ErrShortBuffer
			}
			return copy(b, data), nil
		}
	}
}
func (u *udpConn) Write(b []byte) (int, error) {
	select {
	case <-u.done:
		return 0, net.ErrClosed
	default:
	}
	u.mu.Lock()
	expired := !u.wd.IsZero() && time.Now().After(u.wd)
	u.mu.Unlock()
	if expired {
		return 0, os.ErrDeadlineExceeded
	}
	if err := u.peer.send(u.id, u.host, u.port, b); err != nil {
		return 0, err
	}
	return len(b), nil
}
func (u *udpConn) SetReadDeadline(t time.Time) error {
	u.mu.Lock()
	u.rd = t
	close(u.changed)
	u.changed = make(chan struct{})
	u.mu.Unlock()
	return nil
}
func (u *udpConn) SetWriteDeadline(t time.Time) error {
	u.mu.Lock()
	u.wd = t
	u.mu.Unlock()
	return nil
}
func (u *udpConn) SetDeadline(t time.Time) error {
	_ = u.SetReadDeadline(t)
	return u.SetWriteDeadline(t)
}

var _ net.Conn = (*udpConn)(nil)
