// SPDX-License-Identifier: MIT
package node

import (
	"crypto/ecdh"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/base64"
	"encoding/hex"
	"encoding/pem"
	"math/big"
	"strings"
	"time"
)

type Identity struct {
	PrivateKey     string `json:"private_key"`
	PublicKey      string `json:"public_key"`
	ShortID        string `json:"short_id"`
	ServerName     string `json:"server_name"`
	TLSCertificate string `json:"tls_certificate"`
	TLSKey         string `json:"tls_key"`
	CertificatePin string `json:"certificate_pin"`
	Expires        int64  `json:"expires"`
}

func (i Identity) String() string   { return "Identity([redacted])" }
func (i Identity) GoString() string { return i.String() }

// Called once by the privileged node installer. The JSON output is a private
// pipe to its 0600 journal, never returned to the API. Only public pins leave it.
func NewIdentity(serverName string, now time.Time) (Identity, error) {
	if !host.MatchString(serverName) || !strings.Contains(serverName, ".") || strings.Contains(serverName, "..") {
		return Identity{}, ErrConfiguration
	}
	reality, err := ecdh.X25519().GenerateKey(rand.Reader)
	if err != nil {
		return Identity{}, err
	}
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return Identity{}, err
	}
	serial, err := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 120))
	if err != nil {
		return Identity{}, err
	}
	expires := now.Add(365 * 24 * time.Hour)
	root := &x509.Certificate{SerialNumber: serial, Subject: pkix.Name{CommonName: "PrettyLisaVPN node CA"},
		NotBefore: now.Add(-5 * time.Minute), NotAfter: expires, IsCA: true, BasicConstraintsValid: true,
		KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature}
	rootDER, err := x509.CreateCertificate(rand.Reader, root, root, &key.PublicKey, key)
	if err != nil {
		return Identity{}, err
	}
	leaf := &x509.Certificate{SerialNumber: new(big.Int).Add(serial, big.NewInt(1)), DNSNames: []string{serverName},
		NotBefore: root.NotBefore, NotAfter: expires, KeyUsage: x509.KeyUsageDigitalSignature,
		ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}
	leafDER, err := x509.CreateCertificate(rand.Reader, leaf, root, &key.PublicKey, key)
	if err != nil {
		return Identity{}, err
	}
	privateDER, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		return Identity{}, err
	}
	defer clear(privateDER)
	short := make([]byte, 8)
	if _, err := rand.Read(short); err != nil {
		return Identity{}, err
	}
	pin := sha256.Sum256(rootDER)
	return Identity{
		PrivateKey: base64.RawURLEncoding.EncodeToString(reality.Bytes()),
		PublicKey:  base64.RawURLEncoding.EncodeToString(reality.PublicKey().Bytes()),
		ShortID:    hex.EncodeToString(short), ServerName: serverName,
		TLSCertificate: string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: leafDER})) + string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: rootDER})),
		TLSKey:         string(pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: privateDER})),
		CertificatePin: hex.EncodeToString(pin[:]), Expires: expires.Unix(),
	}, nil
}
