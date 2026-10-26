import type { VpnLocationSelection } from "./selection";
import type { ConnectionDetails } from "./connectionDetails";

export type ProtocolStatus = "UP" | "DOWN";
export type ConnectionResult =
  | { readonly connected: false }
  | {
      readonly connected: true;
      readonly internetVerified: true;
      readonly details: ConnectionDetails;
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
  disconnect(): Promise<void>;
}
