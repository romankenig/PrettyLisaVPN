/**
 * Native-only tunnel bootstrap contract. These values are operationally visible
 * on the user's machine and must not be promoted into React discovery models.
 */
export interface WireGuardEndpoint {
  readonly ipv4: string;
  readonly port: number;
}

export interface WireGuardTransportConfiguration {
  readonly endpoint: WireGuardEndpoint;
  readonly serverPublicKey: string;
  readonly clientAddress: string;
  readonly dns: readonly string[];
  readonly allowedIps: readonly string[];
}

export type WireGuardTunnelState = "UP" | "DOWN";

export interface WireGuardPeerDiagnostics {
  readonly peerPublicKey: string;
  readonly endpoint: string;
  readonly allowedIps: readonly string[];
  readonly persistentKeepalive: number;
  readonly txBytes: number;
  readonly rxBytes: number;
  readonly transportMode: "DIRECT" | "PRETTYLISA_V1" | "WG_OBFUSCATOR";
  readonly transportHealthy: boolean;
  readonly publicEndpoint: string;
}

export interface WireGuardTunnelController {
  start(
    configuration: WireGuardTransportConfiguration,
  ): Promise<WireGuardTunnelState>;
  stop(): Promise<WireGuardTunnelState>;
  state(): Promise<WireGuardTunnelState>;
  diagnostics(): Promise<WireGuardPeerDiagnostics | null>;
}

export class WireGuardTunnelError extends Error {
  constructor(readonly code: string) {
    super(code);
    this.name = "WireGuardTunnelError";
  }
}

type NativeInvoke = <T>(
  command: string,
  args?: Record<string, unknown>,
) => Promise<T>;

export function createWireGuardTunnelController(
  invokeNative: NativeInvoke = invokeTunnelCommand,
): WireGuardTunnelController {
  return {
    async start(configuration) {
      return invokeAndValidate(invokeNative, "start_wireguard_tunnel", {
        configuration,
      });
    },
    async stop() {
      return invokeAndValidate(invokeNative, "stop_wireguard_tunnel");
    },
    async state() {
      return invokeAndValidate(invokeNative, "get_wireguard_tunnel_state");
    },
    async diagnostics() {
      try {
        return await invokeNative<WireGuardPeerDiagnostics | null>(
          "get_wireguard_peer_diagnostics",
        );
      } catch (error) {
        const code =
          typeof error === "string" ? error : "wireguard_tunnel_unavailable";
        throw new WireGuardTunnelError(code);
      }
    },
  };
}

async function invokeAndValidate(
  invokeNative: NativeInvoke,
  command: string,
  args?: Record<string, unknown>,
): Promise<WireGuardTunnelState> {
  try {
    const result = await invokeNative<unknown>(command, args);
    if (result !== "UP" && result !== "DOWN")
      throw new Error("invalid native state");
    return result;
  } catch (error) {
    const code =
      typeof error === "string" ? error : "wireguard_tunnel_unavailable";
    throw new WireGuardTunnelError(code);
  }
}

async function invokeTunnelCommand<T>(
  command: string,
  args?: Record<string, unknown>,
): Promise<T> {
  const { invoke, isTauri } = await import("@tauri-apps/api/core");
  if (!isTauri()) throw new Error("TAURI_REQUIRED");
  return invoke<T>(command, args);
}
