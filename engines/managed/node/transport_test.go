// SPDX-License-Identifier: MIT
package node

import (
	"bytes"
	"context"
	"crypto/ecdh"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"io"
	"math/big"
	"net"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	managed "github.com/romankenig/PrettyLisaVPN/engines/managed"
	xnet "github.com/xtls/xray-core/common/net"
	"github.com/xtls/xray-core/core"
	"github.com/xtls/xray-core/infra/conf/serial"
)

func certificate(t *testing.T) (string, string, string) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	ca := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "Disposable test CA"}, NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour), IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature}
	caDER, err := x509.CreateCertificate(rand.Reader, ca, ca, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	leaf := &x509.Certificate{SerialNumber: big.NewInt(2), DNSNames: []string{"vpn.example.com"}, NotBefore: ca.NotBefore, NotAfter: ca.NotAfter, KeyUsage: x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}
	der, err := x509.CreateCertificate(rand.Reader, leaf, ca, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	private, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		t.Fatal(err)
	}
	cert := string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})) + string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: caDER}))
	pin := sha256.Sum256(caDER)
	return cert, string(pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: private})), hex.EncodeToString(pin[:])
}

// Loopback TCP/UDP only. No TUN, system routes, production node or customer traffic.
// Exercise real handshakes and encrypted application data, not only config constructors.
func TestPlanEncryptedTCPAndUDP(t *testing.T) {
	cert, key, pin := certificate(t)
	l := fixture()
	l.Listen = "127.0.0.1"
	l.Plan = true
	l.TLSCertificate = cert
	l.TLSKey = key
	private, _ := ecdh.X25519().GenerateKey(rand.Reader)
	l.PrivateKey = base64.RawURLEncoding.EncodeToString(private.Bytes())
	// The REALITY camouflage origin is a separate disposable TLS 1.3 server.
	target := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(204) }))
	pair, err := tls.X509KeyPair([]byte(cert), []byte(key))
	if err != nil {
		t.Fatal(err)
	}
	target.TLS = &tls.Config{Certificates: []tls.Certificate{pair}, MinVersion: tls.VersionTLS13, CurvePreferences: []tls.CurveID{tls.X25519}, NextProtos: []string{"h2", "http/1.1"}}
	target.StartTLS()
	defer target.Close()
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
	udp, err := net.ListenPacket("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer udp.Close()
	go func() {
		b := make([]byte, 1500)
		for {
			n, a, e := udp.ReadFrom(b)
			if e != nil {
				return
			}
			_, _ = udp.WriteTo(b[:n], a)
		}
	}()
	// Reserve a contiguous block temporarily to avoid colliding with local services.
	for start := 24000; start < 60000; start += PlanPorts {
		listeners := []io.Closer{}
		available := true
		for port := start; port < start+PlanPorts; port++ {
			a, e := net.Listen("tcp", fmt.Sprintf("127.0.0.1:%d", port))
			if e != nil {
				available = false
				break
			}
			listeners = append(listeners, a)
			b, e := net.ListenPacket("udp", fmt.Sprintf("127.0.0.1:%d", port))
			if e != nil {
				available = false
				break
			}
			listeners = append(listeners, b)
		}
		for _, c := range listeners {
			_ = c.Close()
		}
		if available {
			l.Port = uint16(start)
			break
		}
	}
	inbounds := l.inbounds()
	inbounds[0].(map[string]any)["streamSettings"].(map[string]any)["realitySettings"].(map[string]any)["target"] = strings.TrimPrefix(target.URL, "https://")
	// Only this test omits production's private-destination block to reach the echo servers.
	data, _ := json.Marshal(map[string]any{"log": map[string]any{"loglevel": "none", "access": "none", "error": "none"}, "inbounds": inbounds, "outbounds": []any{map[string]any{"protocol": "freedom", "tag": "internet", "settings": map[string]any{"finalRules": []any{map[string]any{"action": "allow", "ip": []string{"127.0.0.1/32"}}}}}}})
	sc, err := serial.LoadJSONConfig(bytes.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	server, err := core.New(sc)
	if err != nil {
		t.Fatal(err)
	}
	defer server.Close()
	if err = server.Start(); err != nil {
		t.Fatal(err)
	}
	profiles := []managed.Profile{}
	add := func(method, transport string) {
		p := managed.Profile{Version: 1, Session: l.ID, Country: "DE", Method: method, Server: "192.0.2.20", Port: l.Port + uint16(len(profiles)), Secret: l.Secret, Transport: transport}
		if method == "VLESS_REALITY" {
			p.PublicKey = base64.RawURLEncoding.EncodeToString(private.PublicKey().Bytes())
			p.ShortID = l.ShortID
			p.ServerName = l.ServerName
		} else if strings.Contains(method, "TLS") || method == "HYSTERIA2_SALAMANDER" {
			p.ServerName = l.ServerName
			p.CertificatePin = pin
		}
		if transport != "" {
			p.Path = "/plvpn"
			if transport == "grpc" {
				p.Path = "plvpn"
			}
		}
		if method == "SHADOWSOCKS_2022" {
			p.Secret = derived(l.Secret, "ss-server") + ":" + derived(l.Secret, "ss-user")
		}
		if method == "HYSTERIA2_SALAMANDER" {
			p.ObfsSecret = derived(l.Secret, "salamander")
		}
		profiles = append(profiles, p)
	}
	add("VLESS_REALITY", "")
	for _, m := range []string{"VLESS_TLS", "VMESS_TLS", "TROJAN_TLS"} {
		for _, tr := range []string{"", "ws", "grpc", "httpupgrade", "xhttp"} {
			add(m, tr)
		}
	}
	for _, m := range []string{"SHADOWSOCKS", "SHADOWSOCKS_2022", "HYSTERIA2_TLS", "HYSTERIA2_SALAMANDER"} {
		add(m, "")
	}
	if len(profiles) != PlanPorts {
		t.Fatal("catalog size mismatch")
	}
	wrongPin := profiles[1]
	wrongPin.CertificatePin = strings.Repeat("ff", 32)
	wrongName := profiles[1]
	wrongName.ServerName = "wrong.example.com"
	profiles = append(profiles, wrongPin, wrongName)
	for _, p := range profiles {
		reject := p.CertificatePin != "" && (p.CertificatePin != pin || p.ServerName != l.ServerName)
		name := p.Method + "/" + p.Transport
		if reject {
			name += "/reject-server-identity"
		}
		t.Run(name, func(t *testing.T) {
			raw, err := p.CoreConfig(true)
			if err != nil {
				t.Fatal(err)
			}
			var cfg map[string]any
			_ = json.Unmarshal(raw, &cfg)
			delete(cfg, "inbounds")
			// Isolated test endpoint only; production ParseProfile still rejects loopback.
			cfg["outbounds"].([]any)[0].(map[string]any)["settings"].(map[string]any)["address"] = "127.0.0.1"
			raw, _ = json.Marshal(cfg)
			c, err := serial.LoadJSONConfig(bytes.NewReader(raw))
			if err != nil {
				t.Fatal(err)
			}
			client, err := core.New(c)
			if err != nil {
				t.Fatal(err)
			}
			defer client.Close()
			if err = client.Start(); err != nil {
				t.Fatal(err)
			}
			for _, target := range []struct{ network, address string }{{"tcp", tcp.Addr().String()}, {"udp", udp.LocalAddr().String()}} {
				// REALITY's fresh camouflage probe can take two five-second intervals.
				limit := 15 * time.Second
				if reject {
					limit = 2 * time.Second
				}
				ctx, cancel := context.WithTimeout(context.Background(), limit)
				dest, err := xnet.ParseDestination(target.network + ":" + target.address)
				if err != nil {
					t.Fatal(err)
				}
				conn, err := core.Dial(ctx, client, dest)
				if err != nil {
					cancel()
					t.Fatal(err)
				}
				done := make(chan error, 1)
				go func() {
					message := []byte("disposable-probe-" + strconv.Itoa(int(p.Port)))
					_, e := conn.Write(message)
					if e == nil {
						b := make([]byte, len(message))
						_, e = io.ReadFull(conn, b)
						if e == nil && !bytes.Equal(b, message) {
							e = fmt.Errorf("echo mismatch")
						}
					}
					done <- e
				}()
				select {
				case err = <-done:
				case <-ctx.Done():
					err = ctx.Err()
				}
				_ = conn.Close()
				cancel()
				if reject {
					if err == nil {
						t.Fatal("untrusted server exchanged data")
					}
					return
				}
				if err != nil {
					t.Fatalf("%s data exchange: %v", target.network, err)
				}
			}
		})
	}
}
