import {
  ApiError,
  type ActiveVpnSessionResponse,
  type ApiClient,
} from "../api/client";
import type { WireGuardKeyManager } from "../native/wireguardKeys";
import type {
  WireGuardTunnelController,
  WireGuardTunnelState,
} from "../native/wireguardTransport";
import type { VpnLocationSelection } from "./selection";

export interface ConnectedVpnSession {
  readonly sessionId: string;
  readonly countryCode: string;
  readonly expiresAt: string | null;
  readonly remainingSeconds: number | null;
}
export type VpnConnectionState =
  | {
      readonly phase: "RECONCILING" | "CONNECTING";
      readonly backend: "UNKNOWN";
      readonly tunnel: "UNKNOWN";
    }
  | {
      readonly phase: "DISCONNECTING";
      readonly backend: "ACTIVE";
      readonly tunnel: WireGuardTunnelState;
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
      readonly phase: "UNAVAILABLE";
      readonly backend: "ACTIVE" | "NONE" | "UNAVAILABLE";
      readonly tunnel: WireGuardTunnelState | "UNAVAILABLE";
      readonly reason:
        "BACKEND_UNAVAILABLE" | "TUNNEL_UNAVAILABLE" | "CONNECTION_FAILED";
      readonly session?: ConnectedVpnSession;
    };

export interface VpnConnectionManager {
  readonly current: () => VpnConnectionState;
  readonly subscribe: (listener: () => void) => () => void;
  reconcile(accessToken: string): Promise<void>;
  connect(accessToken: string, selection: VpnLocationSelection): Promise<void>;
  disconnect(accessToken: string): Promise<void>;
  dispose(): void;
}

export class VpnConnectionError extends Error {
  constructor(
    readonly code:
      | "CONNECTION_IN_PROGRESS"
      | "COUNTRY_UNAVAILABLE"
      | "VPN_UNAVAILABLE"
      | "LOCAL_TUNNEL_FAILED"
      | "LOCAL_TUNNEL_STOP_FAILED"
      | "CONNECTION_FAILED",
  ) {
    super(code);
    this.name = "VpnConnectionError";
  }
}

export function createVpnConnectionManager(
  api: ApiClient,
  keys: WireGuardKeyManager,
  tunnel: WireGuardTunnelController,
  monitorIntervalMs = 3_000,
): VpnConnectionManager {
  let state: VpnConnectionState = {
    phase: "RECONCILING",
    backend: "UNKNOWN",
    tunnel: "UNKNOWN",
  };
  let generation = 0;
  let desiredConnected = true;
  let inFlight = false;
  let disconnectInFlight: Promise<void> | null = null;
  let timer: ReturnType<typeof setInterval> | undefined;
  let countdownTimer: ReturnType<typeof setInterval> | undefined;
  let expiryTimer: ReturnType<typeof setTimeout> | undefined;
  const listeners = new Set<() => void>();
  const emit = (next: VpnConnectionState) => {
    state = next;
    listeners.forEach((listener) => listener());
  };
  const clearSessionTimers = () => {
    if (countdownTimer !== undefined) clearInterval(countdownTimer);
    if (expiryTimer !== undefined) clearTimeout(expiryTimer);
    countdownTimer = undefined;
    expiryTimer = undefined;
  };
  const monitor = (accessToken: string) => {
    if (timer !== undefined) clearInterval(timer);
    timer = setInterval(
      () => void checkConnection(accessToken),
      monitorIntervalMs,
    );
  };
  const stopMonitor = () => {
    if (timer !== undefined) clearInterval(timer);
    timer = undefined;
  };
  const scheduleBackendCleanup = (
    accessToken: string,
    session: ConnectedVpnSession,
  ) => {
    stopMonitor();
    timer = setInterval(() => {
      void api
        .disconnectVpnSession(accessToken, session.sessionId)
        .then(() => {
          if (
            state.phase === "DISCONNECTED" &&
            state.backend === "UNAVAILABLE" &&
            state.session?.sessionId === session.sessionId
          ) {
            emit({ phase: "DISCONNECTED", backend: "NONE", tunnel: "DOWN" });
            stopMonitor();
          }
        })
        .catch(() => undefined);
    }, monitorIntervalMs);
  };
  const scheduleUnknownBackendCleanup = (accessToken: string) => {
    stopMonitor();
    timer = setInterval(() => {
      void api
        .getCurrentVpnSession(accessToken)
        .then(async ({ session }) => {
          if (session !== null)
            await api.disconnectVpnSession(accessToken, session.session_id);
          if (
            state.phase === "DISCONNECTED" &&
            state.backend === "UNAVAILABLE"
          ) {
            emit({ phase: "DISCONNECTED", backend: "NONE", tunnel: "DOWN" });
            stopMonitor();
          }
        })
        .catch(() => undefined);
    }, monitorIntervalMs);
  };
  const activate = (
    backendSession: ActiveVpnSessionResponse,
    accessToken: string,
  ) => {
    clearSessionTimers();
    const session = productSession(backendSession);
    emit({ phase: "CONNECTED", backend: "ACTIVE", tunnel: "UP", session });
    if (session.remainingSeconds !== null) {
      const deadline = performance.now() + session.remainingSeconds * 1_000;
      countdownTimer = setInterval(() => {
        if (
          state.phase !== "CONNECTED" ||
          state.session.sessionId !== session.sessionId
        )
          return;
        const remainingSeconds = Math.max(
          0,
          Math.ceil((deadline - performance.now()) / 1_000),
        );
        if (remainingSeconds !== state.session.remainingSeconds)
          emit({ ...state, session: { ...state.session, remainingSeconds } });
      }, 1_000);
      expiryTimer = setTimeout(
        () => void manager.disconnect(accessToken),
        session.remainingSeconds * 1_000,
      );
    }
    monitor(accessToken);
  };
  const checkConnection = async (accessToken: string) => {
    if (state.phase !== "CONNECTED") return;
    const observed = state;
    try {
      if ((await tunnel.state()) !== "UP") {
        if (state === observed)
          emit({
            phase: "UNAVAILABLE",
            backend: "ACTIVE",
            tunnel: "DOWN",
            reason: "TUNNEL_UNAVAILABLE",
            session: observed.session,
          });
        return;
      }
    } catch {
      if (state === observed)
        emit({
          phase: "UNAVAILABLE",
          backend: "ACTIVE",
          tunnel: "UNAVAILABLE",
          reason: "TUNNEL_UNAVAILABLE",
          session: observed.session,
        });
      return;
    }
    try {
      const current = await api.getCurrentVpnSession(accessToken);
      if (state !== observed) return;
      if (current.session === null) {
        desiredConnected = false;
        clearSessionTimers();
        await tunnel.stop();
        if (state === observed)
          emit({ phase: "DISCONNECTED", backend: "NONE", tunnel: "DOWN" });
        return;
      }
      activate(current.session, accessToken);
    } catch {
      if (state === observed)
        emit({
          phase: "UNAVAILABLE",
          backend: "UNAVAILABLE",
          tunnel: "UP",
          reason: "BACKEND_UNAVAILABLE",
          session: observed.session,
        });
    }
  };

  const manager: VpnConnectionManager = {
    current: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    async reconcile(accessToken) {
      const run = ++generation;
      emit({ phase: "RECONCILING", backend: "UNKNOWN", tunnel: "UNKNOWN" });
      const [backendResult, tunnelResult] = await Promise.allSettled([
        api.getCurrentVpnSession(accessToken),
        tunnel.state(),
      ]);
      if (run !== generation) return;
      if (backendResult.status === "rejected") {
        emit({
          phase: "UNAVAILABLE",
          backend: "UNAVAILABLE",
          tunnel:
            tunnelResult.status === "fulfilled"
              ? tunnelResult.value
              : "UNAVAILABLE",
          reason: "BACKEND_UNAVAILABLE",
        });
        return;
      }
      const backendSession = backendResult.value.session;
      if (tunnelResult.status === "rejected") {
        emit({
          phase: "UNAVAILABLE",
          backend: backendSession === null ? "NONE" : "ACTIVE",
          tunnel: "UNAVAILABLE",
          reason: "TUNNEL_UNAVAILABLE",
          ...(backendSession === null
            ? {}
            : { session: productSession(backendSession) }),
        });
        return;
      }
      if (backendSession === null) {
        if (tunnelResult.value === "UP") {
          try {
            await tunnel.stop();
          } catch {
            emit({
              phase: "UNAVAILABLE",
              backend: "NONE",
              tunnel: "UNAVAILABLE",
              reason: "TUNNEL_UNAVAILABLE",
            });
            return;
          }
        }
        if (run === generation)
          emit({ phase: "DISCONNECTED", backend: "NONE", tunnel: "DOWN" });
        return;
      }
      if (tunnelResult.value === "DOWN") {
        if (!desiredConnected) {
          try {
            await api.disconnectVpnSession(
              accessToken,
              backendSession.session_id,
            );
            if (run === generation)
              emit({
                phase: "DISCONNECTED",
                backend: "NONE",
                tunnel: "DOWN",
              });
          } catch {
            if (run === generation) {
              const session = productSession(backendSession);
              emit({
                phase: "DISCONNECTED",
                backend: "UNAVAILABLE",
                tunnel: "DOWN",
                session,
              });
              scheduleBackendCleanup(accessToken, session);
            }
          }
          return;
        }
        try {
          await startAndConfirm(tunnel, backendSession);
        } catch {
          if (run === generation)
            emit({
              phase: "UNAVAILABLE",
              backend: "ACTIVE",
              tunnel: "DOWN",
              reason: "TUNNEL_UNAVAILABLE",
              session: productSession(backendSession),
            });
          return;
        }
      }
      if (run === generation) {
        activate(backendSession, accessToken);
      }
    },
    async connect(accessToken, selection) {
      if (inFlight) throw new VpnConnectionError("CONNECTION_IN_PROGRESS");
      desiredConnected = true;
      inFlight = true;
      const run = ++generation;
      const previousTunnel = state.tunnel;
      emit({ phase: "CONNECTING", backend: "UNKNOWN", tunnel: "UNKNOWN" });
      try {
        const publicKey = await keys.ensurePublicKey();
        const backendSession = await api.createVpnSession(
          accessToken,
          selection.mode === "AUTO"
            ? { mode: "AUTO", public_key: publicKey }
            : {
                mode: "COUNTRY",
                country_code: selection.country_code,
                public_key: publicKey,
              },
        );
        try {
          await startAndConfirm(tunnel, backendSession);
        } catch {
          await bestEffortLocalStop(tunnel);
          await bestEffortBackendCleanup(
            api,
            accessToken,
            backendSession.session_id,
          );
          throw new VpnConnectionError("LOCAL_TUNNEL_FAILED");
        }
        if (run === generation) {
          activate(backendSession, accessToken);
        }
      } catch (error) {
        const mapped = mapError(error);
        const backendUnavailable = isBackendUnavailable(error);
        if (run === generation)
          emit({
            phase: "UNAVAILABLE",
            backend: backendUnavailable ? "UNAVAILABLE" : "NONE",
            tunnel:
              previousTunnel === "UNKNOWN" ? "UNAVAILABLE" : previousTunnel,
            reason: backendUnavailable
              ? "BACKEND_UNAVAILABLE"
              : "CONNECTION_FAILED",
          });
        throw mapped;
      } finally {
        inFlight = false;
      }
    },
    disconnect(accessToken) {
      if (disconnectInFlight !== null) return disconnectInFlight;
      if (state.phase === "DISCONNECTED" && state.backend === "NONE") {
        return Promise.resolve();
      }
      desiredConnected = false;
      const session = "session" in state ? state.session : undefined;
      const run = ++generation;
      stopMonitor();
      clearSessionTimers();
      const operation = (async () => {
        emit({
          phase: "DISCONNECTING",
          backend: "ACTIVE",
          tunnel: state.tunnel === "DOWN" ? "DOWN" : "UP",
          ...(session === undefined ? {} : { session }),
        });
        let stopped = false;
        try {
          stopped = (await tunnel.stop()) === "DOWN";
        } catch {
          try {
            stopped = (await tunnel.state()) === "DOWN";
          } catch {
            stopped = false;
          }
        }
        if (!stopped) {
          if (run === generation)
            emit({
              phase: "UNAVAILABLE",
              backend: "ACTIVE",
              tunnel: "UP",
              reason: "TUNNEL_UNAVAILABLE",
              ...(session === undefined ? {} : { session }),
            });
          throw new VpnConnectionError("LOCAL_TUNNEL_STOP_FAILED");
        }

        if (run === generation)
          emit({
            phase: "DISCONNECTING",
            backend: "ACTIVE",
            tunnel: "DOWN",
            ...(session === undefined ? {} : { session }),
          });
        if (session === undefined) {
          if (run === generation) {
            emit({
              phase: "DISCONNECTED",
              backend: "UNAVAILABLE",
              tunnel: "DOWN",
            });
            scheduleUnknownBackendCleanup(accessToken);
          }
          return;
        }
        try {
          await api.disconnectVpnSession(accessToken, session.sessionId);
          if (run === generation)
            emit({ phase: "DISCONNECTED", backend: "NONE", tunnel: "DOWN" });
        } catch {
          if (run === generation) {
            emit({
              phase: "DISCONNECTED",
              backend: "UNAVAILABLE",
              tunnel: "DOWN",
              session,
            });
            scheduleBackendCleanup(accessToken, session);
          }
        }
      })().finally(() => {
        disconnectInFlight = null;
      });
      disconnectInFlight = operation;
      return operation;
    },
    dispose() {
      generation += 1;
      stopMonitor();
      clearSessionTimers();
      listeners.clear();
    },
  };
  return manager;
}

function productSession(
  session: ActiveVpnSessionResponse,
): ConnectedVpnSession {
  return {
    sessionId: session.session_id,
    countryCode: session.country_code,
    expiresAt: session.expires_at,
    remainingSeconds:
      session.expires_at === null
        ? null
        : Math.max(
            0,
            Math.ceil(
              (Date.parse(session.expires_at) -
                Date.parse(session.server_time)) /
                1_000,
            ),
          ),
  };
}
async function startAndConfirm(
  tunnel: WireGuardTunnelController,
  session: ActiveVpnSessionResponse,
) {
  await tunnel.start({
    endpoint: session.transport.endpoint,
    serverPublicKey: session.transport.server_public_key,
    clientAddress: session.transport.client_address,
    dns: session.transport.dns,
    allowedIps: session.transport.allowed_ips,
  });
  if ((await tunnel.state()) !== "UP")
    throw new Error("native tunnel did not reach UP");
}
function mapError(error: unknown) {
  if (error instanceof VpnConnectionError) return error;
  if (
    error instanceof ApiError &&
    (error.code === "COUNTRY_UNAVAILABLE" || error.code === "VPN_UNAVAILABLE")
  )
    return new VpnConnectionError(error.code);
  return new VpnConnectionError("CONNECTION_FAILED");
}
function isBackendUnavailable(error: unknown) {
  return (
    error instanceof ApiError &&
    ["NETWORK_ERROR", "TIMEOUT", "SERVER_ERROR"].includes(error.code)
  );
}
async function bestEffortLocalStop(tunnel: WireGuardTunnelController) {
  try {
    await tunnel.stop();
  } catch {
    /* Native startup also rolls back transient state. */
  }
}
async function bestEffortBackendCleanup(
  api: ApiClient,
  accessToken: string,
  sessionId: string,
) {
  try {
    await api.disconnectVpnSession(accessToken, sessionId);
  } catch {
    /* Durable expiry is the safety net. */
  }
}
