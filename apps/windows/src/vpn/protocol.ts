import type { ConnectionProfile } from "./profiles";
import type { ActiveVpnSessionResponse } from "../api/client";
import type { VpnLocationSelection } from "./selection";

/** Operational configuration. Never expose this through product/UI models. */
export interface ConnectionConfig {
  readonly country: string;
  /** Backend internal identity; never accepted from user selection. */
  readonly node_id?: string;
  readonly protocol: string;
  readonly transport: string;
  readonly port: number;
  readonly encryption_mode: string;
  readonly obfuscation_mode: string;
  readonly obfuscation_version?: number;
  readonly transport_parameters?: Readonly<Record<string, unknown>>;
  readonly mtu: number;
  readonly dns_mode: string;
  readonly routing_mode: string;
}

export type ProtocolStatus = "UP" | "DOWN";
export type ProtocolFailure =
  | "TRANSPORT_TIMEOUT"
  | "HANDSHAKE_FAILED"
  | "TUNNEL_ESTABLISHED_NO_TRAFFIC"
  | "DNS_FAILED"
  | "HTTPS_CHECK_FAILED"
  | "EGRESS_MISMATCH"
  | "ROUTE_LEAK_DETECTED"
  | "SERVER_UNREACHABLE"
  | "OBFUSCATION_FAILED"
  | "UNKNOWN"
  | "CONNECTION_FAILED"
  | "INTERNET_UNVERIFIED"
  | "UNSUPPORTED_CONFIGURATION"
  | "RUNTIME_UNAVAILABLE";
/** Closed allowlist: no messages, config dumps, endpoints, keys or tokens. */
export interface ProtocolDiagnostics {
  readonly status: ProtocolStatus | "UNKNOWN";
  readonly transport_healthy: boolean;
  readonly tx_bytes: number;
  readonly rx_bytes: number;
}
export interface ConnectionResult {
  readonly tunnel_established: boolean;
  readonly internet_verified: boolean;
  readonly failure_code: ProtocolFailure | null;
  readonly diagnostics: ProtocolDiagnostics;
}
export interface ProtocolConfiguration extends ConnectionConfig {
  /** Only the owning protocol adapter interprets this payload. */
  readonly parameters: unknown;
}
export interface VpnProtocol {
  readonly capabilities: ConnectionProfile;
  connect(
    config: ProtocolConfiguration,
    progress?: (phase: VerificationPhase) => void,
  ): Promise<ConnectionResult>;
  disconnect(): Promise<ProtocolStatus>;
  status(): Promise<ProtocolStatus>;
  health(): Promise<ConnectionResult>;
  diagnostics(): Promise<ProtocolDiagnostics>;
}
export type VerificationPhase = "TUNNEL_ESTABLISHED" | "VERIFYING_INTERNET";
export function isVerified(result: ConnectionResult): boolean {
  return (
    result.tunnel_established === true &&
    result.internet_verified === true &&
    result.failure_code === null
  );
}
/** Keeps protocol-specific provisioning and credentials out of orchestration. */
export interface VpnSessionProvisioner {
  create(
    accessToken: string,
    selection: VpnLocationSelection,
  ): Promise<ActiveVpnSessionResponse>;
  candidates(
    session: ActiveVpnSessionResponse,
  ): readonly ProtocolConfiguration[];
}

export class ProtocolConnectionError extends Error {
  constructor(readonly code: ProtocolFailure) {
    super(code);
    this.name = "ProtocolConnectionError";
  }
}

export async function connectFirstCandidate(
  protocol: VpnProtocol,
  candidates: readonly ProtocolConfiguration[],
  progress?: (phase: VerificationPhase) => void,
): Promise<void> {
  const first = candidates[0];
  if (!first) throw new ProtocolConnectionError("UNSUPPORTED_CONFIGURATION");
  const result = await protocol.connect(first, progress);
  if (!isVerified(result))
    throw new ProtocolConnectionError(
      result.failure_code ?? "CONNECTION_FAILED",
    );
}
