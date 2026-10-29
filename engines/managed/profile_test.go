// SPDX-License-Identifier: MIT
package managed

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"testing"

	"github.com/xtls/xray-core/core"
	"github.com/xtls/xray-core/infra/conf/serial"
)

func TestSharedPlanContract(t *testing.T) {
	raw, err := os.ReadFile("testdata/plan-v1.json")
	if err != nil {
		t.Fatal(err)
	}
	var plan struct {
		Profiles []Profile `json:"profiles"`
	}
	if json.Unmarshal(raw, &plan) != nil || len(plan.Profiles) != 20 {
		t.Fatal("invalid shared plan")
	}
	for _, p := range plan.Profiles {
		checkCore(t, p)
	}
}

func sample(method string) Profile {
	key := base64.StdEncoding.EncodeToString(append([]byte{1}, make([]byte, 31)...))
	p := Profile{Version: 1, Session: "d84cd4d2-8aee-4c17-9772-31db1d512924", Country: "DE", Method: method, Server: "192.0.2.20", Port: 443, Secret: "test-only-disposable-password"}
	switch method {
	case "WIREGUARD", "AMNEZIA":
		p.Secret = key
		p.PublicKey = key
		p.Address = "10.77.0.2/32"
	case "VLESS_TLS", "VMESS_TLS", "VLESS_REALITY":
		p.Secret = p.Session
		p.ServerName = "vpn.example.com"
	case "SHADOWSOCKS_2022":
		p.Secret = key + ":" + key
	case "TROJAN_TLS", "HYSTERIA1_TLS", "HYSTERIA2_TLS", "HYSTERIA2_SALAMANDER":
		p.ServerName = "vpn.example.com"
	}
	if method == "VLESS_REALITY" {
		p.PublicKey = base64.RawURLEncoding.EncodeToString(append([]byte{1}, make([]byte, 31)...))
		p.ShortID = "1020304050607080"
	}
	if method == "HYSTERIA2_SALAMANDER" {
		p.ObfsSecret = "test-only-obfs-password"
	}
	return p
}
func TestGeneratedProfilesAcceptedByPinnedCore(t *testing.T) {
	for _, method := range []string{"WIREGUARD", "AMNEZIA", "VLESS_TLS", "VLESS_REALITY", "VMESS_TLS", "TROJAN_TLS", "SHADOWSOCKS", "SHADOWSOCKS_2022", "HYSTERIA1_TLS", "HYSTERIA2_TLS", "HYSTERIA2_SALAMANDER"} {
		t.Run(method, func(t *testing.T) { checkCore(t, sample(method)) })
	}
	for _, method := range []string{"VLESS_TLS", "VMESS_TLS", "TROJAN_TLS"} {
		for _, transport := range []string{"ws", "grpc", "httpupgrade", "xhttp"} {
			t.Run(method+"/"+transport, func(t *testing.T) {
				p := sample(method)
				p.Transport = transport
				p.Path = "/transport"
				if transport == "grpc" {
					p.Path = "transport"
				}
				checkCore(t, p)
			})
		}
	}
}
func checkCore(t *testing.T, p Profile) {
	t.Helper()
	for _, mobile := range []bool{false, true} {
		content, err := p.CoreConfig(mobile)
		if err != nil {
			t.Fatal(err)
		}
		c, err := serial.LoadJSONConfig(bytes.NewReader(content))
		if err != nil {
			t.Fatal("core rejected schema", err)
		}
		if err := p.Configure(c); err != nil {
			t.Fatal(err)
		}
		instance, err := core.New(c)
		if err != nil {
			t.Fatal("core rejected options", err)
		}
		// Never Start here: this check must not change host routes or contact peers.
		if instance.Close() != nil {
			t.Fatal("constructor cleanup failed")
		}
	}
}
func TestRejectUnsupportedAndUnsafeConfiguration(t *testing.T) {
	base := sample("TROJAN_TLS")
	data, _ := json.Marshal(base)
	for _, suffix := range []string{`,"insecure":true}`, `,"env":{"XRAY_TUN_FD":"1"}}`, `,"script":"execute"}`, `,"certificate":"file"}`, `,"log":{"level":"debug"}}`} {
		if _, err := ParseProfile(string(data[:len(data)-1]) + suffix); err == nil {
			t.Fatal("unknown option accepted")
		}
	}
	for _, method := range []string{"SOCKS", "HTTP", "VLESS", "DIRECT", "SSH", "HYSTERIA_TLS", "SHADOWSOCKS_UOT", "OPENVPN", "OPENCONNECT"} {
		p := base
		p.Method = method
		if p.Validate() == nil {
			t.Fatal("unsupported method accepted", method)
		}
	}
	for _, mutate := range []func(*Profile){
		func(p *Profile) { p.ServerName = "" }, func(p *Profile) { p.Country = "Z0" }, func(p *Profile) { p.Server = "127.0.0.1" }, func(p *Profile) { p.Server = "10.0.0.1" }, func(p *Profile) { p.Server = "vpn.example.com" }, func(p *Profile) { p.Port = 0 }, func(p *Profile) { p.Address = "10.0.0.1/32" }, func(p *Profile) { p.ObfsSecret = "ignored" }, func(p *Profile) { p.Transport = "quic" }, func(p *Profile) { p.Path = "/ignored" },
	} {
		p := base
		mutate(&p)
		if p.Validate() == nil {
			t.Fatal("unsafe field accepted")
		}
	}
	if _, err := ParseProfile(string(data) + string(data)); err == nil {
		t.Fatal("trailing JSON accepted")
	}
	if _, err := ParseProfile(strings.Repeat(" ", MaxProfileBytes+1)); err == nil {
		t.Fatal("oversized input accepted")
	}
	for _, method := range []string{"VLESS_REALITY", "WIREGUARD"} {
		p := sample(method)
		p.PublicKey = ""
		if p.Validate() == nil {
			t.Fatal("missing server key accepted")
		}
	}
}
func TestNoDirectDNSLoggingOrIPv6Escape(t *testing.T) {
	p := sample("TROJAN_TLS")
	for _, mobile := range []bool{false, true} {
		data, err := p.CoreConfig(mobile)
		if err != nil {
			t.Fatal(err)
		}
		var c map[string]any
		_ = json.Unmarshal(data, &c)
		log := c["log"].(map[string]any)
		if log["loglevel"] != "none" || log["access"] != "none" || log["error"] != "none" || log["dnsLog"] != false {
			t.Fatal("logging enabled")
		}
		outs := c["outbounds"].([]any)
		if len(outs) != 2 || outs[0].(map[string]any)["tag"] != "vpn" || outs[1].(map[string]any)["protocol"] != "blackhole" {
			t.Fatal("unexpected outbound")
		}
		rules := c["routing"].(map[string]any)["rules"].([]any)
		if rules[0].(map[string]any)["ip"].([]any)[0] != "::/0" || rules[0].(map[string]any)["outboundTag"] != "blocked" || rules[1].(map[string]any)["outboundTag"] != "vpn" {
			t.Fatal("traffic can escape")
		}
		tun := c["inbounds"].([]any)[0].(map[string]any)["settings"].(map[string]any)
		if mobile && tun["autoSystemRoutingTable"] != nil {
			t.Fatal("Android must own routes")
		}
		if !mobile && (len(tun["autoSystemRoutingTable"].([]any)) != 2 || len(tun["autoSystemWfpBlockLeak"].([]any)) != 2) {
			t.Fatal("desktop protection missing")
		}
		if c["dns"] != nil || strings.Contains(string(data), `"freedom"`) {
			t.Fatal("unexpected external resolver or direct route")
		}
	}
	for _, formatted := range []string{fmt.Sprint(p), fmt.Sprintf("%#v", p)} {
		if strings.Contains(formatted, p.Secret) {
			t.Fatal("secret in formatted profile")
		}
	}
}
