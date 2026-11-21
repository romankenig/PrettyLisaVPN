// SPDX-License-Identifier: MIT
package managed

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/miekg/dns"
	xnet "github.com/xtls/xray-core/common/net"
	"github.com/xtls/xray-core/common/session"
	"github.com/xtls/xray-core/core"
	xdns "github.com/xtls/xray-core/features/dns"
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
			p.Routing = &Routing{Mode: mode, Domains: []string{"exact.example.com", "*.sub.example.com", "ifconfig.me", "*.ifconfig.me"}, IPv4CIDRs: []string{"91.108.4.0/22", "149.154.160.0/20"}}
			if mode == "exclude" {
				// Explicit exclusions must not override the API verification routes.
				p.Routing.Domains = append(p.Routing.Domains, "api.prettylisavpn.com", "api.test.prettylisavpn.com")
			}
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
				forceVPN bool
			}{
				{domain: "exact.example.com", selected: true},
				{domain: "www.exact.example.com"},
				{domain: "x.sub.example.com", selected: true},
				{domain: "sub.example.com"},
				{domain: "evilsub.example.com"},
				{domain: "x.sub.example.com.attacker.invalid"},
				{domain: "ifconfig.me.attacker.invalid"},
				{domain: "api.test.prettylisavpn.com.attacker.invalid"},
				{domain: "api.prettylisavpn.com", forceVPN: true},
				{domain: "api.test.prettylisavpn.com", forceVPN: true},
				{domain: "ifconfig.me", forceVPN: true},
				{domain: "www.ifconfig.me", forceVPN: true},
			} {
				expected := "D"
				if tc.forceVPN || tc.selected == (mode == "include") {
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
			// Native MTProto has no DNS/domain metadata: the destination IP alone
			// must choose the selected exit, in both inverse policies.
			for _, tc := range []struct {
				address  string
				selected bool
			}{
				{"91.108.4.1", true}, {"91.108.7.255", true}, {"149.154.167.50", true}, {"91.108.8.1", false},
			} {
				expected := "D"
				if tc.selected == (mode == "include") {
					expected = "V"
				}
				conn, err := core.Dial(ctx, instance, xnet.TCPDestination(xnet.ParseAddress(tc.address), 443))
				if err != nil {
					t.Fatal(err)
				}
				marker := make([]byte, 1)
				_, err = io.ReadFull(conn, marker)
				_ = conn.Close()
				if err != nil || string(marker) != expected {
					t.Fatal("literal IP used wrong exit")
				}
			}
		})
	}
}

func TestAndroidSplitDirectDNSWithUnavailableVPNResolver(t *testing.T) {
	site := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = io.WriteString(w, "direct site")
	}))
	defer site.Close()
	_, portString, err := net.SplitHostPort(strings.TrimPrefix(site.URL, "http://"))
	if err != nil {
		t.Fatal(err)
	}
	port, err := strconv.Atoi(portString)
	if err != nil {
		t.Fatal(err)
	}
	requests := make(chan string, 16)
	resolver := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		data, err := io.ReadAll(r.Body)
		var query dns.Msg
		if err != nil || query.Unpack(data) != nil || len(query.Question) != 1 {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		question := query.Question[0]
		requests <- r.URL.Path + " " + question.Name
		if r.URL.Path == "/direct" && question.Name == "backup.example.com." {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		reply := new(dns.Msg).SetReply(&query)
		reply.Answer = []dns.RR{&dns.A{
			Hdr: dns.RR_Header{Name: question.Name, Rrtype: dns.TypeA, Class: dns.ClassINET, Ttl: 60},
			A:   net.IPv4(127, 0, 0, 1),
		}}
		data, _ = reply.Pack()
		w.Header().Set("Content-Type", "application/dns-message")
		_, _ = w.Write(data)
	}))
	resolver.Config.Protocols = new(http.Protocols)
	resolver.Config.Protocols.SetUnencryptedHTTP2(true)
	resolver.Start()
	defer resolver.Close()

	for _, tc := range []struct {
		name, mode, directHost, vpnHost string
		splitDNS, vpnAvailable          bool
	}{
		{"previous Android", "include", "outside.example.com", "", false, false},
		{"include", "include", "outside.example.com", "sub.selected.example.com", true, false},
		{"exclude", "exclude", "sub.selected.example.com", "selected.example.com", true, false},
		{"direct resolver unavailable", "include", "backup.example.com", "sub.selected.example.com", true, true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			type obj = map[string]any
			p := sample("VLESS_TLS")
			p.Routing = &Routing{Mode: tc.mode, Domains: []string{
				"*.selected.example.com", "api.test.prettylisavpn.com", "*.ifconfig.me",
			}}
			data, err := p.coreConfig(true, tc.splitDNS)
			if err != nil {
				t.Fatal(err)
			}
			var config obj
			if err := json.Unmarshal(data, &config); err != nil {
				t.Fatal(err)
			}
			config["inbounds"] = []any{}
			vpn := config["outbounds"].([]any)[0].(obj)
			vpn["protocol"], vpn["settings"] = "blackhole", obj{}
			if tc.vpnAvailable {
				vpn["protocol"] = "freedom"
			}
			delete(vpn, "streamSettings")
			dnsConfig := config["dns"].(obj)
			if tc.splitDNS {
				resolverURL := "h2c://" + strings.TrimPrefix(resolver.URL, "http://")
				for _, entry := range dnsConfig["servers"].([]any) {
					server := entry.(obj)
					if server["tag"] == "resolver-direct" {
						server["address"] = resolverURL + "/direct"
					} else if server["address"] != "fakedns" {
						server["timeoutMs"] = 150
						if tc.vpnAvailable {
							server["address"] = resolverURL + "/vpn"
							server["timeoutMs"] = 2000
						}
					}
				}
			} else {
				dnsConfig["servers"].([]any)[1] = obj{"address": "1.1.1.1", "timeoutMs": 150}
			}
			data, err = json.Marshal(config)
			if err != nil {
				t.Fatal(err)
			}
			built, err := serial.LoadJSONConfig(bytes.NewReader(data))
			if err != nil {
				t.Fatal(err)
			}
			instance, err := core.New(built)
			if err != nil {
				t.Fatal(err)
			}
			defer instance.Close()
			if err := instance.Start(); err != nil {
				t.Fatal(err)
			}
			client := instance.GetFeature(xdns.ClientType()).(xdns.Client)
			fake, _, err := client.LookupIP(tc.directHost, xdns.IPOption{IPv4Enable: true, FakeEnable: true})
			if err != nil || len(fake) != 1 || fake[0].To4() == nil || fake[0].To4()[0] != 198 {
				t.Fatalf("expected FakeDNS address, got %v (%v)", fake, err)
			}
			select {
			case domain := <-requests:
				t.Fatalf("FakeDNS sent a real query for %s", domain)
			default:
			}
			if !tc.splitDNS {
				if ips, _, _ := client.LookupIP(tc.directHost, xdns.IPOption{IPv4Enable: true}); len(ips) != 0 {
					t.Fatalf("previous direct DNS unexpectedly worked without the VPN resolver: %v", ips)
				}
				return
			}
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			ctx = session.ContextWithInbound(ctx, &session.Inbound{Tag: "tun"})
			ctx = session.ContextWithContent(ctx, &session.Content{SniffingRequest: session.SniffingRequest{
				Enabled: true, MetadataOnly: true, RouteOnly: true, OverrideDestinationForProtocol: []string{"fakedns"},
			}})
			conn, err := core.Dial(ctx, instance, xnet.TCPDestination(xnet.IPAddress(fake[0]), xnet.Port(port)))
			if err != nil {
				t.Fatal(err)
			}
			defer conn.Close()
			if _, err := io.WriteString(conn, "GET / HTTP/1.0\r\nHost: "+tc.directHost+"\r\n\r\n"); err != nil {
				t.Fatal(err)
			}
			response, err := io.ReadAll(conn)
			if err != nil || !bytes.Contains(response, []byte("direct site")) {
				t.Fatalf("direct request failed: %q (%v)", response, err)
			}
			checkRequest := func(path, domain string) {
				t.Helper()
				select {
				case request := <-requests:
					if request != path+" "+domain+"." {
						t.Fatalf("wanted %s DNS query for %s, got %s", path, domain, request)
					}
				default:
					t.Fatalf("missing %s DNS query for %s", path, domain)
				}
			}
			checkRequest("/direct", tc.directHost)
			if tc.vpnAvailable {
				checkRequest("/vpn", tc.directHost)
			}
			for _, domain := range []string{tc.vpnHost, "api.test.prettylisavpn.com", "www.ifconfig.me"} {
				ips, _, err := client.LookupIP(domain, xdns.IPOption{IPv4Enable: true})
				if tc.vpnAvailable {
					if err != nil || len(ips) != 1 {
						t.Fatalf("VPN lookup failed for %s: %v (%v)", domain, ips, err)
					}
					checkRequest("/vpn", domain)
				} else if len(ips) != 0 {
					t.Fatalf("%s was resolved even though the VPN resolver is unavailable: %v", domain, ips)
				}
			}
			select {
			case domain := <-requests:
				t.Fatalf("VPN domain reached the direct resolver: %s", domain)
			default:
			}
		})
	}
}
