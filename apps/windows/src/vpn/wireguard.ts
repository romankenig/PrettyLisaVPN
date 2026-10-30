import { invoke } from "@tauri-apps/api/core";
import type { HttpTransport } from "../native/http";
import type { ConnectionAdapter } from "./protocol";
import { createSessionAdapter } from "./sessionAdapter";
import {
  getDeviceTrafficSelection,
  routingPolicy,
  type RoutingPolicy,
} from "./traffic";

interface Configuration {
  address: string;
  server_public_key: string;
  endpoint: string;
  mtu: number;
  dns: string[];
  allowed_ips: string[];
}
export interface WireGuardNative {
  prepare(): Promise<string>;
  start(
    configuration: Configuration,
    context: { id: string; country: string },
  ): Promise<void>;
  stop(): Promise<void>;
  verify(address: string, id: string, token: string): Promise<boolean>;
  isUp(): Promise<boolean>;
}
let routing: RoutingPolicy = { mode: "all", domains: [] };
export const wireGuardNative: WireGuardNative = {
  prepare: () => {
    routing = routingPolicy(getDeviceTrafficSelection().current());
    return invoke("wg_prepare");
  },
  start: ({ address, server_public_key, endpoint, mtu }, context) =>
    routing.mode === "all"
      ? invoke("wg_start", {
          configuration: { address, server_public_key, endpoint, mtu },
        })
      : invoke("wg_start_routed", {
          configuration: { address, server_public_key, endpoint, mtu },
          sessionId: context.id,
          country: context.country,
          routing,
        }),
  stop: async () => {
    try {
      await invoke("engine_stop");
    } finally {
      await invoke("wg_stop");
    }
  },
  verify: (address, sessionId, accessToken) =>
    routing.mode === "all"
      ? invoke("wg_verify", { address, sessionId, accessToken })
      : invoke("engine_verify", { sessionId, accessToken }),
  isUp: async () =>
    (await invoke<boolean>("wg_is_up")) ||
    (await invoke<boolean>("engine_is_up")),
};
export function createWireGuardAdapter(options: {
  baseUrl: string;
  transport: HttpTransport;
  bearer: () => Promise<string>;
  lost: () => void;
  native?: WireGuardNative;
  viaRelay?: boolean;
}): ConnectionAdapter {
  const native = options.native ?? wireGuardNative;
  const method = options.viaRelay ? "wireguard_relay" : "wireguard";
  const name = options.viaRelay ? "WireGuard+" : "WireGuard";
  return createSessionAdapter<Configuration>({
    ...options,
    method,
    name,
    path: "/vpn/wireguard/sessions",
    native: {
      ...native,
      verify: (configuration, id, token) =>
        native.verify(configuration.address, id, token),
    },
    validate: () => {},
    details: (configuration) => ({
      protocol: name,
      transport: "UDP",
      server: configuration.endpoint,
      encryption: "ChaCha20-Poly1305",
      obfuscation: "none",
      mtu: configuration.mtu,
      dns: configuration.dns,
      clientAddress: configuration.address,
      allowedIps: configuration.allowed_ips,
      serverPublicKey: configuration.server_public_key,
      keepalive: 25,
    }),
  });
}
