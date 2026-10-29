// SPDX-License-Identifier: MIT
package softether

import (
	"github.com/romankenig/PrettyLisaVPN/engines/managed/internal/packetnet"
	xtun "github.com/xtls/xray-core/proxy/tun"
)

type Network = packetnet.Network

func NewNetwork(s *Session, handler xtun.ConnectionHandler, traffic func(bool, int)) (*Network, error) {
	return packetnet.New(s, s.server, MTU, handler, traffic)
}
