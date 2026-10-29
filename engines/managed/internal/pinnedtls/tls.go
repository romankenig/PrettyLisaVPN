// SPDX-License-Identifier: MIT
package pinnedtls

import (
	"crypto/sha256"
	"crypto/subtle"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"errors"
)

var ErrCertificate = errors.New("TLS_CERTIFICATE_INVALID")

// The configured pin replaces trust roots, never hostname, expiry or chain checks.
func Config(name, pin string) (*tls.Config, error) {
	c := &tls.Config{ServerName: name, MinVersion: tls.VersionTLS12}
	expected, err := hex.DecodeString(pin)
	if name == "" || err != nil || len(expected) != sha256.Size {
		return nil, ErrCertificate
	}
	c.InsecureSkipVerify = true // Mandatory full chain verification with the pinned root below.
	c.VerifyConnection = func(state tls.ConnectionState) error {
		if len(state.PeerCertificates) == 0 {
			return ErrCertificate
		}
		roots, intermediates := x509.NewCertPool(), x509.NewCertPool()
		found := false
		for _, cert := range state.PeerCertificates {
			sum := sha256.Sum256(cert.Raw)
			if subtle.ConstantTimeCompare(sum[:], expected) == 1 {
				roots.AddCert(cert)
				found = true
			} else {
				intermediates.AddCert(cert)
			}
		}
		if !found {
			return ErrCertificate
		}
		_, err := state.PeerCertificates[0].Verify(x509.VerifyOptions{DNSName: name, Roots: roots, Intermediates: intermediates})
		return err
	}
	return c, nil
}
