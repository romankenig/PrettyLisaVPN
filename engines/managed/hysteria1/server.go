// SPDX-License-Identifier: MIT
package hysteria1

import (
	"context"
	"crypto/subtle"
	"crypto/tls"
	"io"
	"net"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	quic "github.com/apernet/quic-go"
)

type DialFunc func(context.Context, string, string) (net.Conn, error)

// Server is one short-lived authorization, never a shared user/traffic logger.
// The injected dialer applies the node's private-network and DNS routing policy.
type Server struct {
	ctx         context.Context
	cancel      context.CancelFunc
	listener    *quic.Listener
	packet      net.PacketConn
	secret      string
	dial        DialFunc
	traffic     func(bool, int)
	mu          sync.Mutex
	connections map[*quic.Conn]struct{}
	wg          sync.WaitGroup
	once        sync.Once
}

func NewServer(packet net.PacketConn, certificate tls.Certificate, secret string, dial DialFunc, traffic func(bool, int)) (*Server, error) {
	l, err := quic.Listen(packet, &tls.Config{Certificates: []tls.Certificate{certificate}, MinVersion: tls.VersionTLS13, NextProtos: []string{"hysteria"}}, quicConfig())
	if err != nil {
		return nil, err
	}
	ctx, cancel := context.WithCancel(context.Background())
	s := &Server{ctx: ctx, cancel: cancel, listener: l, packet: packet, secret: secret, dial: dial, traffic: traffic, connections: make(map[*quic.Conn]struct{})}
	s.wg.Add(1)
	go s.accept()
	return s, nil
}
func (s *Server) Close() error {
	s.once.Do(func() {
		s.cancel()
		_ = s.listener.Close()
		_ = s.packet.Close()
		s.mu.Lock()
		for c := range s.connections {
			_ = c.CloseWithError(0, "")
		}
		s.mu.Unlock()
		s.wg.Wait()
	})
	return nil
}
func (s *Server) accept() {
	defer s.wg.Done()
	for {
		c, err := s.listener.Accept(s.ctx)
		if err != nil {
			return
		}
		s.mu.Lock()
		if s.ctx.Err() != nil || len(s.connections) >= 4 {
			s.mu.Unlock()
			_ = c.CloseWithError(1, "")
			continue
		}
		s.connections[c] = struct{}{}
		s.wg.Add(1)
		s.mu.Unlock()
		go func() { defer s.wg.Done(); s.serve(c); s.mu.Lock(); delete(s.connections, c); s.mu.Unlock() }()
	}
}
func (s *Server) serve(c *quic.Conn) {
	defer c.CloseWithError(0, "")
	ctx, cancel := context.WithTimeout(c.Context(), handshakeTimeout)
	control, err := c.AcceptStream(ctx)
	cancel()
	if err != nil {
		return
	}
	_ = control.SetDeadline(time.Now().Add(handshakeTimeout))
	secret, err := readHello(control)
	accepted := err == nil && subtle.ConstantTimeCompare([]byte(secret), []byte(s.secret)) == 1
	if helloResponse(control, accepted) != nil || !accepted {
		return
	}
	_ = control.SetDeadline(time.Time{})
	p := newPeer(c)
	go p.receive()
	var next atomic.Uint32
	var streams sync.WaitGroup
	defer func() { _ = c.CloseWithError(0, ""); streams.Wait() }()
	for {
		stream, err := c.AcceptStream(c.Context())
		if err != nil {
			return
		}
		streams.Add(1)
		go func() {
			defer streams.Done()
			defer closeStream(stream)
			_ = stream.SetDeadline(time.Now().Add(handshakeTimeout))
			udp, address, err := readRequest(stream)
			if err != nil {
				return
			}
			if udp {
				s.serveUDP(p, stream, next.Add(1))
				return
			}
			upstream, err := s.dial(c.Context(), "tcp", address)
			if err != nil {
				_ = response(stream, false, 0)
				return
			}
			defer upstream.Close()
			stop := context.AfterFunc(c.Context(), func() { _ = upstream.Close() })
			defer stop()
			if response(stream, true, 0) != nil {
				return
			}
			_ = stream.SetDeadline(time.Time{})
			s.copyTCP(stream, upstream)
		}()
	}
}

type countingWriter struct {
	io.Writer
	count func(int)
}

func (w countingWriter) Write(b []byte) (int, error) {
	n, e := w.Writer.Write(b)
	w.count(n)
	return n, e
}
func (s *Server) count(up bool, n int) {
	if s.traffic != nil {
		s.traffic(up, n)
	}
}
func (s *Server) copyTCP(stream *quic.Stream, conn net.Conn) {
	done := make(chan struct{}, 1)
	go func() {
		_, _ = io.Copy(countingWriter{conn, func(n int) { s.count(true, n) }}, stream)
		if half, ok := conn.(interface{ CloseWrite() error }); ok {
			_ = half.CloseWrite()
		}
		done <- struct{}{}
	}()
	_, _ = io.Copy(countingWriter{stream, func(n int) { s.count(false, n) }}, conn)
	_ = conn.Close()
	stream.CancelRead(0)
	<-done
}
func (s *Server) serveUDP(p *peer, stream *quic.Stream, id uint32) {
	ch, err := p.register(id)
	if err != nil {
		return
	}
	defer p.remove(id)
	if response(stream, true, id) != nil {
		return
	}
	_ = stream.SetDeadline(time.Time{})
	ctx, cancel := context.WithCancel(p.conn.Context())
	defer cancel()
	go func() { _, _ = io.Copy(io.Discard, stream); cancel() }()
	// Each authenticated session has at most eight destinations. The oldest is
	// evicted on demand, bounding descriptors while retaining protocol v1's mux.
	type flow struct {
		conn   net.Conn
		host   string
		port   uint16
		used   time.Time
		closed atomic.Bool
	}
	flows := make(map[string]*flow)
	var wg sync.WaitGroup
	defer func() {
		for _, f := range flows {
			_ = f.conn.Close()
		}
		wg.Wait()
	}()
	var fragments assembly
	for {
		select {
		case <-ctx.Done():
			return
		case d := <-ch:
			data, ok := fragments.accept(d)
			if !ok {
				continue
			}
			address := net.JoinHostPort(d.host, strconv.Itoa(int(d.port)))
			f := flows[address]
			if f != nil && f.closed.Load() {
				delete(flows, address)
				f = nil
			}
			if f == nil {
				if len(flows) >= 8 {
					var oldest string
					var before time.Time
					for a, f := range flows {
						if oldest == "" || f.used.Before(before) {
							oldest, before = a, f.used
						}
					}
					_ = flows[oldest].conn.Close()
					delete(flows, oldest)
				}
				conn, err := s.dial(ctx, "udp", address)
				if err != nil {
					continue
				}
				f = &flow{conn: conn, host: d.host, port: d.port}
				flows[address] = f
				wg.Add(1)
				go func(f *flow) {
					defer wg.Done()
					defer func() { f.closed.Store(true); _ = f.conn.Close() }()
					b := make([]byte, 65507)
					for {
						n, e := f.conn.Read(b)
						if e != nil {
							return
						}
						s.count(false, n)
						if p.send(id, f.host, f.port, b[:n]) != nil {
							return
						}
					}
				}(f)
			}
			f.used = time.Now()
			n, err := f.conn.Write(data)
			s.count(true, n)
			if err != nil {
				_ = f.conn.Close()
				delete(flows, address)
			}
		}
	}
}
