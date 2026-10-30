// SPDX-License-Identifier: MIT
package node

import (
	"context"
	"errors"
	"net"
	"testing"
	"time"

	"github.com/miekg/dns"
)

func TestProbeDNSUsesRawDatagramAndValidatesReply(t *testing.T) {
	for _, mode := range []string{"valid", "wrong-id", "truncated", "not-response", "failure", "empty"} {
		t.Run(mode, func(t *testing.T) {
			client, server := net.Pipe()
			defer server.Close()
			checked := make(chan error, 1)
			go func() {
				buffer := make([]byte, 4096)
				n, err := server.Read(buffer)
				query := new(dns.Msg)
				if err != nil || query.Unpack(buffer[:n]) != nil || len(query.Question) != 1 || query.Question[0].Name != "api.prettylisavpn.com." || query.Question[0].Qtype != dns.TypeA {
					checked <- errors.New("invalid UDP framing or destination")
					server.Close()
					return
				}
				answer := new(dns.Msg).SetReply(query)
				answer.Answer = []dns.RR{&dns.A{Hdr: dns.RR_Header{Name: query.Question[0].Name, Rrtype: dns.TypeA, Class: dns.ClassINET}, A: net.IPv4(203, 0, 113, 10)}}
				switch mode {
				case "wrong-id":
					answer.Id++
				case "truncated":
					answer.Truncated = true
				case "not-response":
					answer.Response = false
				case "failure":
					answer.Rcode = dns.RcodeServerFailure
				case "empty":
					answer.Answer = nil
				}
				packet, err := answer.Pack()
				if err == nil {
					_, err = server.Write(packet)
				}
				checked <- err
			}()
			ctx, cancel := context.WithTimeout(context.Background(), time.Second)
			defer cancel()
			addresses, err := probeDNS(ctx, func(_ context.Context, network, address string) (net.Conn, error) {
				if network != "udp" || address != "1.1.1.1:53" {
					t.Fatal("unexpected resolver")
				}
				return client, nil
			})
			if mode == "valid" {
				if err != nil || len(addresses) != 1 || addresses[0].String() != "203.0.113.10" {
					t.Fatal("valid response rejected", err)
				}
			} else if err == nil {
				t.Fatal("invalid reply accepted")
			}
			if err := <-checked; err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestProbeDNSCancellationClosesSocket(t *testing.T) {
	client, server := net.Pipe()
	defer server.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	started := time.Now()
	_, err := probeDNS(ctx, func(context.Context, string, string) (net.Conn, error) { return client, nil })
	if err == nil || time.Since(started) > time.Second {
		t.Fatal("cancelled socket survived")
	}
}

func TestProbeRejectsArbitraryConfigurationBeforeDial(t *testing.T) {
	for _, raw := range []string{`{}`, `{"command":"whoami"}`, `{} {}`, `{"measure_host":"127.0.0.1"}`, `{"profile":{"log":{"access":"/tmp/traffic"}}}`} {
		result := Probe([]byte(raw))
		if result.Status != "FAILED" || result.Code != "PROBE_CONFIGURATION_INVALID" || result.Handshake || !result.Cleanup {
			t.Fatal("unsafe input accepted")
		}
	}
}
