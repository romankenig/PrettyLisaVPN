import type { WireGuardTunnelController } from "../native/wireguardTransport";
import {
  createExternalProtocol,
  type ExternalTunnelRuntime,
} from "./externalProtocol";
import type { ProfileId } from "./profiles";
import type { VpnProtocol } from "./protocol";
import { createWireGuardProtocol } from "./wireguard";

/** Explicit instantiation only: no retry, preference ordering or fallback. */
export function createProfileAdapter(
  id: ProfileId,
  dependencies: {
    wireguard?: WireGuardTunnelController;
    openvpn?: ExternalTunnelRuntime;
    masque?: ExternalTunnelRuntime;
  } = {},
): VpnProtocol {
  switch (id) {
    case "WIREGUARD_UDP":
      return createWireGuardProtocol(dependencies.wireguard);
    case "OPENVPN_TLS_TCP":
      return createExternalProtocol(id, dependencies.openvpn);
    case "MASQUE_QUIC":
      return createExternalProtocol(id, dependencies.masque);
  }
}
