// SPDX-License-Identifier: MIT
package hysteria1

import (
	"context"
	"errors"
	"net"
	"syscall"
	"testing"
	"time"

	"github.com/xtls/xray-core/transport/internet"
)

func TestUplinkUsesOutboundProtectionAndPropagatesFailure(t *testing.T) {
	// No TUN, routes or administrator privileges: exercise the socket boundary
	// where the Windows physical-interface and Android VPN protection hooks run.
	internet.ControllersLock.Lock()
	previous := internet.Controllers
	var destination string
	reject := false
	internet.Controllers = append(append([]func(string, string, syscall.RawConn) error{}, previous...), func(_, address string, _ syscall.RawConn) error {
		destination = address
		if reject {
			return errors.New("test protection refusal")
		}
		return nil
	})
	internet.ControllersLock.Unlock()
	t.Cleanup(func() {
		internet.ControllersLock.Lock()
		internet.Controllers = previous
		internet.ControllersLock.Unlock()
	})
	peer, err := net.ListenPacket("udp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer peer.Close()
	port := uint16(peer.LocalAddr().(*net.UDPAddr).Port)
	packet, err := listenUplink(context.Background(), "127.0.0.1", port)
	if err != nil {
		t.Fatal(err)
	}
	defer packet.Close()
	if destination != peer.LocalAddr().String() {
		t.Fatalf("outbound protection did not receive the destination: %q", destination)
	}
	if _, err := packet.WriteTo([]byte("protected"), peer.LocalAddr()); err != nil {
		t.Fatal(err)
	}
	if err := peer.SetReadDeadline(time.Now().Add(time.Second)); err != nil {
		t.Fatal(err)
	}
	buffer := make([]byte, 32)
	n, remote, err := peer.ReadFrom(buffer)
	if err != nil || string(buffer[:n]) != "protected" {
		t.Fatalf("protected send failed: %v", err)
	}
	if _, err := peer.WriteTo(buffer[:n], remote); err != nil {
		t.Fatal(err)
	}
	if err := packet.SetReadDeadline(time.Now().Add(time.Second)); err != nil {
		t.Fatal(err)
	}
	n, _, err = packet.ReadFrom(buffer)
	if err != nil || string(buffer[:n]) != "protected" {
		t.Fatalf("protected receive failed: %v", err)
	}
	reject = true
	packet, err = listenUplink(context.Background(), "127.0.0.1", port)
	if err == nil || packet != nil {
		t.Fatal("protection failure must prevent socket use")
	}
}
