// SPDX-License-Identifier: MIT
// Package node hosts one authorization per process. Killing the process revokes
// existing connections as well as future handshakes; RemoveUser alone cannot.
package node

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"net/netip"
	"regexp"
	"time"

	_ "github.com/romankenig/PrettyLisaVPN/engines/managed"
	"github.com/xtls/xray-core/core"
	"github.com/xtls/xray-core/infra/conf/serial"
	_ "github.com/xtls/xray-core/proxy/freedom"
	_ "github.com/xtls/xray-core/proxy/vless/inbound"
)

var ErrConfiguration = errors.New("INVALID_LEASE")
var uuid = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)
var host = regexp.MustCompile(`^[a-zA-Z0-9][a-zA-Z0-9.-]{0,251}[a-zA-Z0-9]$`)
var short = regexp.MustCompile(`^(?:[0-9a-f]{2}){1,8}$`)

type Lease struct {
	ID         string `json:"id"`
	Secret     string `json:"secret"`
	Listen     string `json:"listen"`
	Port       uint16 `json:"port"`
	PrivateKey string `json:"private_key"`
	ServerName string `json:"server_name"`
	Target     string `json:"target"`
	ShortID    string `json:"short_id"`
	Expires    int64  `json:"expires"`
}

func (l Lease) String() string   { return "Lease([redacted])" }
func (l Lease) GoString() string { return l.String() }

func Parse(raw []byte, now time.Time) (Lease, error) {
	var l Lease
	d := json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	if len(raw) > 8192 || d.Decode(&l) != nil || d.Decode(new(any)) != io.EOF {
		return Lease{}, ErrConfiguration
	}
	key, err := base64.RawURLEncoding.DecodeString(l.PrivateKey)
	ip, e := netip.ParseAddr(l.Listen)
	target, t := netip.ParseAddr(l.Target)
	if !uuid.MatchString(l.ID) || !uuid.MatchString(l.Secret) || l.Port < 1024 ||
		err != nil || len(key) != 32 || bytes.Equal(key, make([]byte, 32)) ||
		e != nil || !ip.Is4() || t != nil || !target.Is4() || !target.IsGlobalUnicast() || target.IsPrivate() ||
		!host.MatchString(l.ServerName) || !short.MatchString(l.ShortID) ||
		l.Expires <= now.Unix() || l.Expires > now.Add(20*time.Minute).Unix() {
		return Lease{}, ErrConfiguration
	}
	return l, nil
}

func (l Lease) Config() (*core.Config, error) {
	type obj = map[string]any
	content, err := json.Marshal(obj{
		"log": obj{"access": "none", "error": "none", "loglevel": "none", "dnsLog": false},
		"inbounds": []any{obj{"tag": "authorized", "listen": l.Listen, "port": l.Port, "protocol": "vless",
			"settings": obj{"decryption": "none", "clients": []any{obj{"id": l.Secret, "flow": "xtls-rprx-vision"}}},
			"streamSettings": obj{"network": "raw", "security": "reality", "realitySettings": obj{
				"show": false, "target": l.Target + ":443", "serverNames": []string{l.ServerName},
				"privateKey": l.PrivateKey, "shortIds": []string{l.ShortID},
			}},
		}},
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
	return c, nil
}
