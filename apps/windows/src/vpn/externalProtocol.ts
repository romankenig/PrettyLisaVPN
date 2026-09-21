import { normalizeFailure, checkHealth } from "./verification";
import { obfuscationProviders, type ObfuscationPlan } from "./obfuscation";
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
  readonly obfuscation?: ObfuscationPlan;
}
/** An implementation owns process/service lifecycle, TUN, routes, DNS and rollback.
 * health must independently verify DNS, HTTPS response and the VPN route.
 * start only establishes the tunnel; it never proves Internet access.
 * Raw output is deliberately unknown and is never returned directly to callers.
 */
export interface ExternalTunnelRuntime {
  /** Opt-in to an independently supplied mature TLS carrier, not merely TLS control encryption. */
  readonly obfuscation_modes?: readonly string[];
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
  const evidence = data.verification as Record<string, unknown> | undefined;
  const evidenceFailure =
    evidence?.route_verified === false
      ? "ROUTE_LEAK_DETECTED"
      : evidence?.egress_matches === false
        ? "EGRESS_MISMATCH"
        : evidence?.dns_verified === false
          ? "DNS_FAILED"
          : evidence?.https_verified === false
            ? "HTTPS_CHECK_FAILED"
            : null;
  const verified =
    up &&
    data.internet_verified === true &&
    !failed &&
    evidence?.dns_verified === true &&
    evidence?.https_verified === true &&
    evidence?.route_verified === true &&
    evidence?.egress_matches !== false;
  return {
    tunnel_established: up,
    internet_verified: verified,
    failure_code:
      evidenceFailure ??
      (failed
        ? normalizeFailure(data.failure_code)
        : verified
          ? null
          : up
            ? "TUNNEL_ESTABLISHED_NO_TRAFFIC"
            : "HANDSHAKE_FAILED"),
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
      return failed("UNKNOWN");
    }
  };
  return {
    capabilities: connectionProfiles[id],
    async connect(config, progress) {
      if (
        !validateProfileConfig(connectionProfiles[id], config) ||
        !parameters(config.parameters)
      )
        return failed("UNSUPPORTED_CONFIGURATION");
      if (!runtime) return failed("RUNTIME_UNAVAILABLE");
      const plan = obfuscationProviders.prepare(config);
      if (
        plan.mode !== "NONE" &&
        !runtime.obfuscation_modes?.includes(`${plan.mode}:${plan.version}`)
      )
        return failed("UNSUPPORTED_CONFIGURATION");
      try {
        const raw = await runtime.start({
          profile: id,
          ...(plan.mode === "NONE" ? {} : { obfuscation: plan }),
          config: createProfileConfig(id, config.country, config.port),
          parameters: { ...config.parameters },
          minimum_tls_version: "1.3",
          verify_certificate: true,
        });
        const result = safeResult(raw);
        const startupFailed =
          raw &&
          typeof raw === "object" &&
          "failure_code" in raw &&
          raw.failure_code != null;
        if (!result.tunnel_established || startupFailed) {
          await runtime.stop();
          return result;
        }
        progress?.("TUNNEL_ESTABLISHED");
        progress?.("VERIFYING_INTERNET");
        const verified = await checkHealth({ health });
        if (verified.failure_code) await runtime.stop();
        return verified;
      } catch {
        try {
          await runtime.stop();
        } catch {
          /* Caller also confirms teardown. */
        }
        return failed("UNKNOWN");
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
