// SPDX-License-Identifier: MIT
package softether

import (
	"bufio"
	"context"
	"crypto/rand"
	"crypto/subtle"
	"crypto/tls"
	"encoding/binary"
	"errors"
	"io"
	"net"
	"sync"
	"time"

	"github.com/romankenig/PrettyLisaVPN/engines/managed/internal/pinnedtls"
)

var ErrProtocol = errors.New("SOFTETHER_CONNECTION_FAILED")

const MTU = 1400
const handshakeTimeout = 20 * time.Second
const sessionTimeoutMillis = 30000

var ClientIP = net.IPv4(172, 30, 252, 2).To4()
var ServerIP = net.IPv4(172, 30, 252, 1).To4()

// Session is one authenticated Ethernet segment with fixed managed addresses.
// It forwards only IPv4 for this lease, never bridges other sessions or host NICs.
type Session struct {
	conn      *tls.Conn
	br        *bufio.Reader
	server    bool
	mac       [6]byte
	peerMu    sync.Mutex
	peerMAC   [6]byte
	peerReady chan struct{}
	peerOnce  sync.Once
	writeMu   sync.Mutex
	done      chan struct{}
	once      sync.Once
	packets   chan []byte
}

// Each physical read renews the idle timeout, including keepalive-only traffic.
type idleReader struct{ conn *tls.Conn }

func (r idleReader) Read(p []byte) (int, error) {
	_ = r.conn.SetReadDeadline(time.Now().Add(45 * time.Second))
	return r.conn.Read(p)
}

func newSession(conn *tls.Conn, server bool) *Session {
	s := &Session{conn: conn, server: server, peerReady: make(chan struct{}), done: make(chan struct{}), packets: make(chan []byte, 64)}
	_, _ = rand.Read(s.mac[:])
	s.mac[0] = (s.mac[0] | 2) & 0xfe
	return s
}

func Dial(ctx context.Context, address, secret, name, pin string, dial func(context.Context, string, string) (net.Conn, error)) (*Session, error) {
	if len(secret) < 16 || len(secret) > 128 {
		return nil, ErrProtocol
	}
	cfg, err := pinnedtls.Config(name, pin)
	if err != nil {
		return nil, ErrProtocol
	}
	ctx, cancel := context.WithTimeout(ctx, handshakeTimeout)
	defer cancel()
	raw, err := dial(ctx, "tcp", address)
	if err != nil {
		return nil, ErrProtocol
	}
	s := newSession(tls.Client(raw, cfg), false)
	stop := context.AfterFunc(ctx, func() { _ = s.Close() })
	defer stop()
	_ = s.conn.SetDeadline(time.Now().Add(handshakeTimeout))
	limited := &io.LimitedReader{R: s.conn, N: 256 * 1024}
	s.br = bufio.NewReader(limited)
	if s.conn.HandshakeContext(ctx) != nil || writeSignature(s.conn, name) != nil || s.login(secret) != nil {
		_ = s.Close()
		return nil, ErrProtocol
	}
	s.start(limited)
	if s.sendARP(1, [6]byte{255, 255, 255, 255, 255, 255}) != nil {
		_ = s.Close()
		return nil, ErrProtocol
	}
	select {
	case <-s.peerReady:
		if ctx.Err() == nil {
			return s, nil
		}
	case <-s.done:
	case <-ctx.Done():
	}
	_ = s.Close()
	return nil, ErrProtocol
}

// The listener bounds concurrency before Accept. No data reader starts until
// the current random challenge is answered with the lease's credential.
func Accept(ctx context.Context, raw net.Conn, cert tls.Certificate, secret string) (*Session, error) {
	if len(cert.Certificate) == 0 || len(secret) < 16 || len(secret) > 128 {
		_ = raw.Close()
		return nil, ErrProtocol
	}
	ctx, cancel := context.WithTimeout(ctx, handshakeTimeout)
	defer cancel()
	s := newSession(tls.Server(raw, &tls.Config{Certificates: []tls.Certificate{cert}, MinVersion: tls.VersionTLS12}), true)
	stop := context.AfterFunc(ctx, func() { _ = s.Close() })
	defer stop()
	_ = s.conn.SetDeadline(time.Now().Add(handshakeTimeout))
	limited := &io.LimitedReader{R: s.conn, N: 256 * 1024}
	s.br = bufio.NewReader(limited)
	if s.conn.HandshakeContext(ctx) != nil || readSignature(s.br, s.conn) != nil || s.authorize(secret) != nil || ctx.Err() != nil {
		_ = s.Close()
		return nil, ErrProtocol
	}
	s.start(limited)
	return s, nil
}

func (s *Session) login(secret string) error {
	hello, err := recvPackHTTP(s.br, false)
	if err != nil || hello.GetStr("hello") == "" || len(hello.GetData("random")) != sha0Size {
		return ErrProtocol
	}
	var challenge, unique [sha0Size]byte
	copy(challenge[:], hello.GetData("random"))
	_, _ = rand.Read(unique[:])
	digest := securePassword(hashPassword("vpn", secret), challenge)
	req := NewPack()
	for key, value := range map[string]string{"method": "login", "hubname": "DEFAULT", "username": "vpn", "client_str": "PrettyLisaVPN", "hello": "PrettyLisaVPN"} {
		req.Add(key, TypeStr, StrValue(value))
	}
	for key, value := range map[string]uint32{"authtype": 1, "client_ver": 400, "version": 400, "client_build": 9787, "build": 9787, "client_id": 0, "protocol": 0, "max_connection": 1, "use_encrypt": 1, "use_compress": 0, "half_connection": 0, "qos": 0, "require_bridge_routing_mode": 0, "require_monitor_mode": 0} {
		req.Add(key, TypeInt, IntValue(value))
	}
	req.Add("secure_password", TypeData, DataValue(digest[:]))
	req.Add("unique_id", TypeData, DataValue(unique[:]))
	if sendPackHTTP(s.conn, req, false, s.conn.ConnectionState().ServerName) != nil {
		return ErrProtocol
	}
	welcome, err := recvPackHTTP(s.br, false)
	if err != nil || welcome.GetInt("error") != 0 || welcome.GetStr("session_name") == "" || welcome.GetInt("use_encrypt") != 1 || welcome.GetInt("use_compress") != 0 || welcome.GetInt("half_connection") != 0 || welcome.GetInt("max_connection") != 1 {
		return ErrProtocol
	}
	return nil
}

func (s *Session) authorize(secret string) error {
	var challenge, key [sha0Size]byte
	_, _ = rand.Read(challenge[:])
	_, _ = rand.Read(key[:])
	hello := NewPack()
	hello.Add("hello", TypeStr, StrValue("PrettyLisaVPN"))
	hello.Add("version", TypeInt, IntValue(400))
	hello.Add("build", TypeInt, IntValue(9787))
	hello.Add("random", TypeData, DataValue(challenge[:]))
	if sendPackHTTP(s.conn, hello, true, "") != nil {
		return ErrProtocol
	}
	req, err := recvPackHTTP(s.br, true)
	if err != nil {
		return ErrProtocol
	}
	want := securePassword(hashPassword("vpn", secret), challenge)
	if req.GetStr("method") != "login" || req.GetStr("hubname") != "DEFAULT" || req.GetStr("username") != "vpn" || req.GetInt("authtype") != 1 || subtle.ConstantTimeCompare(want[:], req.GetData("secure_password")) != 1 || req.GetInt("protocol") != 0 || req.GetInt("use_encrypt") != 1 || req.GetInt("use_compress") != 0 || req.GetInt("half_connection") != 0 || req.GetInt("require_bridge_routing_mode") != 0 || req.GetInt("require_monitor_mode") != 0 {
		return ErrProtocol
	}
	welcome := NewPack()
	welcome.Add("session_name", TypeStr, StrValue("SID-PrettyLisaVPN"))
	welcome.Add("connection_name", TypeStr, StrValue("CID-PrettyLisaVPN"))
	for k, v := range map[string]uint32{"max_connection": 1, "use_encrypt": 1, "use_compress": 0, "half_connection": 0, "qos": 0, "timeout": sessionTimeoutMillis, "vlan_id": 0, "session_key_32": binary.BigEndian.Uint32(key[:4])} {
		welcome.Add(k, TypeInt, IntValue(v))
	}
	welcome.Add("session_key", TypeData, DataValue(key[:]))
	addPolicy(welcome, defaultPolicy(1))
	return sendPackHTTP(s.conn, welcome, true, "")
}

func (s *Session) start(limited *io.LimitedReader) {
	// Keep buffered bytes, replace only the source after bounded control parsing.
	limited.R = idleReader{s.conn}
	limited.N = 1<<63 - 1
	_ = s.conn.SetDeadline(time.Time{})
	go s.readLoop()
	go func() {
		tick := time.NewTicker(10 * time.Second)
		defer tick.Stop()
		for {
			select {
			case <-s.done:
				return
			case <-tick.C:
				s.writeMu.Lock()
				_ = s.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
				err := writeKeepAlive(s.conn)
				s.writeMu.Unlock()
				if err != nil {
					_ = s.Close()
					return
				}
			}
		}
	}()
}

func (s *Session) Close() error          { s.once.Do(func() { close(s.done); _ = s.conn.Close() }); return nil }
func (s *Session) Done() <-chan struct{} { return s.done }
func (s *Session) ReadPacket() ([]byte, error) {
	select {
	case <-s.done:
		return nil, io.ErrClosedPipe
	default:
	}
	select {
	case p := <-s.packets:
		return p, nil
	case <-s.done:
		return nil, io.ErrClosedPipe
	}
}
func (s *Session) writeFrame(frame []byte) error {
	s.writeMu.Lock()
	defer s.writeMu.Unlock()
	select {
	case <-s.done:
		return io.ErrClosedPipe
	default:
	}
	_ = s.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
	if err := writeBlocks(s.conn, [][]byte{frame}); err != nil {
		_ = s.Close()
		return ErrProtocol
	}
	return nil
}
