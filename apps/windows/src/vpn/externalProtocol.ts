import {
  connectionProfiles,
  createProfileConfig,
  validateProfileConfig,
  type ProfileId,
} from "./profiles";
import type {
  ConnectionResult,
  ConnectionConfig,
  ProtocolDiagnostics,
  ProtocolStatus,
  VpnProtocol,
} from "./protocol";

/** Native/service-owned credentials and trust policy, never raw secrets or shell arguments. */
export interface ExternalTunnelParameters {
  readonly endpoint: string;
  readonly server_name: string;
  readonly credential_ref: string;
  readonly trust_ref: string;
}
export interface ExternalTunnelRequest {
  readonly profile: "OPENVPN_TLS_TCP" | "MASQUE_QUIC";
  readonly config: ConnectionConfig;
  readonly parameters: ExternalTunnelParameters;
  readonly minimum_tls_version: "1.3";
  readonly verify_certificate: true;
}
/** An implementation owns process/service lifecycle, TUN, routes, DNS and rollback.
 * A successful start must include an independent tunneled Internet probe.
 * Raw output is deliberately unknown and is never returned directly to callers.
 */
export interface ExternalTunnelRuntime {
  start(request: ExternalTunnelRequest): Promise<unknown>;
  stop(): Promise<unknown>;
  status(): Promise<unknown>;
  health(): Promise<unknown>;
}

function parameters(value: unknown): value is ExternalTunnelParameters {
  if (!value || typeof value !== "object") return false;
  const data = value as Record<string, unknown>;
  const keys = ["endpoint", "server_name", "credential_ref", "trust_ref"];
  const hostname = (v: unknown) =>
    typeof v === "string" &&
    v.length <= 253 &&
    v
      .split(".")
      .every((label) =>
        /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$/.test(label),
      );
  const reference = (v: unknown) =>
    typeof v === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(v);
  return (
    Object.keys(data).length === keys.length &&
    keys.every((key) => Object.hasOwn(data, key)) &&
    hostname(data.endpoint) &&
    hostname(data.server_name) &&
    reference(data.credential_ref) &&
    reference(data.trust_ref)
  );
}

function safeResult(raw: unknown): ConnectionResult {
  const data =
    raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  const up = data.tunnel_established === true;
  const failed = data.failure_code !== undefined && data.failure_code !== null;
  const verified = up && data.internet_verified === true && !failed;
  return {
    tunnel_established: up,
    internet_verified: verified,
    failure_code: failed
      ? "CONNECTION_FAILED"
      : verified
        ? null
        : up
          ? "INTERNET_UNVERIFIED"
          : "CONNECTION_FAILED",
    diagnostics: {
      status: up ? "UP" : "DOWN",
      transport_healthy: up,
      tx_bytes: 0,
      rx_bytes: 0,
    },
  };
}

export function createExternalProtocol(
  id: Exclude<ProfileId, "WIREGUARD_UDP">,
  runtime?: ExternalTunnelRuntime,
): VpnProtocol {
  const failed = (
    code: ConnectionResult["failure_code"],
  ): ConnectionResult => ({ ...safeResult(null), failure_code: code });
  const health = async (): Promise<ConnectionResult> => {
    if (!runtime) return failed("RUNTIME_UNAVAILABLE");
    try {
      return safeResult(await runtime.health());
    } catch {
      return failed("CONNECTION_FAILED");
    }
  };
  return {
    capabilities: connectionProfiles[id],
    async connect(config) {
      if (
        !validateProfileConfig(connectionProfiles[id], config) ||
        !parameters(config.parameters)
      )
        return failed("UNSUPPORTED_CONFIGURATION");
      if (!runtime) return failed("RUNTIME_UNAVAILABLE");
      try {
        const result = safeResult(
          await runtime.start({
            profile: id,
            config: createProfileConfig(id, config.country, config.port),
            parameters: { ...config.parameters },
            minimum_tls_version: "1.3",
            verify_certificate: true,
          }),
        );
        if (result.failure_code) await runtime.stop();
        return result;
      } catch {
        try {
          await runtime.stop();
        } catch {
          /* Caller also confirms teardown. */
        }
        return failed("CONNECTION_FAILED");
      }
    },
    async disconnect(): Promise<ProtocolStatus> {
      if (!runtime) return "DOWN";
      try {
        if ((await runtime.stop()) === "DOWN") return "DOWN";
      } catch {
        /* Sanitize. */
      }
      throw new Error("PROTOCOL_DISCONNECT_FAILED");
    },
    async status(): Promise<ProtocolStatus> {
      if (!runtime) return "DOWN";
      try {
        const state = await runtime.status();
        if (state === "UP" || state === "DOWN") return state;
      } catch {
        /* Sanitize. */
      }
      throw new Error("PROTOCOL_STATUS_UNAVAILABLE");
    },
    health,
    async diagnostics(): Promise<ProtocolDiagnostics> {
      return (await health()).diagnostics;
    },
  };
}
