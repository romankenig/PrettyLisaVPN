// SPDX-License-Identifier: MIT
package managed

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net"
	"testing"
	"time"

	"github.com/miekg/dns"
	xnet "github.com/xtls/xray-core/common/net"
	"github.com/xtls/xray-core/common/session"
	"github.com/xtls/xray-core/core"
	"github.com/xtls/xray-core/infra/conf/serial"
)

// Real dispatcher, FakeDNS and TCP sockets, without altering the host network.
// VPN/direct test exits have separate loopback listeners and distinct replies.
func TestSplitRoutesRealFlowsAndFakeDNS(t *testing.T) {
	listener := func(marker string) string {
		l, err := net.Listen("tcp", "127.0.0.1:0")
		if err != nil {
			t.Fatal(err)
		}
		t.Cleanup(func() { _ = l.Close() })
		go func() {
			for {
				c, err := l.Accept()
				if err != nil {
					return
				}
				_, _ = io.WriteString(c, marker)
				_ = c.Close()
			}
		}()
		return l.Addr().String()
	}
	vpn, direct := listener("V"), listener("D")
	for _, mode := range []string{"include", "exclude"} {
		t.Run(mode, func(t *testing.T) {
			p := sample("VLESS_TLS")
			p.Routing = &Routing{Mode: mode, Domains: []string{"exact.example.com", "*.sub.example.com"}}
			data, _ := p.CoreConfig(true)
			var config map[string]any
			if json.Unmarshal(data, &config) != nil {
				t.Fatal("config")
			}
			config["inbounds"] = []any{}
			for _, item := range config["outbounds"].([]any) {
				out := item.(map[string]any)
				if out["tag"] == "vpn" || out["tag"] == "direct" {
					target := vpn
					if out["tag"] == "direct" {
						target = direct
					}
					out["protocol"], out["settings"] = "freedom", map[string]any{"redirect": target}
					delete(out, "streamSettings")
				}
			}
			data, _ = json.Marshal(config)
			c, err := serial.LoadJSONConfig(bytes.NewReader(data))
			if err != nil {
				t.Fatal(err)
			}
			instance, err := core.New(c)
			if err != nil {
				t.Fatal(err)
			}
			defer instance.Close()
			if err = instance.Start(); err != nil {
				t.Fatal(err)
			}
			ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
			defer cancel()
			ctx = session.ContextWithInbound(ctx, &session.Inbound{Tag: "tun"})
			for _, tc := range []struct {
				domain   string
				selected bool
			}{
				{"exact.example.com", true}, {"www.exact.example.com", false},
				{"x.sub.example.com", true}, {"sub.example.com", false},
				{"evilsub.example.com", false}, {"x.sub.example.com.attacker.invalid", false},
			} {
				expected := "D"
				if tc.selected == (mode == "include") {
					expected = "V"
				}
				for _, fake := range []bool{false, true} {
					address := xnet.DomainAddress(tc.domain)
					flowCtx := ctx
					if fake {
						query, _ := new(dns.Msg).SetQuestion(tc.domain+".", dns.TypeA).Pack()
						socket, err := core.Dial(ctx, instance, xnet.UDPDestination(xnet.ParseAddress("1.1.1.1"), 53))
						if err != nil {
							t.Fatal(err)
						}
						if _, err = socket.Write(query); err != nil {
							t.Fatal(err)
						}
						buffer := make([]byte, 4096)
						n, err := socket.Read(buffer)
						_ = socket.Close()
						if err != nil {
							t.Fatal(err)
						}
						var answer dns.Msg
						if answer.Unpack(buffer[:n]) != nil || len(answer.Answer) != 1 {
							t.Fatal("missing fake answer")
						}
						ip := answer.Answer[0].(*dns.A).A.To4()
						if len(ip) != 4 || ip[0] != 198 || (ip[1] != 18 && ip[1] != 19) {
							t.Fatal("not a fake address")
						}
						address = xnet.IPAddress(ip)
						flowCtx = session.ContextWithContent(ctx, &session.Content{SniffingRequest: session.SniffingRequest{Enabled: true, MetadataOnly: true, RouteOnly: true, OverrideDestinationForProtocol: []string{"fakedns"}}})
					}
					conn, err := core.Dial(flowCtx, instance, xnet.TCPDestination(address, 443))
					if err != nil {
						t.Fatal(err)
					}
					buffer := make([]byte, 1)
					_, err = io.ReadFull(conn, buffer)
					_ = conn.Close()
					if err != nil || string(buffer) != expected {
						t.Fatalf("%s fake=%v: got %q, want %s (%v)", tc.domain, fake, buffer, expected, err)
					}
				}
			}
			// The health origin must remain encrypted even in an empty include list.
			conn, err := core.Dial(ctx, instance, xnet.TCPDestination(xnet.DomainAddress("api.prettylisavpn.com"), 443))
			if err != nil {
				t.Fatal(err)
			}
			defer conn.Close()
			marker := make([]byte, 1)
			if _, err = io.ReadFull(conn, marker); err != nil || string(marker) != "V" {
				t.Fatal("verification escaped VPN")
			}
		})
	}
}
