import { normalizeFailure, checkHealth } from "./verification";
import { obfuscationProviders } from "./obfuscation";
import { connectionProfiles, validateProfileConfig } from "./profiles";
import { isWireGuardTransport, type ApiClient } from "../api/client";
import {
  createWireGuardKeyManager,
  type WireGuardKeyManager,
} from "../native/wireguardKeys";
import {
  createWireGuardTunnelController,
  WireGuardTunnelError,
  type WireGuardTunnelController,
} from "../native/wireguardTransport";
import type {
  ConnectionConfig,
  ConnectionResult,
  ProtocolDiagnostics,
  VpnProtocol,
  VpnSessionProvisioner,
} from "./protocol";

export function wireGuardDefaults(
  country: string,
  port: number,
): ConnectionConfig {
  return {
    country,
    protocol: "WIREGUARD",
    transport: "NATIVE",
    port,
    encryption_mode: "WIREGUARD",
    obfuscation_mode: "NATIVE",
    mtu: 1280,
    dns_mode: "VPN",
    routing_mode: "FULL_TUNNEL",
  };
}

export function createWireGuardProvisioner(
  api: ApiClient,
  keys: WireGuardKeyManager = createWireGuardKeyManager(),
): VpnSessionProvisioner {
  return {
    async create(accessToken, selection) {
      const public_key = await keys.ensurePublicKey();
      return api.createVpnSession(
        accessToken,
        selection.mode === "AUTO"
          ? { mode: "AUTO", public_key }
          : {
              mode: "COUNTRY",
              country_code: selection.country_code,
              public_key,
            },
      );
    },
    candidates(session) {
      // Compatibility with backends predating candidate negotiation. An explicit
      // empty list is never replaced, and ordering is never changed locally.
      return (
        session.candidates ?? [
          wireGuardDefaults(
            session.country_code,
            session.transport.endpoint.port,
          ),
        ]
      ).map((config) => ({ ...config, parameters: session.transport }));
    },
  };
}

export function createWireGuardProtocol(
  tunnel: WireGuardTunnelController = createWireGuardTunnelController(),
): VpnProtocol {
  const diagnostics = async (): Promise<ProtocolDiagnostics> => {
    try {
      const status = await tunnel.state();
      const peer = await tunnel.diagnostics();
      const counter = (value: unknown) =>
        typeof value === "number" && Number.isFinite(value) && value >= 0
          ? value
          : 0;
      return {
        status,
        transport_healthy: peer?.transportHealthy === true,
        tx_bytes: counter(peer?.txBytes),
        rx_bytes: counter(peer?.rxBytes),
      };
    } catch {
      return {
        status: "UNKNOWN",
        transport_healthy: false,
        tx_bytes: 0,
        rx_bytes: 0,
      };
    }
  };
  const result = (
    established: boolean,
    internet: boolean,
    failure: ConnectionResult["failure_code"],
  ): ConnectionResult => ({
    tunnel_established: established,
    internet_verified: internet,
    failure_code: failure,
    diagnostics: {
      status: established ? "UP" : "DOWN",
      transport_healthy: established,
      tx_bytes: 0,
      rx_bytes: 0,
    },
  });
  const health = async (): Promise<ConnectionResult> => {
    try {
      const check = await tunnel.verify();
      const established = check.tunnel_established === true;
      const verified =
        established &&
        check.internet_verified === true &&
        check.failure_code === null;
      return result(
        established,
        verified,
        verified ? null : normalizeFailure(check.failure_code),
      );
    } catch {
      return result(false, false, "UNKNOWN");
    }
  };
  return {
    capabilities: connectionProfiles.WIREGUARD_UDP,
    async connect(config, progress) {
      const defaults = wireGuardDefaults(config.country, config.port);
      if (
        (!validateProfileConfig(connectionProfiles.WIREGUARD_UDP, config) &&
          (Object.entries(defaults).some(
            ([key, value]) => config[key as keyof ConnectionConfig] !== value,
          ) ||
            config.obfuscation_version !== undefined ||
            config.transport_parameters !== undefined)) ||
        !isWireGuardTransport(config.parameters) ||
        config.port !== config.parameters.endpoint.port
      )
        return result(false, false, "UNSUPPORTED_CONFIGURATION");
      const parameters = config.parameters;
      const plan =
        config.transport === "UDP"
          ? obfuscationProviders.prepare(config)
          : undefined;
      try {
        await tunnel.start({
          ...(plan?.mode === "NONE"
            ? { direct: true }
            : plan
              ? {
                  obfuscation: {
                    mode: plan.mode,
                    version: plan.version,
                    maxDatagramSize:
                      plan.transport_parameters.max_datagram_size,
                  },
                }
              : {}),
          endpoint: parameters.endpoint,
          serverPublicKey: parameters.server_public_key,
          clientAddress: parameters.client_address,
          dns: parameters.dns,
          allowedIps: parameters.allowed_ips,
        });
        const up = (await tunnel.state()) === "UP";
        if (!up) return result(false, false, "HANDSHAKE_FAILED");
        progress?.("TUNNEL_ESTABLISHED");
        progress?.("VERIFYING_INTERNET");
        return await checkHealth({ health });
      } catch (error) {
        return result(
          false,
          false,
          error instanceof WireGuardTunnelError
            ? nativeFailure(error.code)
            : "UNKNOWN",
        );
      }
    },
    async disconnect() {
      try {
        return await tunnel.stop();
      } catch {
        throw new Error("PROTOCOL_DISCONNECT_FAILED");
      }
    },
    async status() {
      try {
        return await tunnel.state();
      } catch {
        throw new Error("PROTOCOL_STATUS_UNAVAILABLE");
      }
    },
    health,
    diagnostics,
  };
}

function nativeFailure(code: string): import("./protocol").ProtocolFailure {
  if (code === "route_leak_detected") return "ROUTE_LEAK_DETECTED";
  if (code === "wireguard_handshake_timeout") return "HANDSHAKE_FAILED";
  if (code === "wireguard_data_plane_unavailable")
    return "TUNNEL_ESTABLISHED_NO_TRAFFIC";
  if (code.startsWith("obfuscation_")) return "OBFUSCATION_FAILED";
  return "UNKNOWN";
}
