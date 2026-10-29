import { invoke } from "@tauri-apps/api/core";
import type { HttpTransport } from "../native/http";
import { createSessionAdapter, type SessionEngine } from "./sessionAdapter";

export const managedMethods = {
  vless_reality: "VLESS_REALITY",
  vless: "VLESS_TLS",
  vmess: "VMESS_TLS",
  shadowsocks2022: "SHADOWSOCKS_2022",
  hysteria2: "HYSTERIA2_TLS",
  hysteria2_salamander: "HYSTERIA2_SALAMANDER",
} as const;
export interface ManagedConfiguration {
  engine_profile: {
    version: number;
    session: string;
    country: string;
    method: string;
    server: string;
    port: number;
    secret: string;
  };
  expected_egress_ips: string[];
}
export const managedNative: SessionEngine<ManagedConfiguration> = {
  async prepare() {
    // Request binding only: these transports do not use a WireGuard private key.
    return btoa(
      String.fromCharCode(...crypto.getRandomValues(new Uint8Array(32))),
    );
  },
  start: ({ engine_profile }) =>
    invoke("engine_start", { profile: engine_profile }),
  stop: () => invoke("engine_stop"),
  isUp: () => invoke("engine_is_up"),
  verify: (_, sessionId, accessToken) =>
    invoke("engine_verify", { sessionId, accessToken }),
};
export function createManagedAdapter(options: {
  baseUrl: string;
  transport: HttpTransport;
  bearer: () => Promise<string>;
  lost: () => void;
  id: string;
  name: string;
  native?: SessionEngine<ManagedConfiguration>;
}) {
  const base = options.id.replace(/_relay$/, "") as keyof typeof managedMethods;
  if (!(base in managedMethods)) throw new Error("VPN_METHOD_UNSUPPORTED");
  return createSessionAdapter<ManagedConfiguration>({
    ...options,
    method: options.id,
    path: "/vpn/sessions",
    native: options.native ?? managedNative,
    validate: (configuration, id, country) => {
      const p = configuration.engine_profile;
      if (
        !p ||
        p.version !== 1 ||
        p.session !== id ||
        p.country !== country ||
        p.method !== managedMethods[base] ||
        !configuration.expected_egress_ips?.length
      )
        throw new Error("VPN_INVALID_CONFIGURATION");
    },
    details: ({ engine_profile: p }) => ({
      protocol: options.name,
      transport: base.startsWith("hysteria2")
        ? "UDP"
        : base === "shadowsocks2022"
          ? "TCP/UDP"
          : "TCP",
      server: `${p.server}:${p.port}`,
      encryption: base === "shadowsocks2022" ? "AEAD-2022" : "TLS",
      obfuscation:
        base === "vless_reality"
          ? "REALITY"
          : base === "hysteria2_salamander"
            ? "Salamander"
            : "none",
      mtu: 1280,
      dns: ["1.1.1.1"],
      clientAddress: "172.30.255.1/30",
      allowedIps: ["0.0.0.0/0", "::/0"],
    }),
  });
}
