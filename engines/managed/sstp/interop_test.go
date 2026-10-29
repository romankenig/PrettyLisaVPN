// SPDX-License-Identifier: MIT
package sstp

import (
	"context"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"os"
	"testing"
	"time"
)

// The reference server runs in a disposable container, with no host TUN, routes
// or published ports. Its ephemeral test credential is read from a private file.
func TestOfficialSoftEtherSSTP(t *testing.T) {
	path := os.Getenv("PL_SSTP_REFERENCE")
	if path == "" {
		t.Skip("official SoftEther reference not supplied")
	}
	var config struct{ Address, Secret, Name, Pin string }
	raw, err := os.ReadFile(path)
	if err != nil || json.Unmarshal(raw, &config) != nil {
		t.Fatal("reference configuration unavailable")
	}
	clear(raw)
	ctx, cancel := context.WithTimeout(context.Background(), 35*time.Second)
	defer cancel()
	session, err := Dial(ctx, config.Address, config.Secret, config.Name, config.Pin, (&net.Dialer{}).DialContext)
	if err != nil {
		t.Fatal("reference handshake failed")
	}
	network, err := NewNetwork(session, nil, nil)
	if err != nil {
		t.Fatal("reference network unavailable")
	}
	defer network.Close()
	transport := &http.Transport{Proxy: nil, DialContext: network.DialContext, DisableKeepAlives: true}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: 10 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	request, _ := http.NewRequestWithContext(ctx, http.MethodGet, "https://api.prettylisavpn.com/health", nil)
	response, err := client.Do(request)
	if err != nil {
		t.Fatal("reference tunneled DNS/HTTPS failed")
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, 1025))
	var status struct{ Status string }
	if err != nil || response.StatusCode != 200 || len(body) > 1024 || json.Unmarshal(body, &status) != nil || status.Status != "ok" {
		t.Fatal("reference HTTPS response invalid")
	}
}
