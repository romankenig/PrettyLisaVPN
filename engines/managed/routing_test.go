// SPDX-License-Identifier: MIT
package managed

import (
	"bytes"
	"testing"

	"github.com/xtls/xray-core/core"
	"github.com/xtls/xray-core/infra/conf/serial"
)

func TestRoutingProfilesInstantiatePinnedCore(t *testing.T) {
	for _, method := range []string{"WIREGUARD", "AMNEZIA", "VLESS_REALITY", "VLESS_TLS", "VMESS_TLS", "SHADOWSOCKS_2022", "SSTP", "SOFTETHER", "HYSTERIA1_TLS", "HYSTERIA2_TLS", "HYSTERIA2_SALAMANDER"} {
		for _, mode := range []string{"include", "exclude"} {
			t.Run(method+"/"+mode, func(t *testing.T) {
				p := sample(method)
				p.Routing = &Routing{Mode: mode, Domains: []string{"youtube.com", "*.youtube.com"}}
				data, err := p.CoreConfig(true)
				if err != nil {
					t.Fatal(err)
				}
				config, err := serial.LoadJSONConfig(bytes.NewReader(data))
				if err != nil {
					t.Fatal(err)
				}
				if err = p.Configure(config); err != nil {
					t.Fatal(err)
				}
				instance, err := core.New(config)
				if err != nil {
					t.Fatal(err)
				}
				if err = instance.Close(); err != nil {
					t.Fatal(err)
				}
			})
		}
	}
}

func TestRoutingRejectsUnsafeMasks(t *testing.T) {
	for _, mask := range []string{"https://a.com", "a.com/x", "a.*.com", "*.com", "127.0.0.1", "a..com", "a.com:443", "A.COM", "-a.com", "a.com\n"} {
		p := sample("VLESS_TLS")
		p.Routing = &Routing{Mode: "include", Domains: []string{mask}}
		if p.Validate() == nil {
			t.Fatalf("accepted invalid mask %q", mask)
		}
	}
	for _, mode := range []string{"", "random", "all"} {
		p := sample("VLESS_TLS")
		p.Routing = &Routing{Mode: mode, Domains: []string{"a.com"}}
		if p.Validate() == nil {
			t.Fatalf("accepted invalid mode %q", mode)
		}
	}
}
