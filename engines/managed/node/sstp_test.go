// SPDX-License-Identifier: MIT
package node

import (
	"context"
	"io"
	"net"
	"strings"
	"testing"
	"time"

	"github.com/romankenig/PrettyLisaVPN/engines/managed/sstp"
	xnet "github.com/xtls/xray-core/common/net"
	commonserial "github.com/xtls/xray-core/common/serial"
	"github.com/xtls/xray-core/core"
	"github.com/xtls/xray-core/infra/conf/serial"
)

func TestSSTPCoreRoutesAndCloses(t *testing.T) {
	identity, err := NewIdentity("vpn.example.com", time.Now())
	if err != nil {
		t.Fatal(err)
	}
	reservation, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	port := uint32(reservation.Addr().(*net.TCPAddr).Port)
	_ = reservation.Close()
	serverConfig, err := fixture().Config()
	if err != nil {
		t.Fatal(err)
	}
	serverConfig.Inbound = nil
	serverConfig.App = append(serverConfig.App, commonserial.ToTypedMessage(&sstp.Config{Server: true, Address: "127.0.0.1", Port: port, Secret: "test-authorization-123", Certificate: identity.TLSCertificate, Key: identity.TLSKey}))
	local, err := serial.LoadJSONConfig(strings.NewReader(`{"outbounds":[{"tag":"internet","protocol":"freedom","settings":{"redirect":"127.0.0.1:0","finalRules":[{"action":"allow","ip":["127.0.0.1/32"]}]}}]}`))
	if err != nil {
		t.Fatal(err)
	}
	serverConfig.Outbound = local.Outbound
	server, err := core.New(serverConfig)
	if err != nil {
		t.Fatal(err)
	}
	defer server.Close()
	if err = server.Start(); err != nil {
		t.Fatal(err)
	}
	clientConfig, err := serial.LoadJSONConfig(strings.NewReader(`{"log":{"access":"none","error":"none","loglevel":"none"},"outbounds":[{"tag":"vpn","protocol":"freedom"}]}`))
	if err != nil {
		t.Fatal(err)
	}
	clientConfig.Outbound[0].ProxySettings = commonserial.ToTypedMessage(&sstp.Config{Address: "127.0.0.1", Port: port, Secret: "test-authorization-123", ServerName: "vpn.example.com", CertificatePin: identity.CertificatePin})
	client, err := core.New(clientConfig)
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	if err = client.Start(); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 6*time.Second)
	defer cancel()
	for _, network := range []string{"tcp", "udp"} {
		t.Run(network, func(t *testing.T) {
			var port string
			if network == "tcp" {
				listener, err := net.Listen("tcp", "127.0.0.1:0")
				if err != nil {
					t.Fatal(err)
				}
				defer listener.Close()
				_, port, _ = net.SplitHostPort(listener.Addr().String())
				go func() {
					conn, err := listener.Accept()
					if err == nil {
						defer conn.Close()
						_, _ = io.Copy(conn, conn)
					}
				}()
			} else {
				packet, err := net.ListenPacket("udp", "127.0.0.1:0")
				if err != nil {
					t.Fatal(err)
				}
				defer packet.Close()
				_, port, _ = net.SplitHostPort(packet.LocalAddr().String())
				go func() {
					b := make([]byte, 1024)
					n, a, e := packet.ReadFrom(b)
					if e == nil {
						_, _ = packet.WriteTo(b[:n], a)
					}
				}()
			}
			dest, _ := xnet.ParseDestination(network + ":203.0.113.9:" + port)
			conn, err := core.Dial(ctx, client, dest)
			if err != nil {
				t.Fatal(err)
			}
			defer conn.Close()
			stop := context.AfterFunc(ctx, func() { _ = conn.Close() })
			defer stop()
			if _, err = conn.Write([]byte("sstp core echo")); err != nil {
				t.Fatal(err)
			}
			got := make([]byte, 14)
			if _, err = io.ReadFull(conn, got); err != nil {
				t.Fatal(err)
			}
			if string(got) != "sstp core echo" {
				t.Fatal("core response mismatch")
			}
		})
	}
	_ = client.Close()
	_ = server.Close()
}
