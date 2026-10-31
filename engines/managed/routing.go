// SPDX-License-Identifier: MIT
package managed

import (
	"net/netip"
	"regexp"
	"strings"
)

// Routing contains explicit device preferences only. No observed destinations
// are persisted or exported. Nil preserves the existing full-tunnel profile.
type Routing struct {
	Mode      string   `json:"mode"`
	Domains   []string `json:"domains"`
	IPv4CIDRs []string `json:"ipv4_cidrs,omitempty"`
}

func (r *Routing) validate() error {
	if r == nil {
		return nil
	}
	if (r.Mode != "all" && r.Mode != "include" && r.Mode != "exclude") || len(r.Domains) > 256 || len(r.IPv4CIDRs) > 256 || (r.Mode == "all" && (len(r.Domains) != 0 || len(r.IPv4CIDRs) != 0)) {
		return ErrProfile
	}
	for _, value := range r.IPv4CIDRs {
		prefix, err := netip.ParsePrefix(value)
		if err != nil || !prefix.Addr().Is4() || prefix.Bits() < 8 || prefix.Masked().String() != value || !prefix.Addr().IsGlobalUnicast() || prefix.Addr().IsPrivate() {
			return ErrProfile
		}
		for _, reserved := range []string{"0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.88.99.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/3"} {
			if prefix.Overlaps(netip.MustParsePrefix(reserved)) {
				return ErrProfile
			}
		}
	}
	for _, mask := range r.Domains {
		host := strings.TrimPrefix(mask, "*.")
		parts := strings.Split(host, ".")
		if len(host) > 253 || len(parts) < 2 || !regexp.MustCompile(`[a-z]`).MatchString(parts[len(parts)-1]) {
			return ErrProfile
		}
		for _, label := range parts {
			if !regexp.MustCompile(`^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$`).MatchString(label) {
				return ErrProfile
			}
		}
	}
	return nil
}

func (r *Routing) apply(config map[string]any) {
	if r == nil || r.Mode == "all" {
		return
	}
	type obj = map[string]any
	// Fake addresses retain the domain even for ECH and non-HTTP traffic using
	// system DNS. Mappings live only in this process; upstream answers stay real.
	config["fakedns"] = obj{"ipPool": "198.18.0.0/15", "poolSize": 32768}
	config["dns"] = obj{"tag": "resolver", "queryStrategy": "UseIPv4", "servers": []any{"fakedns", "1.1.1.1"}}
	config["inbounds"].([]any)[0].(obj)["sniffing"] = obj{"enabled": true, "destOverride": []string{"fakedns", "http", "tls", "quic"}, "routeOnly": true}
	config["outbounds"] = append(config["outbounds"].([]any),
		obj{"tag": "direct", "protocol": "freedom", "settings": obj{"domainStrategy": "UseIPv4"}},
		obj{"tag": "dns", "protocol": "dns"})
	// Resolver and our verification/control origin always use the encrypted
	// outbound, before user rules. A direct response cannot verify VPN access.
	rules := []any{
		obj{"type": "field", "inboundTag": []string{"resolver"}, "outboundTag": "vpn"},
		obj{"type": "field", "inboundTag": []string{"tun"}, "port": "53", "outboundTag": "dns"},
		obj{"type": "field", "domain": []string{"full:api.prettylisavpn.com", "domain:ifconfig.me"}, "outboundTag": "vpn"},
		obj{"type": "field", "ip": []string{"::/0"}, "outboundTag": "blocked"},
	}
	selected, fallback := "vpn", "direct"
	if r.Mode == "exclude" {
		selected, fallback = "direct", "vpn"
	}
	domains := make([]string, 0, len(r.Domains))
	for _, mask := range r.Domains {
		if strings.HasPrefix(mask, "*.") {
			// domain: also matches the apex; a wildcard must match subdomains only.
			domains = append(domains, `regexp:^.+\.`+regexp.QuoteMeta(mask[2:])+`$`)
		} else {
			domains = append(domains, "full:"+mask)
		}
	}
	if len(domains) > 0 {
		rules = append(rules, obj{"type": "field", "domain": domains, "outboundTag": selected})
	}
	if len(r.IPv4CIDRs) > 0 {
		rules = append(rules, obj{"type": "field", "ip": r.IPv4CIDRs, "outboundTag": selected})
	}
	// Unknown/stale fake addresses must never escape to the physical network.
	rules = append(rules, obj{"type": "field", "ip": []string{"198.18.0.0/15"}, "outboundTag": "blocked"},
		obj{"type": "field", "inboundTag": []string{"tun"}, "outboundTag": fallback})
	config["routing"] = obj{"domainStrategy": "AsIs", "rules": rules}
}
