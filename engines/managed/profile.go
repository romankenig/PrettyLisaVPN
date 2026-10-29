// SPDX-License-Identifier: MIT
package managed

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/netip"
	"regexp"
	"strconv"
	"strings"

	"github.com/romankenig/PrettyLisaVPN/engines/managed/amnezia"
	"github.com/romankenig/PrettyLisaVPN/engines/managed/hysteria1"
	"github.com/romankenig/PrettyLisaVPN/engines/managed/softether"
	"github.com/romankenig/PrettyLisaVPN/engines/managed/sstp"
	"github.com/xtls/xray-core/common/serial"
	"github.com/xtls/xray-core/core"
)

const Version = "0.3.0"
const CoreVersion = "26.10.21"
const MaxProfileBytes = 64 * 1024

var ErrProfile = errors.New("UNSUPPORTED_CONFIGURATION")

// Profile is a private payload from the authorized client, never an arbitrary
// Xray config. No file paths, scripts, log options, custom routes or insecure TLS.
type Profile struct {
	Version        int    `json:"version"`
	Session        string `json:"session"`
	Country        string `json:"country"`
	Method         string `json:"method"`
	Server         string `json:"server"`
	Port           uint16 `json:"port"`
	Secret         string `json:"secret"`
	ServerName     string `json:"server_name,omitempty"`
	PublicKey      string `json:"public_key,omitempty"`
	ShortID        string `json:"short_id,omitempty"`
	ObfsSecret     string `json:"obfs_secret,omitempty"`
	Transport      string `json:"transport,omitempty"`
	Path           string `json:"path,omitempty"`
	Address        string `json:"address,omitempty"`
	CertificatePin string `json:"certificate_pin,omitempty"`
}

func (p Profile) String() string   { return "Profile([redacted])" }
func (p Profile) GoString() string { return p.String() }

var uuid = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)
var hostname = regexp.MustCompile(`^[a-zA-Z0-9](?:[a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?$`)
var shortID = regexp.MustCompile(`^(?:[0-9a-f]{2}){1,8}$`)
var serviceName = regexp.MustCompile(`^[a-zA-Z0-9_-]{1,64}$`)

func ParseProfile(content string) (Profile, error) {
	var p Profile
	if len(content) == 0 || len(content) > MaxProfileBytes {
		return p, ErrProfile
	}
	d := json.NewDecoder(strings.NewReader(content))
	d.DisallowUnknownFields()
	if d.Decode(&p) != nil || d.Decode(new(any)) != io.EOF || p.Validate() != nil {
		return Profile{}, ErrProfile
	}
	return p, nil
}
func key32(value string, raw bool) bool {
	encoding := base64.StdEncoding
	if raw {
		encoding = base64.RawURLEncoding
	}
	b, err := encoding.DecodeString(value)
	return err == nil && len(b) == 32 && !bytes.Equal(b, make([]byte, 32))
}
func (p Profile) Validate() error {
	ip, err := netip.ParseAddr(p.Server)
	if p.Version != 1 || !uuid.MatchString(p.Session) || !regexp.MustCompile(`^[A-Z]{2}$`).MatchString(p.Country) || err != nil || !ip.Is4() || !ip.IsGlobalUnicast() || ip.IsPrivate() || p.Port == 0 {
		return ErrProfile
	}
	if len(p.Secret) == 0 || len(p.Secret) > 4096 || strings.ContainsAny(p.Secret, "\x00\r\n") {
		return ErrProfile
	}
	tlsRequired := false
	switch p.Method {
	case "WIREGUARD", "AMNEZIA":
		prefix, e := netip.ParsePrefix(p.Address)
		if e != nil || !prefix.Addr().Is4() || prefix.Bits() != 32 || !key32(p.Secret, false) || !key32(p.PublicKey, false) {
			return ErrProfile
		}
	case "VLESS_TLS", "VLESS_REALITY", "VMESS_TLS":
		if !uuid.MatchString(p.Secret) {
			return ErrProfile
		}
		tlsRequired = true
		if p.Method == "VLESS_REALITY" && (!key32(p.PublicKey, true) || !shortID.MatchString(p.ShortID) || p.Transport != "") {
			return ErrProfile
		}
	case "TROJAN_TLS", "HYSTERIA1_TLS", "HYSTERIA2_TLS", "HYSTERIA2_SALAMANDER", "SSTP", "SOFTETHER":
		tlsRequired = true
		if len(p.Secret) < 16 {
			return ErrProfile
		}
		if (p.Method == "HYSTERIA1_TLS" || p.Method == "SSTP" || p.Method == "SOFTETHER") && len(p.Secret) > 128 {
			return ErrProfile
		}
		if p.Method == "HYSTERIA2_SALAMANDER" && (len(p.ObfsSecret) < 16 || len(p.ObfsSecret) > 128 || strings.ContainsAny(p.ObfsSecret, "\x00\r\n")) {
			return ErrProfile
		}
	case "SHADOWSOCKS":
		if len(p.Secret) < 16 {
			return ErrProfile
		}
	case "SHADOWSOCKS_2022":
		parts := strings.Split(p.Secret, ":")
		if len(parts) != 2 || !key32(parts[0], false) || !key32(parts[1], false) {
			return ErrProfile
		}
	default:
		return ErrProfile
	}
	if tlsRequired && (!hostname.MatchString(p.ServerName) || !strings.Contains(p.ServerName, ".") || strings.Contains(p.ServerName, "..")) {
		return ErrProfile
	}
	if p.Method != "WIREGUARD" && p.Method != "AMNEZIA" && p.Address != "" {
		return ErrProfile
	}
	if p.Method != "WIREGUARD" && p.Method != "AMNEZIA" && p.Method != "VLESS_REALITY" && p.PublicKey != "" {
		return ErrProfile
	}
	if p.Method != "VLESS_REALITY" && p.ShortID != "" {
		return ErrProfile
	}
	if p.Method != "HYSTERIA2_SALAMANDER" && p.ObfsSecret != "" {
		return ErrProfile
	}
	if !tlsRequired && p.ServerName != "" {
		return ErrProfile
	}
	if p.CertificatePin != "" && (!tlsRequired || p.Method == "VLESS_REALITY" || !regexp.MustCompile(`^[0-9a-f]{64}$`).MatchString(p.CertificatePin)) {
		return ErrProfile
	}
	if (p.Method == "SSTP" || p.Method == "SOFTETHER") && p.CertificatePin == "" {
		return ErrProfile
	}
	if p.Transport == "" {
		if p.Path != "" {
			return ErrProfile
		}
		return nil
	}
	if p.Method != "VLESS_TLS" && p.Method != "VMESS_TLS" && p.Method != "TROJAN_TLS" {
		return ErrProfile
	}
	switch p.Transport {
	case "ws", "httpupgrade", "grpc", "xhttp":
	default:
		return ErrProfile
	}
	if len(p.Path) > 128 || strings.ContainsAny(p.Path, "\r\n\x00?#") {
		return ErrProfile
	}
	if p.Transport == "grpc" {
		if !serviceName.MatchString(p.Path) {
			return ErrProfile
		}
	} else if !strings.HasPrefix(p.Path, "/") {
		return ErrProfile
	}
	return nil
}

// CoreConfig uses only IP uplinks: resolving TLS SNI outside the tunnel is never
// necessary. All application DNS packets follow the same encrypted outbound.
func (p Profile) CoreConfig(mobile bool) ([]byte, error) {
	if p.Validate() != nil {
		return nil, ErrProfile
	}
	type obj = map[string]any
	settings := obj{"address": p.Server, "port": p.Port}
	out := obj{"tag": "vpn", "settings": settings}
	stream := obj{"network": "raw", "security": "tls", "tlsSettings": obj{"serverName": p.ServerName, "minVersion": "1.2", "allowInsecure": false, "fingerprint": "chrome"}}
	if p.CertificatePin != "" {
		stream["tlsSettings"].(obj)["pinnedPeerCertSha256"] = p.CertificatePin
	}
	switch p.Method {
	case "HYSTERIA1_TLS", "SSTP", "SOFTETHER":
		// The private typed factory is applied by Configure after JSON parsing.
		// Until then this outbound is closed, never an unencrypted fallback.
		out["protocol"], out["settings"] = "blackhole", obj{}
	case "WIREGUARD", "AMNEZIA":
		out["protocol"] = "wireguard"
		out["settings"] = obj{"secretKey": p.Secret, "address": []string{p.Address}, "mtu": 1280, "noKernelTun": true, "peers": []any{obj{"publicKey": p.PublicKey, "endpoint": net.JoinHostPort(p.Server, strconv.Itoa(int(p.Port))), "keepAlive": 25, "allowedIPs": []string{"0.0.0.0/0"}}}}
	case "VLESS_TLS", "VLESS_REALITY":
		out["protocol"] = "vless"
		settings["id"] = p.Secret
		settings["encryption"] = "none"
		if p.Method == "VLESS_REALITY" {
			settings["flow"] = "xtls-rprx-vision"
			delete(stream, "tlsSettings")
			stream["security"] = "reality"
			stream["realitySettings"] = obj{"serverName": p.ServerName, "fingerprint": "chrome", "publicKey": p.PublicKey, "shortId": p.ShortID}
		}
		out["streamSettings"] = stream
	case "VMESS_TLS":
		out["protocol"] = "vmess"
		settings["id"] = p.Secret
		settings["security"] = "auto"
		out["streamSettings"] = stream
	case "TROJAN_TLS":
		out["protocol"] = "trojan"
		settings["password"] = p.Secret
		out["streamSettings"] = stream
	case "SHADOWSOCKS", "SHADOWSOCKS_2022":
		out["protocol"] = "shadowsocks"
		settings["password"] = p.Secret
		settings["method"] = "chacha20-ietf-poly1305"
		if p.Method == "SHADOWSOCKS_2022" {
			settings["method"] = "2022-blake3-aes-256-gcm"
		}
	case "HYSTERIA2_TLS", "HYSTERIA2_SALAMANDER":
		out["protocol"] = "hysteria"
		settings["version"] = 2
		stream["network"] = "hysteria"
		stream["hysteriaSettings"] = obj{"version": 2, "auth": p.Secret}
		if p.Method == "HYSTERIA2_SALAMANDER" {
			stream["finalmask"] = obj{"udp": []any{obj{"type": "salamander", "settings": obj{"password": p.ObfsSecret}}}}
		}
		out["streamSettings"] = stream
	}
	if p.Transport != "" {
		stream["network"] = p.Transport
		switch p.Transport {
		case "grpc":
			stream["grpcSettings"] = obj{"serviceName": p.Path}
		case "ws":
			stream["wsSettings"] = obj{"path": p.Path, "host": p.ServerName}
		case "httpupgrade":
			stream["httpupgradeSettings"] = obj{"path": p.Path, "host": p.ServerName}
		case "xhttp":
			stream["xhttpSettings"] = obj{"path": p.Path, "host": p.ServerName, "mode": "auto"}
		}
	}
	tun := obj{"name": "PrettyLisaVPNEngine", "mtu": 1280}
	if !mobile {
		tun["gateway"] = []string{"172.30.255.1/30", "fd7a:115c:a1e0::1/126"}
		tun["dns"] = []string{"1.1.1.1"}
		tun["autoSystemRoutingTable"] = []string{"0.0.0.0/0", "::/0"}
		tun["autoSystemWfpBlockLeak"] = []string{"dns", "misconfigtun"}
	}
	config := obj{
		"log":       obj{"access": "none", "error": "none", "loglevel": "none", "dnsLog": false},
		"inbounds":  []any{obj{"tag": "tun", "protocol": "tun", "settings": tun}},
		"outbounds": []any{out, obj{"tag": "blocked", "protocol": "blackhole"}},
		"routing":   obj{"domainStrategy": "AsIs", "rules": []any{obj{"type": "field", "ip": []string{"::/0"}, "outboundTag": "blocked"}, obj{"type": "field", "inboundTag": []string{"tun"}, "outboundTag": "vpn"}}},
	}
	return json.Marshal(config)
}

func (p Profile) Configure(config *core.Config) error {
	if p.Method == "AMNEZIA" {
		return amnezia.Wrap(config)
	}
	if p.Method == "HYSTERIA1_TLS" || p.Method == "SSTP" || p.Method == "SOFTETHER" {
		for _, out := range config.Outbound {
			if out.Tag == "vpn" {
				out.ProxySettings = serial.ToTypedMessage(&hysteria1.Config{Address: p.Server, Port: uint32(p.Port), Secret: p.Secret, ServerName: p.ServerName, CertificatePin: p.CertificatePin})
				if p.Method == "SSTP" {
					out.ProxySettings = serial.ToTypedMessage(&sstp.Config{Address: p.Server, Port: uint32(p.Port), Secret: p.Secret, ServerName: p.ServerName, CertificatePin: p.CertificatePin})
				}
				if p.Method == "SOFTETHER" {
					out.ProxySettings = serial.ToTypedMessage(&softether.Config{Address: p.Server, Port: uint32(p.Port), Secret: p.Secret, ServerName: p.ServerName, CertificatePin: p.CertificatePin})
				}
				return nil
			}
		}
		return ErrProfile
	}
	return nil
}
