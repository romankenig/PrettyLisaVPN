// SPDX-License-Identifier: MIT
package managed

import (
	"bytes"
	"encoding/json"
	"strconv"
	"testing"

	"github.com/xtls/xray-core/proxy/tun"
	"golang.org/x/sys/unix"
)

func TestAppleRetainsTypedProfileWithoutHostRouteMutation(t *testing.T) {
	for _, method := range []string{"WIREGUARD", "AMNEZIA", "SSTP", "SOFTETHER", "VLESS_TLS", "VLESS_REALITY", "VMESS_TLS", "SHADOWSOCKS_2022", "HYSTERIA1_TLS", "HYSTERIA2_TLS", "HYSTERIA2_SALAMANDER"} {
		p := sample(method)
		data, err := p.CoreConfig(true)
		if err != nil {
			t.Fatal(err)
		}
		var config map[string]any
		if json.Unmarshal(data, &config) != nil {
			t.Fatal("invalid configuration")
		}
		tun := config["inbounds"].([]any)[0].(map[string]any)["settings"].(map[string]any)
		for _, key := range []string{"autoOutboundsInterface", "autoSystemRoutingTable", "autoSystemWfpBlockLeak", "dns", "gateway"} {
			if _, found := tun[key]; found {
				t.Fatalf("Apple core must not mutate %s", key)
			}
		}
	}
}

func TestApplePublicPacketFlowSocketPairFramingAndOwnership(t *testing.T) {
	fds, err := unix.Socketpair(unix.AF_UNIX, unix.SOCK_DGRAM, 0)
	if err != nil {
		t.Fatal(err)
	}
	defer unix.Close(fds[0])
	defer unix.Close(fds[1])
	t.Setenv("XRAY_TUN_FD", strconv.Itoa(fds[1]))
	device, err := tun.NewTun(&tun.Config{Name: "PrettyLisaVPNEngine", MTU: 1280})
	if err != nil {
		t.Fatal(err)
	}
	packet := append([]byte{0x45}, bytes.Repeat([]byte{1}, 99)...)
	framed := append([]byte{0, 0, 0, unix.AF_INET}, packet...)
	if _, err = unix.Write(fds[0], framed); err != nil {
		t.Fatal(err)
	}
	buffer := make([]byte, 2048)
	read, err := device.ReadPacket(buffer)
	if err != nil || !bytes.Equal(read, packet) {
		t.Fatal("packetFlow-to-core framing failed", err)
	}
	if err = device.WritePacket(packet[:20], packet[20:]); err != nil {
		t.Fatal(err)
	}
	n, err := unix.Read(fds[0], buffer)
	if err != nil || n != len(framed) || !bytes.Equal(buffer[4:n], packet) {
		t.Fatal("core-to-packetFlow framing failed", err)
	}
	if err = device.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err = unix.FcntlInt(uintptr(fds[1]), unix.F_GETFD, 0); err != nil {
		t.Fatal("core closed the application-owned descriptor", err)
	}
}
