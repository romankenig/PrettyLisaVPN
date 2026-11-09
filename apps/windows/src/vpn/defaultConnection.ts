import { invoke } from "@tauri-apps/api/core";
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
    fullTrafficOnly: () => session.current()?.plan === "DEMO",
    lost: (code?: string) => {
      void manager.connectionLost?.(code);
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
    async (signal) => {
      signal.throwIfAborted();
      await invoke("vpn_handoff");
      signal.throwIfAborted();
    },
  );
  manager.localTunnelStatus = async () =>
    (await wireGuardNative.isUp()) || (await managedNative.isUp())
      ? "UP"
      : "DOWN";
  const connect = manager.connect;
  manager.connect = (token, selection) =>
    connect(
      token,
      session.current()?.plan === "DEMO" ? { mode: "AUTO" } : selection,
    );
  return manager;
}
