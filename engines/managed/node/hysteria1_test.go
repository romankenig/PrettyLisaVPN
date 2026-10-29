// SPDX-License-Identifier: MIT
package node

import (
	"bytes"
	"context"
	"io"
	"net"
	"strings"
	"testing"
	"time"

	managed "github.com/romankenig/PrettyLisaVPN/engines/managed"
	xnet "github.com/xtls/xray-core/common/net"
	"github.com/xtls/xray-core/core"
	"github.com/xtls/xray-core/infra/conf/serial"
)

func TestHysteria1LeaseAndClientCore(t *testing.T) {
	cert, key, pin := certificate(t)
	lease := fixture()
	lease.Method = "HYSTERIA1_TLS"
	lease.TLSCertificate, lease.TLSKey = cert, key
	reserved, err := net.ListenPacket("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	lease.Listen, lease.Port = "127.0.0.1", uint16(reserved.LocalAddr().(*net.UDPAddr).Port)
	reserved.Close()
	serverConfiguration, err := lease.Config()
	if err != nil {
		t.Fatal(err)
	}
	// Only the test redirects a documentation IP to a local echo destination.
	localOut, err := serial.LoadJSONConfig(strings.NewReader(`{"outbounds":[{"tag":"internet","protocol":"freedom","settings":{"redirect":"127.0.0.1:0","finalRules":[{"action":"allow","ip":["127.0.0.1/32"]}]}}]}`))
	if err != nil {
		t.Fatal(err)
	}
	serverConfiguration.Outbound = localOut.Outbound
	server, err := core.New(serverConfiguration)
	if err != nil {
		t.Fatal(err)
	}
	defer server.Close()
	if err = server.Start(); err != nil {
		t.Fatal(err)
	}
	p := managed.Profile{Version: 1, Session: lease.ID, Country: "DE", Method: lease.Method, Server: "192.0.2.20", Port: lease.Port, Secret: lease.Secret, ServerName: lease.ServerName, CertificatePin: pin}
	data, err := p.CoreConfig(true)
	if err != nil {
		t.Fatal(err)
	}
	config, err := serial.LoadJSONConfig(bytes.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	config.Inbound = nil
	p.Server = "127.0.0.1"
	if p.Configure(config) != nil {
		t.Fatal("typed profile rejected")
	}
	client, err := core.New(config)
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	if err = client.Start(); err != nil {
		t.Fatal(err)
	}
	for _, network := range []string{"tcp", "udp"} {
		t.Run(network, func(t *testing.T) {
			var port string
			if network == "tcp" {
				l, e := net.Listen("tcp", "127.0.0.1:0")
				if e != nil {
					t.Fatal(e)
				}
				defer l.Close()
				_, port, _ = net.SplitHostPort(l.Addr().String())
				go func() {
					c, e := l.Accept()
					if e == nil {
						defer c.Close()
						_, _ = io.Copy(c, c)
					}
				}()
			} else {
				l, e := net.ListenPacket("udp", "127.0.0.1:0")
				if e != nil {
					t.Fatal(e)
				}
				defer l.Close()
				_, port, _ = net.SplitHostPort(l.LocalAddr().String())
				go func() {
					b := make([]byte, 65507)
					for {
						n, a, e := l.ReadFrom(b)
						if e != nil {
							return
						}
						_, _ = l.WriteTo(b[:n], a)
					}
				}()
			}
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			dest, _ := xnet.ParseDestination(network + ":203.0.113.7:" + port)
			conn, e := core.Dial(ctx, client, dest)
			if e != nil {
				t.Fatal(e)
			}
			defer conn.Close()
			stop := context.AfterFunc(ctx, func() { _ = conn.Close() })
			defer stop()
			payload := bytes.Repeat([]byte("encrypted"), 128)
			if _, e = conn.Write(payload); e != nil {
				t.Fatal(e)
			}
			got := make([]byte, len(payload))
			if _, e = io.ReadFull(conn, got); e != nil {
				t.Fatal(e)
			}
			if !bytes.Equal(got, payload) {
				t.Fatal("payload mismatch")
			}
		})
	}
}
