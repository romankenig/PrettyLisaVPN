package node

import (
	"bufio"
	"context"
	"encoding/base64"
	"io"
	"net"
	"net/http"
	"strings"
	"testing"
)

func TestProxyProbeProfileRejectsUnboundedOrInjectedInput(t *testing.T) {
	valid := `{"method":"HTTPS_PROXY","server":"proxy.example.org","port":49900,"username":"11111111-1111-4111-8111-111111111111","secret":"22222222-2222-4222-8222-222222222222"}`
	if _, err := parseProxyProbe([]byte(valid)); err != nil {
		t.Fatal(err)
	}
	for _, raw := range []string{strings.Replace(valid, "49900", "443", 1), strings.Replace(valid, "proxy.example.org", "user@proxy.example.org", 1), valid + `{}`, strings.Replace(valid, `"method"`, `"unknown"`, 1)} {
		if _, err := parseProxyProbe([]byte(raw)); err == nil {
			t.Fatal("invalid proxy profile accepted")
		}
	}
}

func TestProxyConnectAuthenticatesAndKeepsTunnelOpen(t *testing.T) {
	for _, status := range []string{"200 Connection established", "407 Authentication required"} {
		client, server := net.Pipe()
		done := make(chan error, 1)
		go func() {
			defer server.Close()
			request, err := http.ReadRequest(bufio.NewReader(server))
			if err != nil {
				done <- err
				return
			}
			expected := "Basic " + base64.StdEncoding.EncodeToString([]byte("user:secret"))
			if request.Method != "CONNECT" || request.Host != "api.prettylisavpn.com:443" || request.Header.Get("Proxy-Authorization") != expected {
				done <- io.ErrUnexpectedEOF
				return
			}
			_, err = io.WriteString(server, "HTTP/1.1 "+status+"\r\n\r\n")
			if strings.HasPrefix(status, "200") && err == nil {
				_, err = io.CopyN(io.Discard, server, 4)
			}
			done <- err
		}()
		err := connectProxy(client, "api.prettylisavpn.com:443", "user", "secret")
		if (err == nil) != strings.HasPrefix(status, "200") {
			t.Fatal("wrong CONNECT outcome", err)
		}
		if err == nil {
			_, err = io.WriteString(client, "ping")
			if err != nil {
				t.Fatal(err)
			}
		}
		client.Close()
		if err := <-done; err != nil {
			t.Fatal(err)
		}
	}
}

func TestProxyProbeRejectsNonWebDestinationsBeforeDial(t *testing.T) {
	dial := proxyProbeDial(proxyProbeProfile{})
	for _, address := range []string{"1.1.1.1:53", "127.0.0.1:22", "bad\r\nhost:443"} {
		if conn, err := dial(context.Background(), "tcp", address); err == nil {
			conn.Close()
			t.Fatal("invalid destination accepted")
		}
	}
}
