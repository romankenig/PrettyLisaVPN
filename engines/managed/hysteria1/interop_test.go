// SPDX-License-Identifier: MIT
package hysteria1

import (
	"bytes"
	"context"
	"crypto/sha256"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"io"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

// The official v1.3.5 executable is a test oracle, never packaged in a client.
// Only loopback forwarding is enabled. It creates no TUN, routes or DNS changes.
func TestOfficialV1Interop(t *testing.T) {
	reference := os.Getenv("PL_HYSTERIA1_REFERENCE")
	if reference == "" {
		t.Skip("official v1.3.5 test oracle not supplied")
	}
	raw, err := os.ReadFile(reference)
	if err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256(raw)
	if hex.EncodeToString(digest[:]) != "1001bd4a83f6addac166bfdfc3e777f3b751bb397e11b5d8f1d6ec1c2dd44023" {
		t.Fatal("wrong test oracle checksum")
	}
	directory := t.TempDir()
	cert, pin := testCertificate(t)
	certPath, keyPath := filepath.Join(directory, "cert.pem"), filepath.Join(directory, "key.pem")
	key, err := x509.MarshalPKCS8PrivateKey(cert.PrivateKey)
	if err != nil {
		t.Fatal(err)
	}
	if os.WriteFile(certPath, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: cert.Certificate[0]}), 0600) != nil || os.WriteFile(keyPath, pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: key}), 0600) != nil {
		t.Fatal("test credentials unavailable")
	}
	start := func(t *testing.T, mode string, config map[string]any) {
		t.Helper()
		path := filepath.Join(directory, mode+".json")
		data, _ := json.Marshal(config)
		if os.WriteFile(path, data, 0600) != nil {
			t.Fatal("config write failed")
		}
		ctx, cancel := context.WithCancel(context.Background())
		cmd := exec.CommandContext(ctx, reference, mode, "--config", path, "--no-check", "--log-level", "panic")
		if err := cmd.Start(); err != nil {
			cancel()
			t.Fatal(err)
		}
		t.Cleanup(func() { cancel(); _ = cmd.Wait() })
	}
	tcp, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
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
	check := func(t *testing.T, dial func(context.Context, string, string) (net.Conn, error), tcpAddress, udpAddress string) {
		t.Helper()
		for _, network := range []string{"tcp", "udp"} {
			address := tcpAddress
			if network == "udp" {
				address = udpAddress
			}
			var conn net.Conn
			var err error
			until := time.Now().Add(6 * time.Second)
			for time.Now().Before(until) {
				ctx, cancel := context.WithTimeout(context.Background(), time.Second)
				conn, err = dial(ctx, network, address)
				cancel()
				if err == nil {
					break
				}
				time.Sleep(25 * time.Millisecond)
			}
			if err != nil {
				t.Fatal("reference handshake failed", network)
			}
			_ = conn.SetDeadline(time.Now().Add(3 * time.Second))
			data := bytes.Repeat([]byte("v1-interoperable"), 80)
			_, err = conn.Write(data)
			got := make([]byte, len(data))
			if err == nil {
				_, err = io.ReadFull(conn, got)
			}
			_ = conn.Close()
			if err != nil || !bytes.Equal(got, data) {
				t.Fatal("reference encrypted roundtrip failed", network, err)
			}
		}
	}
	t.Run("new-client-official-server", func(t *testing.T) {
		p := packet(t)
		address := p.LocalAddr().String()
		p.Close()
		start(t, "server", map[string]any{"listen": address, "cert": certPath, "key": keyPath, "up_mbps": 30, "down_mbps": 30, "auth": map[string]any{"mode": "password", "config": map[string]any{"password": "interop-test-secret"}}})
		c := newTestClient(t, address, "interop-test-secret", "vpn.example.com", pin)
		check(t, c.Dial, tcp.Addr().String(), udp.LocalAddr().String())
	})
	t.Run("official-client-new-server", func(t *testing.T) {
		p := packet(t)
		dialer := net.Dialer{Timeout: time.Second}
		s, err := NewServer(p, cert, "interop-test-secret", dialer.DialContext, nil)
		if err != nil {
			t.Fatal(err)
		}
		defer s.Close()
		reserveTCP, err := net.Listen("tcp", "127.0.0.1:0")
		if err != nil {
			t.Fatal(err)
		}
		tcpAddress := reserveTCP.Addr().String()
		reserveTCP.Close()
		reserveUDP := packet(t)
		udpAddress := reserveUDP.LocalAddr().String()
		reserveUDP.Close()
		start(t, "client", map[string]any{"server": p.LocalAddr().String(), "auth_str": "interop-test-secret", "server_name": "vpn.example.com", "ca": certPath, "up_mbps": 30, "down_mbps": 30,
			"relay_tcps": []any{map[string]any{"listen": tcpAddress, "remote": tcp.Addr().String()}}, "relay_udps": []any{map[string]any{"listen": udpAddress, "remote": udp.LocalAddr().String()}}})
		check(t, dialer.DialContext, tcpAddress, udpAddress)
	})
}
