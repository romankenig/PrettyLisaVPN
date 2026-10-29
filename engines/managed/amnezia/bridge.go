// SPDX-License-Identifier: MIT
package amnezia

import (
	"context"
	"crypto/sha256"
	"encoding/binary"
	"fmt"

	"github.com/xtls/xray-core/common"
	"github.com/xtls/xray-core/common/serial"
	"github.com/xtls/xray-core/core"
	"github.com/xtls/xray-core/proxy/wireguard"
)

type DeviceConfig = wireguard.DeviceConfig
type MemoryAccount = wireguard.MemoryAccount

// Public obfuscation parameters are stable per node identity. They are not keys:
// the peer's X25519 key still authorizes every handshake. Disjoint header ranges
// avoid accidental collision with each other and standard WireGuard type bytes.
func obfuscation(serverPublicHex string) string {
	digest := sha256.Sum256([]byte("PrettyLisaVPN/AmneziaWG/v1/" + serverPublicHex))
	s := fmt.Sprintf("jc=4\njmin=40\njmax=140\ns1=%d\ns2=%d\n", 64+int(digest[0])%128, 16+int(digest[1])%32)
	for i := 0; i < 4; i++ {
		header := binary.LittleEndian.Uint32(digest[4+i*4:])&0x0fffffff | uint32(i+1)<<28
		s += fmt.Sprintf("h%d=%d\n", i+1, header)
	}
	return s
}

func init() {
	common.Must(common.RegisterConfig((*Config)(nil), func(ctx context.Context, value interface{}) (interface{}, error) {
		configuration := value.(*Config).Device
		if configuration == nil {
			return nil, fmt.Errorf("AMNEZIA_CONFIGURATION_INVALID")
		}
		configuration.NoKernelTun = true
		if configuration.IsClient {
			return NewClient(ctx, configuration)
		}
		return NewServer(ctx, configuration)
	}))
}

// Replace only parsed WireGuard proxy settings with the distinct Amnezia factory.
// TUN ownership, route protection and all other core settings remain unchanged.
func Wrap(configuration *core.Config) error {
	wrap := func(settings **serial.TypedMessage) error {
		if *settings == nil {
			return nil
		}
		value, err := (*settings).GetInstance()
		if err != nil {
			return err
		}
		if device, ok := value.(*wireguard.DeviceConfig); ok {
			*settings = serial.ToTypedMessage(&Config{Device: device})
		}
		return nil
	}
	for _, inbound := range configuration.Inbound {
		if err := wrap(&inbound.ProxySettings); err != nil {
			return err
		}
	}
	for _, outbound := range configuration.Outbound {
		if err := wrap(&outbound.ProxySettings); err != nil {
			return err
		}
	}
	return nil
}
