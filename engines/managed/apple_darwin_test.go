// SPDX-License-Identifier: MIT
package managed

import (
	"encoding/json"
	"testing"
)

func TestAppleRetainsTypedProfileWithoutHostRouteMutation(t *testing.T) {
	for _, method := range []string{"WIREGUARD", "AMNEZIA", "SSTP", "SOFTETHER", "VLESS_TLS", "VLESS_REALITY", "VMESS_TLS", "SHADOWSOCKS_2022", "HYSTERIA1_TLS", "HYSTERIA2_TLS", "HYSTERIA2_SALAMANDER"} {
		p := sample(method)
		data, err := p.CoreConfig(true)
		if err != nil {
			t.Fatal(err)
		}
		var config map[string]any
		if json.Unmarshal(data, &config) != nil {
			t.Fatal("invalid configuration")
		}
		tun := config["inbounds"].([]any)[0].(map[string]any)["settings"].(map[string]any)
		for _, key := range []string{"autoOutboundsInterface", "autoSystemRoutingTable", "autoSystemWfpBlockLeak", "dns", "gateway"} {
			if _, found := tun[key]; found {
				t.Fatalf("Apple core must not mutate %s", key)
			}
		}
	}
}
