import { isTerminalVpnFailure } from "./sessionAdapter";
import {
  RemoteCleanupPending,
  type ConnectionAdapter,
  type ProtocolStatus,
} from "./protocol";
import type { VpnLocationSelection } from "./selection";
import type { ConnectionDetails } from "./connectionDetails";
import type { ConnectionAttempt } from "./attempt";
import { createMethodPreference } from "./methodPreference";

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
      readonly backend: "NONE" | "PENDING" | "UNAVAILABLE";
      readonly tunnel: "DOWN";
      readonly session?: ConnectedVpnSession;
      readonly failure_code?: string;
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
  resetMethods?(
    accessToken: string,
    selection: VpnLocationSelection,
  ): Promise<void>;
  setOwner?(owner: string | null): void;
  dispose(): void;
  connectionLost?(code?: string): Promise<void>;
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

/** Every native adapter shares the sequential executor and confirmed cleanup boundary. */
export function createVpnConnectionManager(
  adapters: readonly ConnectionAdapter[],
  preference = createMethodPreference(),
  enabledMethods: () => readonly string[] | null = () => null,
  beforeConnect?: (signal: AbortSignal) => Promise<void>,
): VpnConnectionManager {
  const idle = (): Extract<VpnConnectionState, { phase: "DISCONNECTED" }> => ({
    phase: "DISCONNECTED",
    backend: "NONE",
    tunnel: "DOWN",
  });
  let state: VpnConnectionState = idle();
  let details: ConnectionDetails | null = null;
  let owner: string | null = null;
  let active: ConnectionAdapter | null = null;
  let run: { controller: AbortController; done: Promise<void> } | null = null;
  let stopping: Promise<void> | null = null;
  let disposed = false;
  let intentRevision = 0;
  let recoveredOwner: string | null = null;
  const listeners = new Set<() => void>();
  const emit = (value: VpnConnectionState) => {
    state = value;
    listeners.forEach((listener) => listener());
  };
  const fail = (method: string, code: string) =>
    emit({
      phase: "FAILED",
      backend: "NONE",
      tunnel: code === "CLEANUP_FAILED" ? "UNAVAILABLE" : "DOWN",
      failure_code: code,
      attempt: { method, previousMethod: null, retry: false },
    });
  const localStopped = (reason?: string) => {
    details = null;
    emit({
      phase: "DISCONNECTED",
      backend: "PENDING",
      tunnel: "DOWN",
      failure_code: reason,
    });
  };
  const cleanupFailed = (error: unknown, method = "") => {
    if (error instanceof RemoteCleanupPending) {
      details = null;
      emit({ phase: "DISCONNECTED", backend: "UNAVAILABLE", tunnel: "DOWN" });
    } else fail(method, "CLEANUP_FAILED");
  };

  const disconnect = async (reason?: string) => {
    run?.controller.abort();
    if (stopping) return stopping;
    // Publish cancellation before waiting for adapter cleanup.
    if ((run || active) && state.phase !== "DISCONNECTED")
      emit({
        phase: "DISCONNECTING",
        backend: "ACTIVE",
        tunnel: state.tunnel === "DOWN" ? "DOWN" : "UP",
      });
    const completion = run?.done;
    stopping = (async () => {
      await completion;
      if (active) {
        await active.disconnect(() => localStopped(reason));
        active = null;
      }
      details = null;
      emit(idle());
    })();
    try {
      await stopping;
    } catch (error) {
      cleanupFailed(error);
      throw error;
    } finally {
      stopping = null;
    }
  };

  const manager: VpnConnectionManager = {
    current: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    async localTunnelStatus() {
      return active && state.tunnel !== "DOWN" ? "UP" : "DOWN";
    },
    async connectionDetails() {
      return details;
    },
    async reconcile() {
      if (
        !owner ||
        recoveredOwner === owner ||
        active ||
        run ||
        stopping ||
        disposed
      )
        return;
      const adapter = adapters.find((item) => item.recover);
      if (!adapter) return;
      active = adapter;
      const account = owner;
      emit({ phase: "RECONCILING", backend: "UNKNOWN", tunnel: "UNKNOWN" });
      stopping = (async () => {
        try {
          await adapter.recover!(localStopped);
          active = null;
          recoveredOwner = account;
          emit(idle());
        } catch (error) {
          cleanupFailed(error, adapter.name);
        } finally {
          stopping = null;
        }
      })();
      await stopping;
    },
    setOwner(value) {
      if (owner !== value) {
        intentRevision++;
        owner = value;
        void disconnect().catch(() => {}); // disconnect publishes the precise failure.
      }
    },
    async connect(_accessToken, selection) {
      if (
        disposed ||
        run ||
        ((stopping || active) && state.phase !== "DISCONNECTED")
      )
        return;
      intentRevision++;
      const pendingStop = stopping;
      const current = {
        controller: new AbortController(),
        done: Promise.resolve(),
      };
      run = current;
      current.done = (async () => {
        // Reconnect may retry remote cleanup, but may not allocate a second grant.
        if (pendingStop) await pendingStop.catch(() => {});
        if (current.controller.signal.aborted) return;
        if (active) {
          await active.disconnect(localStopped);
          active = null;
        }
        if (beforeConnect) {
          emit({ phase: "CONNECTING", backend: "NONE", tunnel: "DOWN" });
          try {
            await beforeConnect(current.controller.signal);
          } catch (error) {
            if (!current.controller.signal.aborted)
              fail(
                "",
                typeof error === "string" && /^[A-Z_]{1,64}$/.test(error)
                  ? error
                  : "VPN_CONFLICT",
              );
            return;
          }
        }
        let previousMethod: string | null = null;
        let firstFailure: string | null = null;
        const preferred = preference.current();
        const enabled = enabledMethods();
        const allowed = adapters.filter(
          (adapter) => enabled === null || enabled.includes(adapter.id),
        );
        if (enabled)
          allowed.sort((a, b) => enabled.indexOf(a.id) - enabled.indexOf(b.id));
        const ordered = [
          ...allowed.filter((adapter) => adapter.id === preferred),
          ...allowed.filter((adapter) => adapter.id !== preferred),
        ];
        for (const adapter of ordered) {
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
          let attemptFailure: string | null = null;
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
              preference.remember(adapter.id);
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
            if (/^[A-Z_]{1,64}$/.test(code)) {
              firstFailure ??= code;
              attemptFailure = code;
            }
            /* An individual adapter failure continues after cleanup. */
          }
          try {
            await adapter.disconnect(() => {
              if (current.controller.signal.aborted) localStopped();
            });
          } catch (error) {
            active = adapter;
            throw error;
          }
          if (current.controller.signal.aborted) return;
          if (attemptFailure && isTerminalVpnFailure(attemptFailure)) {
            fail(adapter.name, attemptFailure);
            return;
          }
          previousMethod = adapter.name;
        }
        fail(previousMethod ?? "", firstFailure ?? "METHODS_EXHAUSTED");
      })();
      try {
        await current.done;
      } catch (error) {
        cleanupFailed(
          error,
          ("attempt" in state ? state.attempt?.method : "") ?? "",
        );
      } finally {
        if (run === current) run = null;
      }
    },
    disconnect() {
      intentRevision++;
      return disconnect();
    },
    async resetMethods(accessToken, selection) {
      if (disposed || run || stopping) return;
      const revision = ++intentRevision;
      const expectedOwner = owner;
      preference.clear();
      await disconnect();
      if (revision === intentRevision && owner === expectedOwner && !disposed)
        await manager.connect(accessToken, selection);
    },
    async connectionLost(code = "VPN_CONNECTION_LOST") {
      if (run || !active) return;
      const method = active.name;
      const revision = intentRevision;
      try {
        await disconnect(code);
        if (revision !== intentRevision) return;
        if (["VPN_CONNECTION_LOST", "VPN_SERVER_UNAVAILABLE"].includes(code))
          emit({ ...idle(), failure_code: code });
        else fail(method, code);
      } catch {
        // disconnect already distinguishes remote cleanup from a local failure.
      }
    },
    dispose() {
      intentRevision++;
      disposed = true;
      void disconnect().catch(() => {});
      listeners.clear();
    },
  };
  return manager;
}
