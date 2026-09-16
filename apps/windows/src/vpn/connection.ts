import { ApiError, type ApiClient } from "../api/client";
import type { WireGuardKeyManager } from "../native/wireguardKeys";
import type { WireGuardTunnelController } from "../native/wireguardTransport";
import type { VpnLocationSelection } from "./selection";

export interface ConnectedVpnSession {
  readonly sessionId: string;
  readonly countryCode: string;
  readonly expiresAt: string | null;
}

export interface VpnConnectionOrchestrator {
  connect(
    accessToken: string,
    selection: VpnLocationSelection,
  ): Promise<ConnectedVpnSession>;
}

export class VpnConnectionError extends Error {
  constructor(
    readonly code:
      | "CONNECTION_IN_PROGRESS"
      | "COUNTRY_UNAVAILABLE"
      | "VPN_UNAVAILABLE"
      | "LOCAL_TUNNEL_FAILED"
      | "CONNECTION_FAILED",
  ) {
    super(code);
    this.name = "VpnConnectionError";
  }
}

export function createVpnConnectionOrchestrator(
  api: ApiClient,
  keys: WireGuardKeyManager,
  tunnel: WireGuardTunnelController,
): VpnConnectionOrchestrator {
  let inFlight = false;

  return {
    async connect(accessToken, selection) {
      if (inFlight) throw new VpnConnectionError("CONNECTION_IN_PROGRESS");
      inFlight = true;
      try {
        const publicKey = await keys.ensurePublicKey();
        const backendSession = await api.createVpnSession(
          accessToken,
          selection.mode === "AUTO"
            ? { mode: "AUTO", public_key: publicKey }
            : {
                mode: "COUNTRY",
                country_code: selection.country_code,
                public_key: publicKey,
              },
        );
        try {
          await tunnel.start({
            endpoint: backendSession.transport.endpoint,
            serverPublicKey: backendSession.transport.server_public_key,
            clientAddress: backendSession.transport.client_address,
            dns: backendSession.transport.dns,
            allowedIps: backendSession.transport.allowed_ips,
          });
          if ((await tunnel.state()) !== "UP") {
            throw new Error("native tunnel did not reach UP");
          }
        } catch {
          await bestEffortLocalStop(tunnel);
          await bestEffortBackendCleanup(
            api,
            accessToken,
            backendSession.session_id,
          );
          throw new VpnConnectionError("LOCAL_TUNNEL_FAILED");
        }

        return {
          sessionId: backendSession.session_id,
          countryCode: backendSession.country_code,
          expiresAt: backendSession.expires_at,
        };
      } catch (error) {
        if (error instanceof VpnConnectionError) throw error;
        if (error instanceof ApiError && error.code === "COUNTRY_UNAVAILABLE") {
          throw new VpnConnectionError("COUNTRY_UNAVAILABLE");
        }
        if (error instanceof ApiError && error.code === "VPN_UNAVAILABLE") {
          throw new VpnConnectionError("VPN_UNAVAILABLE");
        }
        throw new VpnConnectionError("CONNECTION_FAILED");
      } finally {
        inFlight = false;
      }
    },
  };
}

async function bestEffortLocalStop(tunnel: WireGuardTunnelController) {
  try {
    await tunnel.stop();
  } catch {
    // The native start path also rolls back its transient adapter on failure.
  }
}

async function bestEffortBackendCleanup(
  api: ApiClient,
  accessToken: string,
  sessionId: string,
) {
  try {
    await api.disconnectVpnSession(accessToken, sessionId);
  } catch {
    // Durable backend expiry/reconciliation remains the final safety net.
  }
}
