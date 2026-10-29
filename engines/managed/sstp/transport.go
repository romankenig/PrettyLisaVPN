// SPDX-License-Identifier: MIT
package sstp

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"errors"
	"io"
	"net"
	"sync"
	"time"

	"github.com/romankenig/PrettyLisaVPN/engines/managed/sstp/internal/mschap"
	"github.com/romankenig/PrettyLisaVPN/engines/managed/sstp/internal/ppp"
	"github.com/romankenig/PrettyLisaVPN/engines/managed/sstp/internal/wire"
)

var ErrProtocol = errors.New("SSTP_CONNECTION_FAILED")
var ClientIP = net.IPv4(172, 30, 252, 2).To4()
var ServerIP = net.IPv4(172, 30, 252, 1).To4()

const handshakeTimeout = 20 * time.Second
const MTU = ppp.DefaultMRU

// Session carries authorized IP packets only. It owns no host TUN or routes.
type Session struct {
	conn                   *tls.Conn
	secret                 string
	server                 bool
	nonce                  []byte
	certificate            []byte
	writeMu                sync.Mutex
	mu                     sync.Mutex
	authed, bound, network bool
	ntResponse             [mschap.NTResponseLen]byte
	ready                  chan struct{}
	readyOnce              sync.Once
	done                   chan struct{}
	closeOnce              sync.Once
	packets                chan []byte
	clientPPP              *ppp.Session
	serverPPP              *ppp.ServerSession
}

// The configured pin replaces trust roots, never hostname, expiry or chain checks.
func verifiedTLS(name, pin string) (*tls.Config, error) {
	c := &tls.Config{ServerName: name, MinVersion: tls.VersionTLS12}
	expected, err := hex.DecodeString(pin)
	if name == "" || err != nil || len(expected) != sha256.Size {
		return nil, ErrProtocol
	}
	c.InsecureSkipVerify = true // Mandatory full chain verification with the pinned root below.
	c.VerifyConnection = func(state tls.ConnectionState) error {
		if len(state.PeerCertificates) == 0 {
			return ErrProtocol
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
			return ErrProtocol
		}
		_, err := state.PeerCertificates[0].Verify(x509.VerifyOptions{DNSName: name, Roots: roots, Intermediates: intermediates})
		return err
	}
	return c, nil
}

func newSession(conn *tls.Conn, secret string, server bool) *Session {
	return &Session{conn: conn, secret: secret, server: server, ready: make(chan struct{}), done: make(chan struct{}), packets: make(chan []byte, 64)}
}

// Dial uses a caller-protected physical socket, then verifies the pinned TLS peer.
func Dial(ctx context.Context, address, secret, name, pin string, dial func(context.Context, string, string) (net.Conn, error)) (*Session, error) {
	if len(secret) < 16 || len(secret) > 128 {
		return nil, ErrProtocol
	}
	configuration, err := verifiedTLS(name, pin)
	if err != nil {
		return nil, err
	}
	ctx, cancel := context.WithTimeout(ctx, handshakeTimeout)
	defer cancel()
	raw, err := dial(ctx, "tcp", address)
	if err != nil {
		return nil, ErrProtocol
	}
	conn := tls.Client(raw, configuration)
	s := newSession(conn, secret, false)
	stop := context.AfterFunc(ctx, func() { _ = s.Close() })
	defer stop()
	_ = conn.SetDeadline(time.Now().Add(handshakeTimeout))
	if conn.HandshakeContext(ctx) != nil || sstpHandshake(conn, name) != nil || sendCallConnectRequest(conn) != nil {
		_ = s.Close()
		return nil, ErrProtocol
	}
	s.certificate = conn.ConnectionState().PeerCertificates[0].Raw
	s.nonce, err = readCallConnectAck(conn)
	if err != nil {
		_ = s.Close()
		return nil, ErrProtocol
	}
	s.clientPPP = ppp.New("vpn", secret, s, clientHandler{s})
	s.clientPPP.Start()
	go s.readLoop()
	return s.waitReady(ctx)
}

// Accept performs TLS, PPP authentication and SSTP crypto binding before exposing IP.
// The listener owner must bound concurrent accepted connections before calling it.
func Accept(ctx context.Context, raw net.Conn, cert tls.Certificate, secret string) (*Session, error) {
	if len(cert.Certificate) == 0 || len(secret) < 16 || len(secret) > 128 {
		_ = raw.Close()
		return nil, ErrProtocol
	}
	ctx, cancel := context.WithTimeout(ctx, handshakeTimeout)
	defer cancel()
	conn := tls.Server(raw, &tls.Config{Certificates: []tls.Certificate{cert}, MinVersion: tls.VersionTLS12})
	s := newSession(conn, secret, true)
	s.certificate = cert.Certificate[0]
	stop := context.AfterFunc(ctx, func() { _ = s.Close() })
	defer stop()
	_ = conn.SetDeadline(time.Now().Add(handshakeTimeout))
	if conn.HandshakeContext(ctx) != nil {
		_ = s.Close()
		return nil, ErrProtocol
	}
	line, err := readHTTPHeader(conn)
	if err != nil || line != "SSTP_DUPLEX_POST "+sstpURI+" HTTP/1.1" {
		_ = s.Close()
		return nil, ErrProtocol
	}
	if _, err = io.WriteString(conn, "HTTP/1.1 200 OK\r\nContent-Length: 18446744073709551615\r\n\r\n"); err != nil {
		_ = s.Close()
		return nil, ErrProtocol
	}
	control, body, err := wire.ReadPacket(conn)
	if err != nil || !control {
		_ = s.Close()
		return nil, ErrProtocol
	}
	msg, err := wire.ParseControl(body)
	if err != nil || msg.Type != wire.MsgCallConnectRequest || len(msg.Attributes) != 1 || msg.Attributes[0].ID != wire.AttrEncapsulatedProtocolID || !bytes.Equal(msg.Attributes[0].Value, []byte{0, wire.ProtocolPPP}) {
		_ = s.Close()
		return nil, ErrProtocol
	}
	s.nonce = make([]byte, wire.NonceLen)
	if _, err = rand.Read(s.nonce); err != nil {
		_ = s.Close()
		return nil, ErrProtocol
	}
	value := make([]byte, 4+wire.NonceLen)
	value[3] = wire.CertHashSHA256
	copy(value[4:], s.nonce)
	if s.control(wire.MsgCallConnectAck, []wire.Attribute{{ID: wire.AttrCryptoBindingReq, Value: value}}) != nil {
		_ = s.Close()
		return nil, ErrProtocol
	}
	s.serverPPP = ppp.NewServer(ppp.ServerConfig{ClientIP: ClientIP, ServerIP: ServerIP, DNS: []net.IP{net.IPv4(1, 1, 1, 1)}, Auth: func(user string) (string, bool) {
		return secret, subtle.ConstantTimeCompare([]byte(user), []byte("vpn")) == 1
	}}, s, serverHandler{s})
	s.serverPPP.Start()
	go s.readLoop()
	return s.waitReady(ctx)
}

func (s *Session) waitReady(ctx context.Context) (*Session, error) {
	select {
	case <-s.ready:
		select {
		case <-s.done:
			return nil, ErrProtocol
		default:
		}
		go s.keepalive()
		return s, nil
	case <-s.done:
		return nil, ErrProtocol
	case <-ctx.Done():
		_ = s.Close()
		return nil, ErrProtocol
	}
}
func (s *Session) Close() error {
	s.closeOnce.Do(func() { close(s.done); _ = s.conn.Close() })
	return nil
}
func (s *Session) Done() <-chan struct{} { return s.done }
func (s *Session) ReadPacket() ([]byte, error) {
	select {
	case <-s.done:
		return nil, io.ErrClosedPipe
	default:
	}
	select {
	case packet := <-s.packets:
		return packet, nil
	case <-s.done:
		return nil, io.ErrClosedPipe
	}
}
func (s *Session) WritePacket(packet []byte) error {
	select {
	case <-s.ready:
	default:
		return ErrProtocol
	}
	if len(packet) > MTU || len(packet) < 20 || packet[0]>>4 != 4 {
		return ErrProtocol
	}
	return s.SendPPP(ppp.EncapsulateIP(packet))
}
func (s *Session) write(packet []byte) error {
	s.writeMu.Lock()
	defer s.writeMu.Unlock()
	select {
	case <-s.done:
		return io.ErrClosedPipe
	default:
	}
	_ = s.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
	_, err := s.conn.Write(packet)
	if err != nil {
		_ = s.Close()
	}
	return err
}
func (s *Session) SendPPP(frame []byte) error {
	packet, err := wire.EncodeData(frame)
	if err != nil {
		return ErrProtocol
	}
	return s.write(packet)
}
func (s *Session) control(kind uint16, attributes []wire.Attribute) error {
	packet, err := wire.EncodeControl(kind, attributes)
	if err != nil {
		return ErrProtocol
	}
	return s.write(packet)
}
func (s *Session) readyLocked() {
	if s.authed && s.bound && s.network {
		s.readyOnce.Do(func() { _ = s.conn.SetReadDeadline(time.Time{}); close(s.ready) })
	}
}
func (s *Session) readLoop() {
	defer func() {
		_ = s.Close()
		if s.clientPPP != nil {
			s.clientPPP.Close()
		}
		if s.serverPPP != nil {
			s.serverPPP.Close()
		}
	}()
	for {
		control, body, err := wire.ReadPacket(s.conn)
		if err != nil {
			return
		}
		if control {
			msg, err := wire.ParseControl(body)
			if err != nil {
				return
			}
			switch msg.Type {
			case wire.MsgCallConnected:
				if !s.server || s.verifyBinding(body, msg) != nil {
					return
				}
			case wire.MsgEchoRequest:
				if s.control(wire.MsgEchoResponse, nil) != nil {
					return
				}
			case wire.MsgEchoResponse:
			case wire.MsgCallDisconnect, wire.MsgCallAbort:
				return
			default:
				return
			}
			continue
		}
		if packet, ok := ppp.IsIP(body); ok {
			select {
			case <-s.ready:
			default:
				return
			}
			// Each private authorization owns a single IPv4 address. Spoofing and
			// premature packets are rejected before reaching the in-memory IP stack.
			if len(packet) < 20 || len(packet) > MTU || packet[0]>>4 != 4 {
				return
			}
			address := packet[16:20]
			if s.server {
				address = packet[12:16]
			}
			if !bytes.Equal(address, ClientIP) {
				return
			}
			select {
			case s.packets <- append([]byte(nil), packet...):
			case <-s.done:
				return
			}
		} else if s.server {
			s.serverPPP.Receive(body)
		} else {
			s.clientPPP.Receive(body)
		}
	}
}
func (s *Session) verifyBinding(body []byte, msg wire.ControlMessage) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if !s.authed || s.bound || len(msg.Attributes) != 1 {
		return ErrProtocol
	}
	cb := msg.Attributes[0]
	if cb.ID != wire.AttrCryptoBinding || len(cb.Value) != CBValueLen || cb.Value[3] != wire.CertHashSHA256 || !bytes.Equal(cb.Value[4:36], s.nonce) {
		return ErrProtocol
	}
	if VerifyCryptoBinding(body, mschap.ClientHLAK(s.secret, s.ntResponse), s.certificate) != nil {
		return ErrProtocol
	}
	s.bound = true
	s.readyLocked()
	return nil
}
func (s *Session) keepalive() {
	timer := time.NewTicker(20 * time.Second)
	defer timer.Stop()
	for {
		select {
		case <-timer.C:
			if s.control(wire.MsgEchoRequest, nil) != nil {
				return
			}
		case <-s.done:
			return
		}
	}
}

type clientHandler struct{ *Session }

func (h clientHandler) Authenticated(response [mschap.NTResponseLen]byte) {
	packet, err := buildCallConnected(h.nonce, h.certificate, mschap.ClientHLAK(h.secret, response))
	if err != nil || h.write(packet) != nil {
		_ = h.Close()
		return
	}
	h.mu.Lock()
	h.authed = true
	h.bound = true
	h.readyLocked()
	h.mu.Unlock()
}
func (h clientHandler) NetworkUp(config ppp.IPConfig) {
	if !config.LocalIP.Equal(ClientIP) || !config.PeerIP.Equal(ServerIP) {
		_ = h.Close()
		return
	}
	h.mu.Lock()
	h.network = true
	h.readyLocked()
	h.mu.Unlock()
}
func (h clientHandler) Closed(error) { _ = h.Close() }

type serverHandler struct{ *Session }

func (h serverHandler) Authenticated(_, _ string, response [mschap.NTResponseLen]byte) {
	h.mu.Lock()
	h.ntResponse = response
	h.authed = true
	h.mu.Unlock()
}
func (h serverHandler) NetworkUp(uint16) {
	h.mu.Lock()
	h.network = true
	h.readyLocked()
	h.mu.Unlock()
}
func (h serverHandler) NetworkDown() { _ = h.Close() }
func (h serverHandler) Closed(error) { _ = h.Close() }
