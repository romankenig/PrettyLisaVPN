// SPDX-License-Identifier: MIT
package node

import (
	"bytes"
	"context"
	"crypto/ecdh"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"io"
	"net"
	"strings"
	"testing"
	"time"

	"github.com/romankenig/PrettyLisaVPN/engines/managed/amnezia"
	xnet "github.com/xtls/xray-core/common/net"
	"github.com/xtls/xray-core/core"
	"github.com/xtls/xray-core/infra/conf/serial"
)

func TestAmneziaEncryptedTCPUDPAndPeerRejection(t *testing.T) {
	serverKey, _ := ecdh.X25519().GenerateKey(rand.Reader)
	lease := fixture()
	lease.Method = "AMNEZIA"
	raw, _ := base64.StdEncoding.DecodeString(derived(lease.Secret, "amnezia-key"))
	clientKey, _ := ecdh.X25519().NewPrivateKey(raw)
	clear(raw)
	encode := base64.StdEncoding.EncodeToString
	udp, err := net.ListenPacket("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer udp.Close()
	go func() {
		buffer := make([]byte, 1500)
		for {
			n, addr, err := udp.ReadFrom(buffer)
			if err != nil {
				return
			}
			_, _ = udp.WriteTo(buffer[:n], addr)
		}
	}()
	tcp, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer tcp.Close()
	go func() {
		for {
			conn, err := tcp.Accept()
			if err != nil {
				return
			}
			go func() { defer conn.Close(); _, _ = io.Copy(conn, conn) }()
		}
	}()
	reserved, err := net.ListenPacket("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	port := reserved.LocalAddr().(*net.UDPAddr).Port
	endpoint := reserved.LocalAddr().String()
	reserved.Close()
	type obj = map[string]any
	start := func(value obj) *core.Instance {
		t.Helper()
		data, _ := json.Marshal(value)
		configuration, err := serial.LoadJSONConfig(bytes.NewReader(data))
		if err != nil {
			t.Fatal(err)
		}
		if err := amnezia.Wrap(configuration); err != nil {
			t.Fatal(err)
		}
		instance, err := core.New(configuration)
		if err != nil {
			t.Fatal(err)
		}
		t.Cleanup(func() { instance.Close() })
		if err := instance.Start(); err != nil {
			t.Fatal(err)
		}
		return instance
	}
	lease.Listen, lease.Port = "127.0.0.1", uint16(port)
	lease.PrivateKey = base64.RawURLEncoding.EncodeToString(serverKey.Bytes())
	start(obj{
		"inbounds":  lease.inbounds(),
		"outbounds": []any{obj{"protocol": "freedom", "settings": obj{"redirect": "127.0.0.1:0", "finalRules": []any{obj{"action": "allow", "ip": []string{"127.0.0.1/32"}}}}}},
	})
	client := func(key *ecdh.PrivateKey) *core.Instance {
		return start(obj{
			"outbounds": []any{obj{"protocol": "wireguard", "settings": obj{"secretKey": encode(key.Bytes()),
				"address": []string{"172.30.253.2/32"}, "mtu": 1280, "noKernelTun": true,
				"peers": []any{obj{"publicKey": encode(serverKey.PublicKey().Bytes()), "endpoint": endpoint, "allowedIPs": []string{"0.0.0.0/0"}}}}}},
		})
	}
	working := client(clientKey)
	for _, destination := range []string{"tcp:" + tcp.Addr().String(), "udp:" + udp.LocalAddr().String()} {
		t.Run(destination[:3], func(t *testing.T) {
			ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
			defer cancel()
			dest, _ := xnet.ParseDestination(strings.Replace(destination, "127.0.0.1", "203.0.113.7", 1))
			connection, err := core.Dial(ctx, working, dest)
			if err != nil {
				t.Fatal(err)
			}
			defer connection.Close()
			go func() { <-ctx.Done(); connection.Close() }()
			payload := []byte("amnezia-encrypted-roundtrip")
			if _, err := connection.Write(payload); err != nil {
				t.Fatal(err)
			}
			got := make([]byte, len(payload))
			if _, err := io.ReadFull(connection, got); err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(got, payload) {
				t.Fatal("roundtrip differs")
			}
		})
	}
	wrongKey, _ := ecdh.X25519().GenerateKey(rand.Reader)
	unauthorized := client(wrongKey)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	dest, _ := xnet.ParseDestination("tcp:" + strings.Replace(tcp.Addr().String(), "127.0.0.1", "203.0.113.7", 1))
	connection, err := core.Dial(ctx, unauthorized, dest)
	if err == nil {
		defer connection.Close()
		go func() { <-ctx.Done(); connection.Close() }()
		_, _ = connection.Write([]byte("not-authorized"))
		buffer := make([]byte, 1)
		if n, _ := connection.Read(buffer); n != 0 {
			t.Fatal("unknown peer passed authentication")
		}
	}
}
