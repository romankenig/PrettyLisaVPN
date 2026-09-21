import type { ConnectionConfig } from "./protocol";

export interface ObfuscationPlan {
  readonly mode: string;
  readonly version: number;
  readonly transport_parameters: Readonly<Record<string, number>>;
}
export interface ObfuscationProvider {
  readonly mode: string;
  readonly version: number;
  supports(protocol: string, transport: string): boolean;
  prepare(config: ConnectionConfig): ObfuscationPlan;
}

const emptyParameters = (config: ConnectionConfig) => {
  if (Object.keys(config.transport_parameters ?? {}).length !== 0)
    throw new Error("UNSUPPORTED_OBFUSCATION_CONFIGURATION");
};

/** Extension point is this registry and the owning packet/runtime adapter, never VpnProtocol. */
export class ObfuscationRegistry {
  private readonly providers = new Map<string, ObfuscationProvider>();
  constructor(providers: readonly ObfuscationProvider[]) {
    for (const provider of providers) {
      const key = `${provider.mode}:${provider.version}`;
      if (this.providers.has(key))
        throw new Error("DUPLICATE_OBFUSCATION_PROVIDER");
      this.providers.set(key, provider);
    }
  }
  prepare(config: ConnectionConfig): ObfuscationPlan {
    const version =
      config.obfuscation_version ??
      (config.obfuscation_mode === "NONE" ? 0 : -1);
    const provider = this.providers.get(
      `${config.obfuscation_mode}:${version}`,
    );
    if (!provider || !provider.supports(config.protocol, config.transport))
      throw new Error("UNSUPPORTED_OBFUSCATION_CONFIGURATION");
    return provider.prepare(config);
  }
}

export const obfuscationProviders = new ObfuscationRegistry([
  {
    mode: "NONE",
    version: 0,
    supports: () => true,
    prepare(config) {
      emptyParameters(config);
      return { mode: "NONE", version: 0, transport_parameters: {} };
    },
  },
  {
    mode: "SIMPLE_PACKET_WRAPPER_V1",
    version: 1,
    supports: (protocol, transport) =>
      protocol === "WIREGUARD" && transport === "UDP",
    prepare(config) {
      const parameters = config.transport_parameters ?? {};
      const maximum = parameters.max_datagram_size ?? 1400;
      // IPv4 WireGuard data adds 32 bytes (MTU 1280 is already 16-byte aligned).
      if (
        Object.keys(parameters).some((key) => key !== "max_datagram_size") ||
        typeof maximum !== "number" ||
        !Number.isInteger(maximum) ||
        maximum < config.mtu + 40 ||
        maximum > 65507
      )
        throw new Error("UNSUPPORTED_OBFUSCATION_CONFIGURATION");
      return {
        mode: "SIMPLE_PACKET_WRAPPER_V1",
        version: 1,
        transport_parameters: { max_datagram_size: maximum },
      };
    },
  },
  {
    mode: "TLS_TRANSPORT",
    version: 1,
    supports: (protocol, transport) =>
      protocol === "OPENVPN" && transport === "TCP",
    prepare(config) {
      emptyParameters(config);
      return { mode: "TLS_TRANSPORT", version: 1, transport_parameters: {} };
    },
  },
]);

export function validObfuscation(config: ConnectionConfig): boolean {
  try {
    obfuscationProviders.prepare(config);
    return true;
  } catch {
    return false;
  }
}
