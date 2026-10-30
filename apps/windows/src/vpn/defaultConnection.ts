import { createVpnConnectionManager } from "./connection";
import type { ApiClient } from "../api/client";
import type { AuthenticationSession } from "../auth/session";
import { createHttpTransport } from "../native/http";
import { connectionMethods } from "./catalog";
import { createManagedAdapter, managedNative, managedMethods } from "./managed";
import { createWireGuardAdapter, wireGuardNative } from "./wireguard";
import { createDeviceMethodPreference } from "./methodPreference";
import { getDeviceMethodSelection } from "./methodSelection";

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
  const manager = createVpnConnectionManager(
    [
      createWireGuardAdapter(options),
      createWireGuardAdapter({ ...options, viaRelay: true }),
      ...connectionMethods
        .filter((item) => item.id.replace(/_relay$/, "") in managedMethods)
        .map((item) =>
          createManagedAdapter({ ...options, id: item.id, name: item.name }),
        ),
    ],
    createDeviceMethodPreference(),
    getDeviceMethodSelection().current,
  );
  manager.localTunnelStatus = async () =>
    (await wireGuardNative.isUp()) || (await managedNative.isUp())
      ? "UP"
      : "DOWN";
  return manager;
}
