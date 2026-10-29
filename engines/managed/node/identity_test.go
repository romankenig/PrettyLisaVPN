// SPDX-License-Identifier: MIT
package node

import (
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"strings"
	"testing"
	"time"
)

func TestIdentityUsesPrivateNodeKeysAndPinnedValidCertificate(t *testing.T) {
	now := time.Now()
	identity, err := NewIdentity("node.prettylisavpn.internal", now)
	if err != nil {
		t.Fatal(err)
	}
	pair, err := tls.X509KeyPair([]byte(identity.TLSCertificate), []byte(identity.TLSKey))
	if err != nil || len(pair.Certificate) != 2 {
		t.Fatal("invalid chain", err)
	}
	root, _ := x509.ParseCertificate(pair.Certificate[1])
	leaf, _ := x509.ParseCertificate(pair.Certificate[0])
	pool := x509.NewCertPool()
	pool.AddCert(root)
	if _, err := leaf.Verify(x509.VerifyOptions{Roots: pool, DNSName: identity.ServerName, CurrentTime: now}); err != nil {
		t.Fatal(err)
	}
	if _, err := leaf.Verify(x509.VerifyOptions{Roots: pool, DNSName: "other.example.com", CurrentTime: now}); err == nil {
		t.Fatal("wrong server identity accepted")
	}
	for _, value := range []string{identity.PrivateKey, identity.TLSKey} {
		if strings.Contains(fmt.Sprintf("%#v", identity), value) {
			t.Fatal("private key exposed by diagnostics")
		}
	}
}
