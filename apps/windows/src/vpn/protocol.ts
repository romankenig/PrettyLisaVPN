import type { VpnLocationSelection } from "./selection";
import type { ConnectionDetails } from "./connectionDetails";
import type { ConnectedVpnSession } from "./connection";

export type ProtocolStatus = "UP" | "DOWN";
/** Local shutdown succeeded; the server has not confirmed removal yet. */
export class RemoteCleanupPending extends Error {
  constructor() {
    super("VPN_REMOTE_CLEANUP_PENDING");
  }
}
export type ConnectionResult =
  | { readonly connected: false }
  | {
      readonly connected: true;
      readonly internetVerified: true;
      readonly details: ConnectionDetails;
      readonly session?: ConnectedVpnSession;
    };

/** An adapter owns its resources. Failure and cancellation must finish cleanup
 * before the orchestrator starts another method. Never return success on start alone. */
export interface ConnectionAdapter {
  readonly id: string;
  readonly name: string;
  connect(
    selection: VpnLocationSelection,
    signal: AbortSignal,
  ): Promise<ConnectionResult>;
  disconnect(onLocalStopped?: () => void): Promise<void>;
  recover?(onLocalStopped?: () => void): Promise<void>;
}
