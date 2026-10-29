// SPDX-License-Identifier: MIT
package node

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"io"
	"math"
	"net"
	"net/http"
	"net/netip"
	"strings"
	"time"

	"github.com/miekg/dns"
	managed "github.com/romankenig/PrettyLisaVPN/engines/managed"
	xnet "github.com/xtls/xray-core/common/net"
	"github.com/xtls/xray-core/core"
	"github.com/xtls/xray-core/infra/conf/serial"
)

type ProbeInput struct {
	Profile      json.RawMessage `json:"profile"`
	MeasureHost  string          `json:"measure_host"`
	MeasureCA    string          `json:"measure_ca"`
	MeasureToken string          `json:"measure_token"`
	Expected     []string        `json:"expected_egress_ips"`
}

type ProbeResult struct {
	Status       string    `json:"status"`
	Mode         string    `json:"mode"`
	Code         string    `json:"code"`
	ObservedAt   time.Time `json:"observed_at"`
	Handshake    bool      `json:"handshake_ok"`
	DNS          bool      `json:"dns_ok"`
	HTTPS        bool      `json:"https_ok"`
	Egress       bool      `json:"egress_ok"`
	ConnectionMS *float64  `json:"connection_ms,omitempty"`
	Download     *float64  `json:"download_mbps,omitempty"`
	Upload       *float64  `json:"upload_mbps,omitempty"`
	Cleanup      bool      `json:"cleanup_confirmed"`
}

// Only fixed owned health/measurement endpoints are used. The process creates
// no TUN or host routes: every DNS and HTTP socket is dialed by the encrypted core.
func Probe(raw []byte) ProbeResult {
	result := ProbeResult{Status: "FAILED", Mode: "SYNTHETIC", Code: "PROBE_CONFIGURATION_INVALID", ObservedAt: time.Now().UTC(), Cleanup: true}
	var input ProbeInput
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if len(raw) > 131072 || decoder.Decode(&input) != nil || decoder.Decode(new(any)) != io.EOF {
		return result
	}
	host, err := netip.ParseAddr(input.MeasureHost)
	if err != nil || !host.Is4() || !host.IsGlobalUnicast() || host.IsPrivate() || len(input.Expected) == 0 || len(input.Expected) > 4 || len(input.MeasureToken) < 32 || len(input.MeasureToken) > 256 {
		return result
	}
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM([]byte(input.MeasureCA)) {
		return result
	}
	p, err := managed.ParseProfile(string(input.Profile))
	if err != nil {
		return result
	}
	config, err := p.CoreConfig(true)
	if err != nil {
		return result
	}
	var settings map[string]any
	if json.Unmarshal(config, &settings) != nil {
		return result
	}
	clear(config)
	delete(settings, "inbounds")
	config, err = json.Marshal(settings)
	if err != nil {
		return result
	}
	parsed, err := serial.LoadJSONConfig(bytes.NewReader(config))
	clear(config)
	if err != nil {
		return result
	}
	instance, err := core.New(parsed)
	if err != nil {
		return result
	}
	defer instance.Close()
	if instance.Start() != nil {
		result.Code = "ENGINE_START_FAILED"
		return result
	}
	ctx, cancel := context.WithTimeout(context.Background(), 75*time.Second)
	defer cancel()
	dial := func(ctx context.Context, network, address string) (net.Conn, error) {
		destination, err := xnet.ParseDestination(network + ":" + address)
		if err != nil {
			return nil, errors.New("INVALID_DESTINATION")
		}
		return core.Dial(ctx, instance, destination)
	}
	transport := &http.Transport{Proxy: nil, DisableKeepAlives: true, TLSClientConfig: &tls.Config{RootCAs: pool, MinVersion: tls.VersionTLS12}, DialContext: dial}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: 10 * time.Second, CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }}
	const size = 8 * 1024 * 1024
	measure := func(path string, upload bool) ([]byte, time.Duration, error) {
		method := "GET"
		var body io.Reader
		if upload {
			method, body = "POST", strings.NewReader(strings.Repeat("x", size))
		}
		request, err := http.NewRequestWithContext(ctx, method, "https://"+input.MeasureHost+":8443"+path, body)
		if err != nil {
			return nil, 0, err
		}
		request.Header.Set("Authorization", "Bearer "+input.MeasureToken)
		started := time.Now()
		response, err := client.Do(request)
		if err != nil {
			return nil, 0, err
		}
		defer response.Body.Close()
		if response.StatusCode != 200 {
			return nil, 0, errors.New("MEASUREMENT_FAILED")
		}
		bodyBytes, err := io.ReadAll(io.LimitReader(response.Body, size+1))
		if err != nil || len(bodyBytes) > size {
			return nil, 0, errors.New("MEASUREMENT_FAILED")
		}
		return bodyBytes, time.Since(started), nil
	}
	data, elapsed, err := measure("/ip", false)
	if err != nil {
		result.Code = "HANDSHAKE_FAILED"
		return result
	}
	result.Handshake = true
	millis := float64(elapsed.Microseconds()) / 1000
	result.ConnectionMS = &millis
	var egress struct {
		IP string `json:"ip"`
	}
	if json.Unmarshal(data, &egress) != nil {
		result.Code = "EGRESS_IP_MISMATCH"
		return result
	}
	for _, expected := range input.Expected {
		if expected == egress.IP {
			result.Egress = true
		}
	}
	if !result.Egress {
		result.Code = "EGRESS_IP_MISMATCH"
		return result
	}
	dnsContext, dnsCancel := context.WithTimeout(ctx, 8*time.Second)
	addresses, err := probeDNS(dnsContext, dial)
	dnsCancel()
	if err != nil || len(addresses) == 0 {
		result.Code = "DNS_FAILED"
		return result
	}
	result.DNS = true
	healthTransport := &http.Transport{Proxy: nil, DisableKeepAlives: true, DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
		return dial(ctx, "tcp", net.JoinHostPort(addresses[0].String(), "443"))
	}}
	defer healthTransport.CloseIdleConnections()
	health := &http.Client{Transport: healthTransport, Timeout: 10 * time.Second, CheckRedirect: client.CheckRedirect}
	request, _ := http.NewRequestWithContext(ctx, "GET", "https://api.prettylisavpn.com/health", nil)
	response, err := health.Do(request)
	if err != nil {
		result.Code = "HTTPS_FAILED"
		return result
	}
	data, err = io.ReadAll(io.LimitReader(response.Body, 1025))
	_ = response.Body.Close()
	var status struct {
		Status string `json:"status"`
	}
	if err != nil || response.StatusCode != 200 || len(data) > 1024 || json.Unmarshal(data, &status) != nil || status.Status != "ok" {
		result.Code = "HTTPS_FAILED"
		return result
	}
	result.HTTPS = true
	data, elapsed, err = measure("/download", false)
	if err == nil && len(data) == size {
		speed := size * 8 / math.Max(elapsed.Seconds(), 0.001) / 1000000
		result.Download = &speed
	}
	data, elapsed, err = measure("/upload", true)
	if err == nil {
		var count struct {
			Received int `json:"received"`
		}
		if json.Unmarshal(data, &count) == nil && count.Received == size {
			speed := float64(count.Received) * 8 / math.Max(elapsed.Seconds(), 0.001) / 1000000
			result.Upload = &speed
		}
	}
	result.Status, result.Code = "HEALTHY", "MANAGED_CHECK_PASSED"
	return result
}

// A core UDP connection does not implement net.PacketConn. net.Resolver would
// treat it as a DNS-over-TCP stream and add an invalid length prefix to UDP.
func probeDNS(ctx context.Context, dial func(context.Context, string, string) (net.Conn, error)) ([]net.IP, error) {
	connection, err := dial(ctx, "udp", "1.1.1.1:53")
	if err != nil {
		return nil, err
	}
	defer connection.Close()
	done := make(chan struct{})
	defer close(done)
	go func() {
		select {
		case <-ctx.Done():
			_ = connection.Close()
		case <-done:
		}
	}()
	query := new(dns.Msg)
	query.SetQuestion("api.prettylisavpn.com.", dns.TypeA)
	packet, err := query.Pack()
	if err != nil {
		return nil, err
	}
	if _, err := connection.Write(packet); err != nil {
		return nil, err
	}
	buffer := make([]byte, 4096)
	n, err := connection.Read(buffer)
	if err != nil {
		return nil, err
	}
	answer := new(dns.Msg)
	if answer.Unpack(buffer[:n]) != nil || answer.Id != query.Id || !answer.Response || answer.Truncated || answer.Rcode != dns.RcodeSuccess {
		return nil, errors.New("DNS_FAILED")
	}
	var addresses []net.IP
	for _, value := range answer.Answer {
		if record, ok := value.(*dns.A); ok {
			addresses = append(addresses, record.A)
		}
	}
	if len(addresses) == 0 {
		return nil, errors.New("DNS_FAILED")
	}
	return addresses, nil
}
