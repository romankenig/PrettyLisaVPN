import { createVpnConnectionManager } from "./connection";
import type { ApiClient } from "../api/client";
import type { AuthenticationSession } from "../auth/session";
import { createHttpTransport } from "../native/http";
import { placeholderAdapters } from "./placeholders";
import { createWireGuardAdapter, wireGuardNative } from "./wireguard";

export function createDefaultVpnConnection(
  baseUrl: string,
  session: AuthenticationSession,
  api: ApiClient,
) {
  const options = {
    baseUrl,
    transport: createHttpTransport(),
    bearer: () => session.bearer(api),
    lost: () => {
      void manager.connectionLost?.();
    },
  };
  const manager = createVpnConnectionManager([
    createWireGuardAdapter(options),
    createWireGuardAdapter({ ...options, viaRelay: true }),
    ...placeholderAdapters().filter((item) => item.id !== "wireguard"),
  ]);
  manager.localTunnelStatus = async () =>
    (await wireGuardNative.isUp()) ? "UP" : "DOWN";
  return manager;
}
