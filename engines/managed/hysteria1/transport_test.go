// SPDX-License-Identifier: MIT
package hysteria1

import (
	"bytes"
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"io"
	"math/big"
	"net"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func testCertificate(t *testing.T) (tls.Certificate, string) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	template := &x509.Certificate{SerialNumber: big.NewInt(1), DNSNames: []string{"vpn.example.com"}, NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour), IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	pin := sha256.Sum256(der)
	return tls.Certificate{Certificate: [][]byte{der}, PrivateKey: key}, hex.EncodeToString(pin[:])
}
func packet(t *testing.T) net.PacketConn {
	t.Helper()
	p, e := net.ListenPacket("udp", "127.0.0.1:0")
	if e != nil {
		t.Fatal(e)
	}
	return p
}
func newTestClient(t *testing.T, address, secret, name, pin string) *Client {
	t.Helper()
	c, e := NewClient(address, secret, name, pin, func(context.Context) (net.PacketConn, error) { return net.ListenPacket("udp", "127.0.0.1:0") })
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() { _ = c.Close() })
	return c
}
func TestEncryptedTCPUDPAndIdentity(t *testing.T) {
	cert, pin := testCertificate(t)
	p := packet(t)
	var up, down atomic.Int64
	dialer := net.Dialer{Timeout: time.Second}
	s, e := NewServer(p, cert, "test-authorization-123", dialer.DialContext, func(u bool, n int) {
		if u {
			up.Add(int64(n))
		} else {
			down.Add(int64(n))
		}
	})
	if e != nil {
		t.Fatal(e)
	}
	defer s.Close()
	tcp, e := net.Listen("tcp", "127.0.0.1:0")
	if e != nil {
		t.Fatal(e)
	}
	defer tcp.Close()
	go func() {
		for {
			c, e := tcp.Accept()
			if e != nil {
				return
			}
			go func() { defer c.Close(); _, _ = io.Copy(c, c) }()
		}
	}()
	udp := packet(t)
	defer udp.Close()
	go func() {
		b := make([]byte, 65507)
		for {
			n, a, e := udp.ReadFrom(b)
			if e != nil {
				return
			}
			_, _ = udp.WriteTo(b[:n], a)
		}
	}()
	c := newTestClient(t, p.LocalAddr().String(), "test-authorization-123", "vpn.example.com", pin)
	for _, network := range []string{"tcp", "udp"} {
		t.Run(network, func(t *testing.T) {
			address := tcp.Addr().String()
			if network == "udp" {
				address = udp.LocalAddr().String()
			}
			conn, e := c.Dial(context.Background(), network, address)
			if e != nil {
				t.Fatal(e)
			}
			defer conn.Close()
			_ = conn.SetDeadline(time.Now().Add(5 * time.Second))
			body := bytes.Repeat([]byte("payload-"), 4000)
			if _, e = conn.Write(body); e != nil {
				t.Fatal(e)
			}
			got := make([]byte, len(body))
			if _, e = io.ReadFull(conn, got); e != nil {
				t.Fatal(e)
			}
			if !bytes.Equal(got, body) {
				t.Fatal("encrypted echo mismatch")
			}
		})
	}
	if up.Load() < 64000 || down.Load() < 64000 {
		t.Fatal("missing aggregate traffic counters")
	}
	for _, bad := range []struct{ name, pin, secret string }{
		{"wrong.example.com", pin, "test-authorization-123"},
		{"vpn.example.com", strings.Repeat("ff", 32), "test-authorization-123"},
		{"vpn.example.com", pin, "wrong-authorization-123"},
	} {
		badClient := newTestClient(t, p.LocalAddr().String(), bad.secret, bad.name, bad.pin)
		if conn, err := badClient.Dial(context.Background(), "tcp", tcp.Addr().String()); err == nil {
			conn.Close()
			t.Fatal("unauthorized identity accepted")
		}
	}
	conn, e := c.Dial(context.Background(), "udp", udp.LocalAddr().String())
	if e != nil {
		t.Fatal(e)
	}
	done := make(chan error, 1)
	go func() { _, e := conn.Read(make([]byte, 100)); done <- e }()
	_ = c.Close()
	select {
	case e := <-done:
		if e == nil {
			t.Fatal("close did not cancel read")
		}
	case <-time.After(time.Second):
		t.Fatal("read leaked after close")
	}
	if _, e = c.Dial(context.Background(), "tcp", tcp.Addr().String()); e == nil {
		t.Fatal("closed client reopened")
	}
}

func TestProtocolGoldenAndBounds(t *testing.T) {
	var out bytes.Buffer
	if e := hello(&out, "a"); e != nil {
		t.Fatal(e)
	}
	// Version 3, two big-endian 3,750,000 B/s rates, auth length 1, auth "a".
	if hex.EncodeToString(out.Bytes()) != "0300000000003938700000000000393870000161" {
		t.Fatalf("wire hello %x", out.Bytes())
	}
	if _, e := readHello(bytes.NewReader([]byte{2})); e == nil {
		t.Fatal("old version accepted")
	}
	var tooLong bytes.Buffer
	_ = write(&tooLong, uint16(65535))
	if _, e := getString(&tooLong, 128); e == nil {
		t.Fatal("oversize allocation accepted")
	}
	d := datagram{session: 7, host: "1.1.1.1", port: 53, id: 2, count: 2, data: []byte("one")}
	var fragments assembly
	if _, ok := fragments.accept(d); ok {
		t.Fatal("incomplete emitted")
	}
	d.index = 1
	d.host = "8.8.8.8"
	if _, ok := fragments.accept(d); ok {
		t.Fatal("mixed destination fragments")
	}
	d.index = 0
	d.data = []byte("two")
	if b, ok := fragments.accept(d); !ok || string(b) != "twoone" {
		t.Fatal("valid assembly failed")
	}
	raw, _ := d.encode()
	if _, e := decodeDatagram(append(raw, 0)); e == nil {
		t.Fatal("trailing byte accepted")
	}
}
func FuzzDatagram(f *testing.F) {
	raw, _ := (datagram{session: 1, host: "1.1.1.1", port: 53, count: 1, data: []byte("query")}).encode()
	f.Add(raw)
	f.Fuzz(func(t *testing.T, b []byte) {
		d, e := decodeDatagram(b)
		if e == nil {
			encoded, e := d.encode()
			if e != nil || !bytes.Equal(encoded, b) {
				t.Fatal("invalid parser round trip")
			}
			var a assembly
			_, _ = a.accept(d)
		}
	})
}
