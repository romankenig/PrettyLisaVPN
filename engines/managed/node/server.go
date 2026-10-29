// SPDX-License-Identifier: MIT
// Package node hosts one authorization per process. Killing the process revokes
// existing connections as well as future handshakes; RemoveUser alone cannot.
package node

import (
	"bytes"
	"crypto/tls"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"net/netip"
	"regexp"
	"time"

	_ "github.com/romankenig/PrettyLisaVPN/engines/managed"
	"github.com/romankenig/PrettyLisaVPN/engines/managed/amnezia"
	"github.com/romankenig/PrettyLisaVPN/engines/managed/hysteria1"
	"github.com/romankenig/PrettyLisaVPN/engines/managed/sstp"
	_ "github.com/xtls/xray-core/app/policy"
	_ "github.com/xtls/xray-core/app/stats"
	commonserial "github.com/xtls/xray-core/common/serial"
	"github.com/xtls/xray-core/core"
	"github.com/xtls/xray-core/infra/conf/serial"
	_ "github.com/xtls/xray-core/proxy/freedom"
	_ "github.com/xtls/xray-core/proxy/vless/inbound"
	_ "github.com/xtls/xray-core/proxy/vmess/inbound"
)

var ErrConfiguration = errors.New("INVALID_LEASE")
var uuid = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)
var host = regexp.MustCompile(`^[a-zA-Z0-9][a-zA-Z0-9.-]{0,251}[a-zA-Z0-9]$`)
var short = regexp.MustCompile(`^(?:[0-9a-f]{2}){1,8}$`)

type Lease struct {
	Method         string `json:"method,omitempty"`
	ID             string `json:"id"`
	Secret         string `json:"secret"`
	Listen         string `json:"listen"`
	Port           uint16 `json:"port"`
	PrivateKey     string `json:"private_key"`
	ServerName     string `json:"server_name"`
	Target         string `json:"target"`
	ShortID        string `json:"short_id"`
	Expires        int64  `json:"expires"`
	Plan           bool   `json:"plan,omitempty"`
	TLSCertificate string `json:"tls_certificate,omitempty"`
	TLSKey         string `json:"tls_key,omitempty"`
}

func (l Lease) String() string   { return "Lease([redacted])" }
func (l Lease) GoString() string { return l.String() }

func Parse(raw []byte, now time.Time) (Lease, error) {
	var l Lease
	d := json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	if len(raw) > 65536 || d.Decode(&l) != nil || d.Decode(new(any)) != io.EOF {
		return Lease{}, ErrConfiguration
	}
	key, err := base64.RawURLEncoding.DecodeString(l.PrivateKey)
	ip, e := netip.ParseAddr(l.Listen)
	target, t := netip.ParseAddr(l.Target)
	if !uuid.MatchString(l.ID) || !uuid.MatchString(l.Secret) || l.Port < 1024 ||
		err != nil || len(key) != 32 || bytes.Equal(key, make([]byte, 32)) ||
		e != nil || !ip.Is4() || t != nil || !target.Is4() || !target.IsGlobalUnicast() || target.IsPrivate() ||
		!host.MatchString(l.ServerName) || !short.MatchString(l.ShortID) ||
		l.Expires <= now.Unix() || l.Expires > now.Add(MaxLeaseDuration).Unix() {
		return Lease{}, ErrConfiguration
	}
	if l.Plan {
		if int(l.Port)+PlanPorts-1 > 65535 {
			return Lease{}, ErrConfiguration
		}
		if _, err := tls.X509KeyPair([]byte(l.TLSCertificate), []byte(l.TLSKey)); err != nil {
			return Lease{}, ErrConfiguration
		}
	} else if l.TLSCertificate != "" || l.TLSKey != "" {
		if l.Method == "" || l.Method == "VLESS_REALITY" {
			return Lease{}, ErrConfiguration
		}
	}
	if l.Method != "" {
		if _, ok := methodOffsets[l.Method]; !ok || l.Plan {
			return Lease{}, ErrConfiguration
		}
		if l.Method != "VLESS_REALITY" && l.Method != "SHADOWSOCKS_2022" && l.Method != "AMNEZIA" {
			if _, err := tls.X509KeyPair([]byte(l.TLSCertificate), []byte(l.TLSKey)); err != nil {
				return Lease{}, ErrConfiguration
			}
		}
	}
	return l, nil
}

func (l Lease) Config() (*core.Config, error) {
	type obj = map[string]any
	content, err := json.Marshal(obj{
		"log":       obj{"access": "none", "error": "none", "loglevel": "none", "dnsLog": false},
		"stats":     obj{},
		"policy":    obj{"system": obj{"statsInboundUplink": true, "statsInboundDownlink": true}},
		"inbounds":  l.inbounds(),
		"outbounds": []any{obj{"tag": "internet", "protocol": "freedom", "settings": obj{"domainStrategy": "UseIPv4"}}, obj{"tag": "blocked", "protocol": "blackhole"}},
		"routing": obj{"domainStrategy": "IPIfNonMatch", "rules": []any{obj{"type": "field", "outboundTag": "blocked",
			"ip": []string{"0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/4", "240.0.0.0/4", "::/0"},
		}}},
	})
	if err != nil {
		return nil, ErrConfiguration
	}
	defer clear(content)
	c, err := serial.LoadJSONConfig(bytes.NewReader(content))
	if err != nil {
		return nil, ErrConfiguration
	}
	if l.Method == "AMNEZIA" {
		if amnezia.Wrap(c) != nil {
			return nil, ErrConfiguration
		}
	}
	if l.Method == "HYSTERIA1_TLS" {
		c.App = append(c.App, commonserial.ToTypedMessage(&hysteria1.Config{Server: true, Address: l.Listen, Port: uint32(l.Port), Secret: l.Secret, Certificate: l.TLSCertificate, Key: l.TLSKey}))
	}
	if l.Method == "SSTP" {
		c.App = append(c.App, commonserial.ToTypedMessage(&sstp.Config{Server: true, Address: l.Listen, Port: uint32(l.Port), Secret: l.Secret, Certificate: l.TLSCertificate, Key: l.TLSKey}))
	}
	return c, nil
}
