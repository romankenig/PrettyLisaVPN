// SPDX-License-Identifier: MIT
package softether

import (
	"context"
	"io"
	"net"
	"sync/atomic"
	"testing"
	"time"

	xnet "github.com/xtls/xray-core/common/net"
)

type echoHandler struct{ tcp, udp atomic.Int32 }

func (h *echoHandler) HandleConnection(conn net.Conn, dest xnet.Destination) {
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(3 * time.Second))
	if dest.Network == xnet.Network_UDP {
		h.udp.Add(1)
	} else {
		h.tcp.Add(1)
	}
	_, _ = io.Copy(conn, conn)
}
func TestNetworkTCPUDPThroughAuthenticatedTLS(t *testing.T) {
	cert, pin := certificate(t)
	l, accepted := listener(t, cert)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	client, err := Dial(ctx, l.Addr().String(), "test-authorization-123", "vpn.example.com", pin, (&net.Dialer{}).DialContext)
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	var server *Session
	select {
	case server = <-accepted:
	case <-ctx.Done():
		t.Fatal("server did not authorize")
	}
	defer server.Close()
	handler := &echoHandler{}
	var rx, tx atomic.Int64
	serverNet, err := NewNetwork(server, handler, func(up bool, n int) {
		if up {
			rx.Add(int64(n))
		} else {
			tx.Add(int64(n))
		}
	})
	if err != nil {
		t.Fatal(err)
	}
	defer serverNet.Close()
	clientNet, err := NewNetwork(client, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer clientNet.Close()
	for _, network := range []string{"tcp", "udp"} {
		conn, err := clientNet.DialContext(ctx, network, "192.0.2.1:12345")
		if err != nil {
			t.Fatal(network, err)
		}
		_ = conn.SetDeadline(time.Now().Add(2 * time.Second))
		if _, err = conn.Write([]byte("tunneled echo")); err != nil {
			t.Fatal(network, err)
		}
		got := make([]byte, 13)
		if _, err = io.ReadFull(conn, got); err != nil {
			t.Fatal(network, err)
		}
		if string(got) != "tunneled echo" {
			t.Fatal("payload mismatch")
		}
		_ = conn.Close()
	}
	if handler.tcp.Load() != 1 || handler.udp.Load() != 1 || rx.Load() == 0 || tx.Load() == 0 {
		t.Fatal("missing routed traffic")
	}
	_ = serverNet.Close()
	select {
	case <-clientNet.Done():
	case <-time.After(time.Second):
		t.Fatal("peer shutdown lost")
	}
	if _, err = clientNet.DialContext(ctx, "tcp", "192.0.2.1:12345"); err == nil {
		t.Fatal("closed network reopened")
	}
}
