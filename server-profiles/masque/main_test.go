//go:build linux

package main

import (
	"encoding/binary"
	"net/netip"
	"os"
	"testing"
	"time"
)

func TestPacketValidation(t *testing.T) {
	p := make([]byte, 1280)
	p[0] = 0x45
	binary.BigEndian.PutUint16(p[2:4], 1280)
	copy(p[12:16], []byte{10, 80, 0, 2})
	copy(p[16:20], []byte{1, 1, 1, 1})
	src, dst, ok := packet(p)
	if !ok || src.String() != "10.80.0.2" || dst.String() != "1.1.1.1" {
		t.Fatal("valid packet rejected")
	}
	for _, bad := range [][]byte{nil, p[:19], p[:1279], append(p, 0), {0x60}} {
		if _, _, ok := packet(bad); ok {
			t.Fatal("malformed accepted")
		}
	}
	p[0] = 0x44
	if _, _, ok := packet(p); ok {
		t.Fatal("invalid IHL accepted")
	}
}
func TestNoAdministrativeDestinations(t *testing.T) {
	for _, ip := range []string{"127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.169.254", "100.64.0.1", "0.0.0.0", "224.0.0.1", "255.255.255.255"} {
		if public(netip.MustParseAddr(ip)) {
			t.Fatal("private destination allowed")
		}
	}
	if !public(netip.MustParseAddr("1.1.1.1")) {
		t.Fatal("public destination rejected")
	}
}

func TestTunReadDoesNotFailBeforeTraffic(t *testing.T) {
	if os.Getenv("PRETTYLISA_TUN_TEST") != "1" {
		t.Skip("requires an isolated Linux network namespace and NET_ADMIN")
	}
	f, err := tun(config{Interface: "pltuntest", Address: "10.249.19.1/24"})
	if err != nil {
		t.Fatal("TUN setup failed")
	}
	defer f.Close()
	done := make(chan error, 1)
	go func() { b := make([]byte, 65535); _, err := f.Read(b); done <- err }()
	select {
	case err := <-done:
		if err != nil {
			t.Fatal("TUN descriptor failed before traffic")
		}
	case <-time.After(250 * time.Millisecond):
	}
}
