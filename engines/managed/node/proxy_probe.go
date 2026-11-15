// SPDX-License-Identifier: MIT
package node

import (
	"bufio"
	"bytes"
	"context"
	"crypto/tls"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"strconv"
	"strings"
	"time"
)

type probeDialFunc func(context.Context, string, string) (net.Conn, error)

type proxyProbeProfile struct {
	Method   string `json:"method"`
	Server   string `json:"server"`
	Port     int    `json:"port"`
	Username string `json:"username"`
	Secret   string `json:"secret"`
}

func parseProxyProbe(raw []byte) (proxyProbeProfile, error) {
	var p proxyProbeProfile
	d := json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	if d.Decode(&p) != nil || d.Decode(new(any)) != io.EOF || p.Method != "HTTPS_PROXY" || p.Port < 49900 || p.Port > 49999 || len(p.Server) == 0 || len(p.Server) > 253 || len(p.Username) != 36 || len(p.Secret) != 36 || strings.ContainsAny(p.Server, "/:@ \r\n") || strings.ContainsAny(p.Username+p.Secret, "\r\n:") {
		return p, errors.New("PROXY_CONFIGURATION_INVALID")
	}
	return p, nil
}

// Proxy credentials only enter a publicly trusted TLS connection. The exit's
// existing CONNECT implementation resolves and pins public destination addresses.
func proxyProbeDial(p proxyProbeProfile) probeDialFunc {
	return func(ctx context.Context, network, address string) (net.Conn, error) {
		host, port, err := net.SplitHostPort(address)
		if err != nil || network != "tcp" || (port != "443" && port != "8443") || strings.ContainsAny(host, "\r\n/@ ") {
			return nil, errors.New("PROXY_DESTINATION_INVALID")
		}
		ips, err := net.DefaultResolver.LookupIP(ctx, "ip4", p.Server)
		if err != nil || len(ips) == 0 {
			return nil, errors.New("PROXY_DNS_FAILED")
		}
		for _, ip := range ips {
			if !publicServiceIP(ip) {
				return nil, errors.New("PROXY_NONPUBLIC_HOST")
			}
		}
		dialer := tls.Dialer{NetDialer: &net.Dialer{Timeout: 10 * time.Second}, Config: &tls.Config{ServerName: p.Server, MinVersion: tls.VersionTLS12}}
		conn, err := dialer.DialContext(ctx, "tcp", net.JoinHostPort(ips[0].String(), strconv.Itoa(p.Port)))
		if err != nil {
			return nil, errors.New("PROXY_TLS_FAILED")
		}
		deadline := time.Now().Add(10 * time.Second)
		if limit, ok := ctx.Deadline(); ok && limit.Before(deadline) {
			deadline = limit
		}
		_ = conn.SetDeadline(deadline)
		if err = connectProxy(conn, address, p.Username, p.Secret); err != nil {
			conn.Close()
			return nil, err
		}
		_ = conn.SetDeadline(time.Time{})
		return conn, nil
	}
}

func connectProxy(conn net.Conn, address, username, secret string) error {
	auth := base64.StdEncoding.EncodeToString([]byte(username + ":" + secret))
	if _, err := io.WriteString(conn, "CONNECT "+address+" HTTP/1.1\r\nHost: "+address+"\r\nProxy-Authorization: Basic "+auth+"\r\n\r\n"); err != nil {
		return errors.New("PROXY_CONNECT_FAILED")
	}
	reader := bufio.NewReader(io.LimitReader(conn, 16384))
	response, err := http.ReadResponse(reader, &http.Request{Method: "CONNECT"})
	if err != nil || response.StatusCode != 200 || reader.Buffered() != 0 {
		return errors.New("PROXY_CONNECT_FAILED")
	}
	return nil
}
