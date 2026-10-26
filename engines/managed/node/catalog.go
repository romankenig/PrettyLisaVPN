// SPDX-License-Identifier: MIT
package node

import (
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"strings"
)

// The order and port offsets are a versioned wire contract with the node agent.
// One process owns every listener; revocation closes every candidate together.
const PlanPorts = 20

func derived(secret, purpose string) string {
	sum := sha256.Sum256([]byte("PrettyLisaVPN/plan/v1/" + purpose + "\x00" + secret))
	return base64.StdEncoding.EncodeToString(sum[:])
}

func (l Lease) inbounds() []any {
	type obj = map[string]any
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
