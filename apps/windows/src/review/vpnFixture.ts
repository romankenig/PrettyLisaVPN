import type { ApiClient } from "../api/client";
import type { WireGuardTunnelController } from "../native/wireguardTransport";
import { createVpnConnectionManager } from "../vpn/connection";
import {
  createWireGuardProtocol,
  createWireGuardProvisioner,
} from "../vpn/wireguard";

// Only selected by the explicit test-environment review build flag in main.tsx.
// These dependencies never invoke native VPN commands or create real keys.
export function createReviewVpnConnection(api: ApiClient) {
  const key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
  let up = false;
  const tunnel: WireGuardTunnelController = {
    async start() {
      up = true;
      return "UP";
    },
    async stop() {
      up = false;
      return "DOWN";
    },
    async state() {
      return up ? "UP" : "DOWN";
    },
    async verify() {
      return {
        tunnel_established: up,
        internet_verified: up,
        failure_code: up ? null : "HTTPS_CHECK_FAILED",
      };
    },
    async diagnostics() {
      return up
        ? {
            peerPublicKey: key,
            endpoint: "192.0.2.20:51820",
            publicEndpoint: "192.0.2.20:51820",
            allowedIps: ["0.0.0.0/0"],
            persistentKeepalive: 25,
            txBytes: 100,
            rxBytes: 200,
            transportMode: "DIRECT",
            transportHealthy: true,
          }
        : null;
    },
  };
  const keys = {
    ensurePublicKey: async () => key,
    loadPublicKey: async () => key,
    delete: async () => undefined,
  };
  return createVpnConnectionManager(
    api,
    createWireGuardProvisioner(api, keys),
    createWireGuardProtocol(tunnel),
  );
}
