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
  readonly mtu: number;
  readonly dns_mode: string;
  readonly routing_mode: string;
}

export type ProtocolStatus = "UP" | "DOWN";
export type ProtocolFailure =
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
  connect(config: ProtocolConfiguration): Promise<ConnectionResult>;
  disconnect(): Promise<ProtocolStatus>;
  status(): Promise<ProtocolStatus>;
  health(): Promise<ConnectionResult>;
  diagnostics(): Promise<ProtocolDiagnostics>;
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
): Promise<void> {
  const first = candidates[0];
  if (!first) throw new ProtocolConnectionError("UNSUPPORTED_CONFIGURATION");
  const result = await protocol.connect(first);
  if (
    result.failure_code ||
    !result.tunnel_established ||
    !result.internet_verified
  )
    throw new ProtocolConnectionError(
      result.failure_code ?? "CONNECTION_FAILED",
    );
}
