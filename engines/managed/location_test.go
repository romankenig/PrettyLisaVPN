// SPDX-License-Identifier: MIT
package managed

import (
	"context"
	"io"
	"net/http"
	"strings"
	"testing"
)

type locationTransport func(*http.Request) (*http.Response, error)

func (f locationTransport) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestDirectLocationRequiresLiveSplitRuntime(t *testing.T) {
	r := &Runtime{}
	if _, err := r.DirectLocation(); err != ErrLocation {
		t.Fatal("inactive runtime must not observe another route")
	}
}

func TestDirectLocationFixedAnonymousObservation(t *testing.T) {
	calls := 0
	client := &http.Client{Transport: locationTransport(func(r *http.Request) (*http.Response, error) {
		calls++
		if r.Header.Get("Authorization") != "" || r.Header.Get("Cookie") != "" || r.Header.Get("Origin") != "" {
			t.Fatal("identity headers")
		}
		body := `{"ip_addr":"8.8.4.4","ignored":"not retained"}`
		if calls == 1 && r.URL.String() != "https://ifconfig.me/all.json" {
			t.Fatal("unexpected endpoint")
		}
		if calls == 2 {
			if r.URL.String() != "https://ipwho.is/8.8.4.4" {
				t.Fatal("unexpected geo endpoint")
			}
			body = `{"success":true,"ip":"8.8.4.4","country_code":"US","city":"Example"}`
		}
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(body))}, nil
	})}
	result, err := observeDirectLocation(context.Background(), client)
	if err != nil || result.IP != "8.8.4.4" || result.Country == nil || *result.Country != "US" || calls != 2 {
		t.Fatal("observation failed")
	}
}

func TestDirectLocationRejectsInvalidPrimaryAndIgnoresWrongGeo(t *testing.T) {
	for _, body := range []string{`{"ip_addr":"127.0.0.1"}`, `{"ip_addr":"10.0.0.1"}`, `{"ip_addr":"host/path"}`, strings.Repeat("x", 16385)} {
		client := &http.Client{Transport: locationTransport(func(r *http.Request) (*http.Response, error) {
			return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(body))}, nil
		})}
		if _, err := observeDirectLocation(context.Background(), client); err != ErrLocation {
			t.Fatal("invalid observation accepted")
		}
	}
	client := &http.Client{Transport: locationTransport(func(r *http.Request) (*http.Response, error) {
		body := `{"ip_addr":"8.8.4.4"}`
		if r.URL.Host == "ipwho.is" {
			body = `{"success":true,"ip":"1.1.1.1","country_code":"DE","city":"Wrong"}`
		}
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(body))}, nil
	})}
	result, err := observeDirectLocation(context.Background(), client)
	if err != nil || result.Country != nil || result.City != nil {
		t.Fatal("mismatched geolocation used")
	}
}
