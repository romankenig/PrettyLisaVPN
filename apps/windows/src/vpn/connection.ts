import type { ConnectionAdapter, ProtocolStatus } from "./protocol";
import type { VpnLocationSelection } from "./selection";
import type { ConnectionDetails } from "./connectionDetails";
import type { ConnectionAttempt } from "./attempt";
import { placeholderAdapters } from "./placeholders";

export interface ConnectedVpnSession {
  readonly sessionId: string;
  readonly countryCode: string;
  readonly expiresAt: string | null;
  readonly remainingSeconds: number | null;
}
export type VpnConnectionState =
  | {
      readonly phase: "RECONCILING" | "CONNECTING";
      readonly backend: "UNKNOWN" | "ACTIVE" | "NONE";
      readonly tunnel: "UNKNOWN" | "DOWN";
      readonly session?: ConnectedVpnSession;
      readonly attempt?: ConnectionAttempt;
    }
  | {
      readonly phase: "DISCONNECTING";
      readonly backend: "ACTIVE";
      readonly tunnel: ProtocolStatus;
      readonly session?: ConnectedVpnSession;
    }
  | {
      readonly phase: "DISCONNECTED";
      readonly backend: "NONE" | "UNAVAILABLE";
      readonly tunnel: "DOWN";
      readonly session?: ConnectedVpnSession;
    }
  | {
      readonly phase: "CONNECTED";
      readonly backend: "ACTIVE";
      readonly tunnel: "UP";
      readonly session: ConnectedVpnSession;
    }
  | {
      readonly phase:
        "TUNNEL_ESTABLISHED" | "VERIFYING_INTERNET" | "DEGRADED" | "FAILED";
      readonly backend: "ACTIVE" | "NONE" | "UNAVAILABLE";
      readonly tunnel: ProtocolStatus | "UNAVAILABLE";
      readonly session?: ConnectedVpnSession;
      readonly failure_code?: string;
      readonly attempt?: ConnectionAttempt;
    }
  | {
      readonly phase: "UNAVAILABLE";
      readonly backend: "ACTIVE" | "NONE" | "UNAVAILABLE";
      readonly tunnel: ProtocolStatus | "UNAVAILABLE";
      readonly reason:
        "BACKEND_UNAVAILABLE" | "TUNNEL_UNAVAILABLE" | "CONNECTION_FAILED";
      readonly session?: ConnectedVpnSession;
    };

export interface VpnConnectionManager {
  /** Read-only probe for pre-login locale detection; never starts or stops a tunnel. */
  localTunnelStatus?(): Promise<ProtocolStatus>;
  connectionDetails?(): Promise<ConnectionDetails | null>;
  readonly current: () => VpnConnectionState;
  readonly subscribe: (listener: () => void) => () => void;
  reconcile(accessToken: string): Promise<void>;
  connect(accessToken: string, selection: VpnLocationSelection): Promise<void>;
  disconnect(accessToken: string): Promise<void>;
  setOwner?(owner: string | null): void;
  dispose(): void;
  connectionLost?(): Promise<void>;
}

export class VpnConnectionError extends Error {
  constructor(
    readonly code:
      | "CONNECTION_IN_PROGRESS"
      | "COUNTRY_UNAVAILABLE"
      | "VPN_UNAVAILABLE"
      | "LOCAL_TUNNEL_FAILED"
      | "VPN_TRAFFIC_INTERCEPTED"
      | "LOCAL_TUNNEL_STOP_FAILED"
      | "CONNECTION_FAILED"
      | string,
  ) {
    super(code);
    this.name = "VpnConnectionError";
  }
}

/** Real adapters and placeholders share one sequential executor and cleanup boundary. */
export function createVpnConnectionManager(
  adapters: readonly ConnectionAdapter[] = placeholderAdapters(),
): VpnConnectionManager {
  const idle = (): VpnConnectionState => ({
    phase: "DISCONNECTED",
    backend: "NONE",
    tunnel: "DOWN",
  });
  let state = idle();
  let details: ConnectionDetails | null = null;
  let owner: string | null = null;
  let active: ConnectionAdapter | null = null;
  let run: { controller: AbortController; done: Promise<void> } | null = null;
  let stopping: Promise<void> | null = null;
  let disposed = false;
  const listeners = new Set<() => void>();
  const emit = (value: VpnConnectionState) => {
    state = value;
    listeners.forEach((listener) => listener());
  };
  const fail = (method: string, code: string) =>
    emit({
      phase: "FAILED",
      backend: "NONE",
      tunnel: "DOWN",
      failure_code: code,
      attempt: { method, previousMethod: null, retry: false },
    });

  const disconnect = async () => {
    if (stopping) return stopping;
    run?.controller.abort();
    // Publish cancellation before waiting for adapter cleanup.
    if (run || active)
      emit({ phase: "DISCONNECTING", backend: "ACTIVE", tunnel: "DOWN" });
    const completion = run?.done;
    stopping = (async () => {
      await completion;
      if (active) {
        await active.disconnect();
        active = null;
      }
      details = null;
      emit(idle());
    })();
    try {
      await stopping;
    } finally {
      stopping = null;
    }
  };

  return {
    current: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    async localTunnelStatus() {
      return active ? "UP" : "DOWN";
    },
    async connectionDetails() {
      return details;
    },
    async reconcile() {},
    setOwner(value) {
      if (owner !== value) {
        owner = value;
        void disconnect().catch(() => fail("", "CLEANUP_FAILED"));
      }
    },
    async connect(_accessToken, selection) {
      if (disposed || run || stopping || active) return;
      const current = {
        controller: new AbortController(),
        done: Promise.resolve(),
      };
      run = current;
      current.done = (async () => {
        let previousMethod: string | null = null;
        let firstFailure: string | null = null;
        for (const adapter of adapters) {
          if (current.controller.signal.aborted) return;
          emit({
            phase: "CONNECTING",
            backend: "NONE",
            tunnel: "DOWN",
            attempt: {
              method: adapter.name,
              previousMethod,
              retry: previousMethod !== null,
            },
          });
          try {
            const result = await adapter.connect(
              selection,
              current.controller.signal,
            );
            if (
              !current.controller.signal.aborted &&
              result.connected &&
              result.internetVerified
            ) {
              active = adapter;
              details = result.details;
              emit({
                phase: "CONNECTED",
                backend: "ACTIVE",
                tunnel: "UP",
                session: result.session ?? {
                  sessionId: adapter.id,
                  countryCode:
                    selection.mode === "COUNTRY"
                      ? selection.country_code
                      : "AUTO",
                  expiresAt: null,
                  remainingSeconds: null,
                },
              });
              return;
            }
          } catch (error) {
            const code =
              error instanceof Error
                ? error.message
                : typeof error === "string"
                  ? error
                  : "";
            if (/^[A-Z_]{1,64}$/.test(code)) firstFailure ??= code;
            /* An individual adapter failure continues after cleanup. */
          }
          try {
            await adapter.disconnect();
          } catch (error) {
            active = adapter;
            throw error;
          }
          if (current.controller.signal.aborted) return;
          previousMethod = adapter.name;
        }
        fail(previousMethod ?? "", firstFailure ?? "METHODS_EXHAUSTED");
      })();
      try {
        await current.done;
      } catch {
        if (!current.controller.signal.aborted)
          fail(
            ("attempt" in state ? state.attempt?.method : "") ?? "",
            "CLEANUP_FAILED",
          );
      } finally {
        if (run === current) run = null;
      }
    },
    disconnect,
    async connectionLost() {
      try {
        await disconnect();
        fail("WireGuard", "VPN_CONNECTION_LOST");
      } catch {
        fail("WireGuard", "CLEANUP_FAILED");
      }
    },
    dispose() {
      disposed = true;
      void disconnect().catch(() => fail("", "CLEANUP_FAILED"));
      listeners.clear();
    },
  };
}
