// SPDX-License-Identifier: MIT
package sstp

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

	"github.com/romankenig/PrettyLisaVPN/engines/managed/internal/pinnedtls"
	"github.com/romankenig/PrettyLisaVPN/engines/managed/sstp/internal/mschap"
	"github.com/romankenig/PrettyLisaVPN/engines/managed/sstp/internal/ppp"
	"github.com/romankenig/PrettyLisaVPN/engines/managed/sstp/internal/wire"
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

func TestNetworkNegotiationAcceptsDummyPPPAddressButStillRequiresAuthentication(t *testing.T) {
	for _, peer := range []net.IP{nil, net.IPv4(192, 0, 0, 8), ServerIP} {
		s := &Session{ready: make(chan struct{})}
		clientHandler{s}.NetworkUp(ppp.IPConfig{LocalIP: ClientIP, PeerIP: peer})
		if !s.network {
			t.Fatal("valid PPP configuration rejected")
		}
		select {
		case <-s.ready:
			t.Fatal("IPCP bypassed authentication and binding")
		default:
		}
	}
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
			t.Fatal("authorized IP did not cross SSTP")
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
			t.Fatal("unauthorized SSTP accepted")
		}
	}
}
func TestRejectsDataBeforePPPAuthentication(t *testing.T) {
	cert, pin := certificate(t)
	l, accepted := listener(t, cert)
	configuration, err := pinnedtls.Config("vpn.example.com", pin)
	if err != nil {
		t.Fatal(err)
	}
	c, err := tls.Dial("tcp", l.Addr().String(), configuration)
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	_ = c.SetDeadline(time.Now().Add(time.Second))
	if sstpHandshake(c, "vpn.example.com") != nil || sendCallConnectRequest(c) != nil {
		t.Fatal("opening handshake failed")
	}
	if _, err = readCallConnectAck(c); err != nil {
		t.Fatal(err)
	}
	data, _ := wire.EncodeData(ppp.EncapsulateIP(ipPacket(ClientIP, net.IPv4(1, 1, 1, 1))))
	_, _ = c.Write(data)
	for {
		if _, _, err = wire.ReadPacket(c); err != nil {
			if timeout, ok := err.(net.Error); ok && timeout.Timeout() {
				t.Fatal("server did not reject premature data")
			}
			break
		}
	}
	select {
	case s := <-accepted:
		_ = s.Close()
		t.Fatal("premature IP authorized")
	default:
	}
}
func TestBindingRequiresCurrentNonceAndAuthentication(t *testing.T) {
	secret := "test-authorization-123"
	var response [mschap.NTResponseLen]byte
	for _, test := range []struct{ authed, bound, badNonce bool }{{false, false, false}, {true, true, false}, {true, false, true}, {true, false, false}} {
		nonce := bytes.Repeat([]byte{7}, 32)
		s := &Session{secret: secret, authed: test.authed, bound: test.bound, nonce: nonce, certificate: []byte("cert"), ntResponse: response}
		provided := append([]byte(nil), nonce...)
		if test.badNonce {
			provided[0]++
		}
		packet, err := buildCallConnected(provided, s.certificate, mschap.ClientHLAK(secret, response))
		if err != nil {
			t.Fatal(err)
		}
		msg, err := wire.ParseControl(packet[4:])
		if err != nil {
			t.Fatal(err)
		}
		err = s.verifyBinding(packet[4:], msg)
		want := test.authed && !test.bound && !test.badNonce
		if (err == nil) != want {
			t.Fatal("binding admission mismatch")
		}
	}
}
