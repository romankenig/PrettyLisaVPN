// SPDX-License-Identifier: MIT
package managed

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"strings"
	"time"
	"unicode"

	xnet "github.com/xtls/xray-core/common/net"
	"github.com/xtls/xray-core/common/session"
	"github.com/xtls/xray-core/core"
)

var ErrLocation = errors.New("PUBLIC_LOCATION_UNAVAILABLE")

type Location struct {
	Success bool    `json:"success"`
	IP      string  `json:"ip"`
	Country *string `json:"country_code"`
	City    *string `json:"city"`
}

// DirectLocation measures the same protected direct outbound used by excluded
// services. It accepts no URL, credentials or routing configuration. Ordinary
// ifconfig.me traffic still follows the existing mandatory VPN rule.
func (r *Runtime) DirectLocation() (*Location, error) {
	r.mu.Lock()
	instance, ok := r.instance.(*core.Instance)
	direct := r.direct
	r.mu.Unlock()
	if !ok || !direct {
		return nil, ErrLocation
	}
	ctx, cancel := context.WithTimeout(context.Background(), 12*time.Second)
	defer cancel()
	transport := &http.Transport{Proxy: nil, DisableKeepAlives: true,
		DialContext: func(ctx context.Context, network, address string) (net.Conn, error) {
			host, port, err := net.SplitHostPort(address)
			if err != nil || network != "tcp" || port != "443" || (host != "ifconfig.me" && host != "ipwho.is") {
				return nil, ErrLocation
			}
			return core.Dial(session.SetForcedOutboundTagToContext(ctx, "direct"), instance,
				xnet.TCPDestination(xnet.DomainAddress(host), 443))
		},
	}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: 8 * time.Second,
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }}
	result, err := observeDirectLocation(ctx, client)
	r.mu.Lock()
	current := r.instance == instance
	r.mu.Unlock()
	if !current {
		return nil, ErrLocation
	}
	return result, err
}

func observeDirectLocation(ctx context.Context, client *http.Client) (*Location, error) {
	read := func(url string, target any) error {
		req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
		if err != nil {
			return ErrLocation
		}
		req.Header.Set("Accept", "application/json")
		response, err := client.Do(req)
		if err != nil {
			return ErrLocation
		}
		defer response.Body.Close()
		if response.StatusCode != http.StatusOK {
			return ErrLocation
		}
		body, err := io.ReadAll(io.LimitReader(response.Body, 16385))
		if err != nil || len(body) > 16384 || json.Unmarshal(body, target) != nil {
			return ErrLocation
		}
		return nil
	}
	var value struct {
		IP string `json:"ip_addr"`
	}
	if read("https://ifconfig.me/all.json", &value) != nil {
		return nil, ErrLocation
	}
	ip := net.ParseIP(value.IP)
	if ip == nil || ip.To4() == nil || !ip.IsGlobalUnicast() || ip.IsPrivate() {
		return nil, ErrLocation
	}
	result := &Location{Success: true, IP: ip.String()}
	var geo Location
	if read("https://ipwho.is/"+result.IP, &geo) == nil && geo.Success && geo.IP == result.IP {
		if geo.Country != nil && len(*geo.Country) == 2 && strings.IndexFunc(*geo.Country, func(r rune) bool { return r < 'A' || r > 'Z' }) == -1 {
			result.Country = geo.Country
		}
		if geo.City != nil && len([]rune(*geo.City)) <= 120 && strings.IndexFunc(*geo.City, unicode.IsControl) == -1 {
			city := strings.TrimSpace(*geo.City)
			if city != "" {
				result.City = &city
			}
		}
	}
	return result, nil
}
