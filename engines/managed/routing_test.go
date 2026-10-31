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
				p.Routing = &Routing{Mode: mode, Domains: []string{"youtube.com", "*.youtube.com"}, IPv4CIDRs: []string{"91.108.4.0/22"}}
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

func TestServiceNetworksValidateWithoutAllowingPrivateOrFakeDestinations(t *testing.T) {
	for _, value := range []string{"91.108.4.0/22", "149.154.160.0/20", "185.76.151.1/32"} {
		p := sample("WIREGUARD")
		p.Routing = &Routing{Mode: "include", IPv4CIDRs: []string{value}}
		if err := p.Validate(); err != nil {
			t.Fatalf("valid service network rejected: %v", err)
		}
	}
	for _, value := range []string{"91.108.4.1/22", "91.108.4.0", "091.108.4.0/22", "1.0.0.0/7", "0.0.0.0/0", "127.0.0.1/32", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "100.64.0.0/10", "198.18.0.0/15", "198.0.0.0/8", "224.0.0.0/4", "2001:b28:f23d::/48"} {
		p := sample("WIREGUARD")
		p.Routing = &Routing{Mode: "include", IPv4CIDRs: []string{value}}
		if p.Validate() == nil {
			t.Fatalf("invalid service network accepted: %q", value)
		}
	}
	for _, routing := range []*Routing{
		{Mode: "all", IPv4CIDRs: []string{"91.108.4.0/22"}},
		{Mode: "include", IPv4CIDRs: make([]string, 257)},
	} {
		if routing.validate() == nil {
			t.Fatal("invalid network policy accepted")
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
