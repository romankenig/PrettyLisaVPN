// SPDX-License-Identifier: MIT
package node

import (
	"crypto/ecdh"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"strings"
)

// The order and port offsets are a versioned wire contract with the node agent.
// One process owns every listener; revocation closes every candidate together.
const PlanPorts = 20

// A current lease exposes exactly one selected encrypted protocol.
var methodOffsets = map[string]int{
	"AMNEZIA":       -1,
	"HYSTERIA1_TLS": -2,
	"VLESS_REALITY": 0, "VLESS_TLS": 1, "VMESS_TLS": 6,
	"SHADOWSOCKS_2022": 17, "HYSTERIA2_TLS": 18, "HYSTERIA2_SALAMANDER": 19,
}

func derived(secret, purpose string) string {
	sum := sha256.Sum256([]byte("PrettyLisaVPN/plan/v1/" + purpose + "\x00" + secret))
	return base64.StdEncoding.EncodeToString(sum[:])
}

func (l Lease) inbounds() []any {
	type obj = map[string]any
	if l.Method == "HYSTERIA1_TLS" {
		return nil
	}
	if l.Method == "AMNEZIA" {
		raw, _ := base64.StdEncoding.DecodeString(derived(l.Secret, "amnezia-key"))
		private, _ := ecdh.X25519().NewPrivateKey(raw)
		clear(raw)
		return []any{obj{"tag": "authorized", "listen": l.Listen, "port": l.Port, "protocol": "wireguard",
			"settings": obj{"secretKey": l.PrivateKey, "address": []string{"172.30.253.1/24"}, "mtu": 1280,
				"peers": []any{obj{"publicKey": base64.StdEncoding.EncodeToString(private.PublicKey().Bytes()), "allowedIPs": []string{"172.30.253.2/32"}}}}}}
	}
	if l.Method != "" {
		legacy := l
		legacy.Method, legacy.Plan = "", true
		// Build the pinned core configuration, then expose only this lease's method.
		inbound := legacy.inbounds()[methodOffsets[l.Method]].(map[string]any)
		inbound["port"], inbound["tag"] = l.Port, "authorized"
		return []any{inbound}
	}
	reality := obj{"tag": "authorized", "listen": l.Listen, "port": l.Port, "protocol": "vless",
		"settings": obj{"decryption": "none", "clients": []any{obj{"id": l.Secret, "flow": "xtls-rprx-vision"}}},
		"streamSettings": obj{"network": "raw", "security": "reality", "realitySettings": obj{
			"show": false, "target": l.Target + ":443", "serverNames": []string{l.ServerName},
			"privateKey": l.PrivateKey, "shortIds": []string{l.ShortID},
		}},
	}
	result := []any{reality}
	if !l.Plan {
		return result
	}
	add := func(protocol string, settings, stream obj) {
		inbound := obj{"tag": fmt.Sprintf("authorized-%d", len(result)), "listen": l.Listen, "port": int(l.Port) + len(result), "protocol": protocol, "settings": settings}
		if stream != nil {
			inbound["streamSettings"] = stream
		}
		result = append(result, inbound)
	}
	tlsStream := func(network string) obj {
		return obj{"network": network, "security": "tls", "tlsSettings": obj{
			"minVersion": "1.2", "certificates": []any{obj{"certificate": strings.Split(l.TLSCertificate, "\n"), "key": strings.Split(l.TLSKey, "\n")}},
		}}
	}
	for _, protocol := range []string{"vless", "vmess", "trojan"} {
		for _, transport := range []string{"raw", "ws", "grpc", "httpupgrade", "xhttp"} {
			settings := obj{"clients": []any{obj{"id": l.Secret}}}
			if protocol == "vless" {
				settings["decryption"] = "none"
			}
			if protocol == "trojan" {
				settings["clients"] = []any{obj{"password": l.Secret}}
			}
			stream := tlsStream(transport)
			switch transport {
			case "ws":
				stream["wsSettings"] = obj{"path": "/plvpn"}
			case "grpc":
				stream["grpcSettings"] = obj{"serviceName": "plvpn"}
			case "httpupgrade":
				stream["httpupgradeSettings"] = obj{"path": "/plvpn"}
			case "xhttp":
				stream["xhttpSettings"] = obj{"path": "/plvpn", "mode": "auto"}
			}
			add(protocol, settings, stream)
		}
	}
	add("shadowsocks", obj{"method": "chacha20-ietf-poly1305", "password": l.Secret, "network": "tcp,udp"}, nil)
	add("shadowsocks", obj{"method": "2022-blake3-aes-256-gcm", "password": derived(l.Secret, "ss-server"), "clients": []any{obj{"password": derived(l.Secret, "ss-user")}}, "network": "tcp,udp"}, nil)
	for _, obfuscated := range []bool{false, true} {
		stream := tlsStream("hysteria")
		stream["hysteriaSettings"] = obj{"version": 2}
		if obfuscated {
			stream["finalmask"] = obj{"udp": []any{obj{"type": "salamander", "settings": obj{"password": derived(l.Secret, "salamander")}}}}
		}
		add("hysteria", obj{"version": 2, "clients": []any{obj{"auth": l.Secret}}}, stream)
	}
	return result
}
