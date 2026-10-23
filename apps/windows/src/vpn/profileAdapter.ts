import type { WireGuardTunnelController } from "../native/wireguardTransport";
import {
  createExternalProtocol,
  type ExternalTunnelRuntime,
} from "./externalProtocol";
import { connectionProfiles, type ProfileId } from "./profiles";
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

/** Routes each authorized candidate to its own engine, retaining the winning
 * adapter for health, details and stop. No label can make an absent engine work.
 */
export function createAutomaticProtocol(
  dependencies: Parameters<typeof createProfileAdapter>[1] = {},
): VpnProtocol {
  const adapters = new Map<ProfileId, VpnProtocol>();
  const adapter = (id: ProfileId) => {
    let value = adapters.get(id);
    if (!value) {
      value = createProfileAdapter(id, dependencies);
      adapters.set(id, value);
    }
    return value;
  };
  let active: VpnProtocol | null = null;
  const current = () => active ?? adapter("WIREGUARD_UDP");
  return {
    get capabilities() {
      return current().capabilities;
    },
    async connect(config, progress) {
      const profile = Object.values(connectionProfiles).find(
        (item) =>
          item.protocol === config.protocol &&
          item.transport === config.transport,
      );
      const id =
        profile?.id ??
        (config.protocol === "WIREGUARD" && config.transport === "NATIVE"
          ? "WIREGUARD_UDP"
          : null);
      if (!id)
        return {
          tunnel_established: false,
          internet_verified: false,
          failure_code: "UNSUPPORTED_CONFIGURATION",
          diagnostics: {
            status: "DOWN",
            transport_healthy: false,
            tx_bytes: 0,
            rx_bytes: 0,
          },
        };
      active = adapter(id);
      return active.connect(config, progress);
    },
    async disconnect() {
      const status = await current().disconnect();
      if (status === "DOWN") active = null;
      return status;
    },
    status: () => current().status(),
    health: () => current().health(),
    diagnostics: () => current().diagnostics(),
    connectionDetails: async () => current().connectionDetails?.() ?? null,
  };
}
