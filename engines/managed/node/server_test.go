// SPDX-License-Identifier: MIT
package node

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/xtls/xray-core/core"
)

func fixture() Lease {
	return Lease{ID: "d84cd4d2-8aee-4c17-9772-31db1d512924", Secret: "28d1564f-cb6e-4d0c-b2a6-b6db50b0fca1", Listen: "192.0.2.1", Port: 18443,
		PrivateKey: base64.RawURLEncoding.EncodeToString(append([]byte{1}, make([]byte, 31)...)), ServerName: "vpn.example.com", Target: "192.0.2.2", ShortID: "12345678", Expires: time.Now().Add(time.Minute).Unix()}
}
func TestLeaseUsesPinnedRealityServer(t *testing.T) {
	l := fixture()
	raw, _ := json.Marshal(l)
	p, err := Parse(raw, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	c, err := p.Config()
	if err != nil {
		t.Fatal(err)
	}
	i, err := core.New(c)
	if err != nil {
		t.Fatal("server schema rejected", err)
	}
	defer i.Close()
	if strings.Contains(fmt.Sprintf("%#v", p), l.Secret) {
		t.Fatal("credential exposed")
	}
}
func TestRejectExpiredUnboundedAndUnsafeLeases(t *testing.T) {
	for _, change := range []func(*Lease){func(l *Lease) { l.Expires = time.Now().Unix() }, func(l *Lease) { l.Expires = time.Now().Add(time.Hour).Unix() }, func(l *Lease) { l.Secret = "bad" }, func(l *Lease) { l.PrivateKey = "bad" }, func(l *Lease) { l.Target = "127.0.0.1" }, func(l *Lease) { l.Port = 22 }} {
		l := fixture()
		change(&l)
		raw, _ := json.Marshal(l)
		if _, err := Parse(raw, time.Now()); err == nil {
			t.Fatal("unsafe lease accepted")
		}
	}
}

func TestSelectedMethodExposesOnlyOneListener(t *testing.T) {
	cert, key, _ := certificate(t)
	for method := range methodOffsets {
		l := fixture()
		l.Method = method
		if method != "VLESS_REALITY" {
			l.TLSCertificate, l.TLSKey = cert, key
		}
		raw, _ := json.Marshal(l)
		parsed, err := Parse(raw, time.Now())
		if err != nil {
			t.Fatal(method, err)
		}
		inbounds := parsed.inbounds()
		if len(inbounds) != 1 || inbounds[0].(map[string]any)["port"] != l.Port {
			t.Fatal("unselected listener exposed", method)
		}
		config, err := parsed.Config()
		if err != nil {
			t.Fatal(method, err)
		}
		instance, err := core.New(config)
		if err != nil {
			t.Fatal(method, err)
		}
		_ = instance.Close()
	}
}
