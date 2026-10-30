// SPDX-License-Identifier: MIT
package softether

import (
	"bytes"
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/binary"
	"encoding/hex"
	"math/big"
	"net"
	"testing"
	"time"
)

func certificate(t *testing.T) (tls.Certificate, string) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	c := &x509.Certificate{SerialNumber: big.NewInt(1), DNSNames: []string{"vpn.example.com"}, NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour), IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}
	der, err := x509.CreateCertificate(rand.Reader, c, c, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	pin := sha256.Sum256(der)
	return tls.Certificate{Certificate: [][]byte{der}, PrivateKey: key}, hex.EncodeToString(pin[:])
}

func ipPacket(source, dest net.IP) []byte {
	b := make([]byte, 28)
	b[0] = 0x45
	b[8] = 64
	b[9] = 17
	binary.BigEndian.PutUint16(b[2:4], 28)
	copy(b[12:16], source.To4())
	copy(b[16:20], dest.To4())
	return b
}
func listener(t *testing.T, cert tls.Certificate) (net.Listener, <-chan *Session) {
	t.Helper()
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = l.Close() })
	accepted := make(chan *Session, 1)
	go func() {
		raw, err := l.Accept()
		if err != nil {
			return
		}
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		s, err := Accept(ctx, raw, cert, "test-authorization-123")
		if err == nil {
			accepted <- s
		}
	}()
	return l, accepted
}
func TestAuthenticatedPacketsAndClose(t *testing.T) {
	cert, pin := certificate(t)
	l, accepted := listener(t, cert)
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	c, err := Dial(ctx, l.Addr().String(), "test-authorization-123", "vpn.example.com", pin, (&net.Dialer{}).DialContext)
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	var s *Session
	select {
	case s = <-accepted:
	case <-ctx.Done():
		t.Fatal("server handshake timed out")
	}
	defer s.Close()
	for _, pair := range [][2]*Session{{c, s}, {s, c}} {
		packet := ipPacket(ClientIP, net.IPv4(1, 1, 1, 1))
		if pair[0] == s {
			packet = ipPacket(net.IPv4(1, 1, 1, 1), ClientIP)
		}
		if err = pair[0].WritePacket(packet); err != nil {
			t.Fatal(err)
		}
		got, err := pair[1].ReadPacket()
		if err != nil || !bytes.Equal(packet, got) {
			t.Fatal("authorized IP did not cross SoftEther")
		}
	}
	_ = c.Close()
	select {
	case <-s.Done():
	case <-time.After(time.Second):
		t.Fatal("close did not end peer")
	}
	if _, err = s.ReadPacket(); err == nil {
		t.Fatal("closed transport still readable")
	}
}
func TestRejectsBadTLSAndCredentials(t *testing.T) {
	cert, pin := certificate(t)
	for _, test := range []struct{ name, pin, secret string }{{"wrong.example.com", pin, "test-authorization-123"}, {"vpn.example.com", hex.EncodeToString(make([]byte, 32)), "test-authorization-123"}, {"vpn.example.com", pin, "wrong-authorization-123"}} {
		l, _ := listener(t, cert)
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		c, err := Dial(ctx, l.Addr().String(), test.secret, test.name, test.pin, (&net.Dialer{}).DialContext)
		cancel()
		if err == nil {
			_ = c.Close()
			t.Fatal("unauthorized SoftEther accepted")
		}
	}
}
