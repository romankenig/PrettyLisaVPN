// SPDX-License-Identifier: MIT
package node

import (
	"context"
	"errors"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

func allowedServiceURL(raw string, domains []string) bool {
	u, err := url.Parse(raw)
	if err != nil || len(raw) > 2048 || u.Scheme != "https" || u.User != nil || u.Fragment != "" || (u.Port() != "" && u.Port() != "443") {
		return false
	}
	host := strings.ToLower(u.Hostname())
	for _, domain := range domains {
		root := strings.TrimPrefix(domain, "*.")
		if host == root || (strings.HasPrefix(domain, "*.") && strings.HasSuffix(host, "."+root)) {
			return true
		}
	}
	return false
}

// Both DNS and HTTPS traverse the selected VPN core. Public addresses are pinned
// for each request; redirects cannot escape the catalog service or reach a LAN.
func probeService(ctx context.Context, dial func(context.Context, string, string) (net.Conn, error), raw string, domains []string) bool {
	return probeServiceRequest(ctx, dial, raw, domains, false)
}

func probeServiceRequest(ctx context.Context, dial func(context.Context, string, string) (net.Conn, error), raw string, domains []string, remoteDNS bool) bool {
	if !allowedServiceURL(raw, domains) {
		return false
	}
	transport := &http.Transport{Proxy: nil, DisableKeepAlives: true, DialContext: func(ctx context.Context, network, address string) (net.Conn, error) {
		host, port, err := net.SplitHostPort(address)
		if err != nil || port != "443" {
			return nil, errors.New("INVALID_SERVICE_DESTINATION")
		}
		if remoteDNS {
			return dial(ctx, network, address)
		}
		ips, err := probeDNSName(ctx, dial, host)
		if err != nil || len(ips) == 0 {
			return nil, errors.New("SERVICE_DNS_FAILED")
		}
		for _, ip := range ips {
			if !publicServiceIP(ip) {
				return nil, errors.New("NON_PUBLIC_SERVICE")
			}
		}
		return dial(ctx, network, net.JoinHostPort(ips[0].String(), "443"))
	}}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: 15 * time.Second, CheckRedirect: func(req *http.Request, via []*http.Request) error {
		if len(via) >= 5 || !allowedServiceURL(req.URL.String(), domains) {
			return errors.New("SERVICE_REDIRECT_REJECTED")
		}
		return nil
	}}
	request, err := http.NewRequestWithContext(ctx, "GET", raw, nil)
	if err != nil {
		return false
	}
	request.Header.Set("User-Agent", "PrettyLisaVPN-Availability/1.0")
	response, err := client.Do(request)
	if err != nil {
		return false
	}
	defer response.Body.Close()
	_, err = io.Copy(io.Discard, io.LimitReader(response.Body, 1024*1024))
	return err == nil && response.StatusCode == http.StatusOK
}

func publicServiceIP(ip net.IP) bool {
	if !ip.IsGlobalUnicast() || ip.IsPrivate() || ip.IsLoopback() || ip.IsLinkLocalUnicast() {
		return false
	}
	for _, raw := range []string{"0.0.0.0/8", "100.64.0.0/10", "192.0.0.0/24", "192.0.2.0/24", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "240.0.0.0/4"} {
		_, block, _ := net.ParseCIDR(raw)
		if block.Contains(ip) {
			return false
		}
	}
	return true
}
