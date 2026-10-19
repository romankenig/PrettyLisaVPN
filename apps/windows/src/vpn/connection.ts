import { checkHealth } from "./verification";
import {
  ApiError,
  type ActiveVpnSessionResponse,
  type ApiClient,
} from "../api/client";
import {
  connectFirstCandidate,
  isVerified,
  type ProtocolFailure,
  type VerificationPhase,
  ProtocolConnectionError,
  type VpnProtocol,
  type VpnSessionProvisioner,
  type ProtocolStatus,
} from "./protocol";
import type { VpnLocationSelection } from "./selection";
import type { ConnectionDetails } from "./connectionDetails";

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
      readonly session: ConnectedVpnSession;
      readonly failure_code?: ProtocolFailure;
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
  dispose(): void;
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
      | ProtocolFailure,
  ) {
    super(code);
    this.name = "VpnConnectionError";
  }
}

export function createVpnConnectionManager(
  api: ApiClient,
  provisioner: VpnSessionProvisioner,
  tunnel: VpnProtocol,
  monitorIntervalMs = 30_000,
): VpnConnectionManager {
  let state: VpnConnectionState = {
    phase: "RECONCILING",
    backend: "UNKNOWN",
    tunnel: "UNKNOWN",
  };
  let generation = 0;
  let desiredConnected = true;
  let inFlight = false;
  let checking = false;
  let healthFailures = 0;
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
          (state.phase !== "CONNECTED" && state.phase !== "DEGRADED") ||
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
  const progress =
    (run: number, session: ActiveVpnSessionResponse) =>
    (phase: VerificationPhase) => {
      if (run === generation)
        emit({
          phase,
          backend: "ACTIVE",
          tunnel: "UP",
          session: productSession(session),
        });
    };
  const fail = async (
    accessToken: string,
    session: ConnectedVpnSession,
    code: ProtocolFailure,
    run: number,
  ) => {
    if (run !== generation) return;
    inFlight = true;
    stopMonitor();
    clearSessionTimers();
    emit({
      phase: "FAILED",
      backend: "ACTIVE",
      tunnel: "UP",
      session,
      failure_code: code,
    });
    let down = false;
    try {
      down = (await tunnel.disconnect()) === "DOWN";
    } catch {
      /* Keep teardown available. */
    }
    let backend: "NONE" | "UNAVAILABLE" = "NONE";
    try {
      await api.disconnectVpnSession(accessToken, session.sessionId);
    } catch {
      backend = "UNAVAILABLE";
    }
    if (run === generation)
      emit({
        phase: "FAILED",
        backend,
        tunnel: down ? "DOWN" : "UNAVAILABLE",
        session,
        failure_code: code,
      });
    inFlight = false;
  };
  const verifyExisting = async (
    run: number,
    session: ActiveVpnSessionResponse,
  ) => {
    progress(run, session)("TUNNEL_ESTABLISHED");
    progress(run, session)("VERIFYING_INTERNET");
    const result = await checkHealth(tunnel);
    if (!isVerified(result))
      throw new ProtocolConnectionError(
        result.failure_code ?? "TUNNEL_ESTABLISHED_NO_TRAFFIC",
      );
  };
  const checkConnection = async (accessToken: string) => {
    if (checking || (state.phase !== "CONNECTED" && state.phase !== "DEGRADED"))
      return;
    checking = true;
    const run = generation;
    const session = state.session;
    try {
      let result;
      try {
        result = await checkHealth(tunnel);
      } catch {
        result = null;
      }
      if (run !== generation) return;
      if (!result || !isVerified(result)) {
        const code = result?.failure_code ?? "UNKNOWN";
        healthFailures += 1;
        if (
          healthFailures >= 3 ||
          code === "ROUTE_LEAK_DETECTED" ||
          code === "EGRESS_MISMATCH" ||
          result?.tunnel_established === false
        ) {
          await fail(accessToken, session, code, run);
        } else {
          emit({
            phase: "DEGRADED",
            backend: "ACTIVE",
            tunnel: "UP",
            session,
            failure_code: code,
          });
        }
        return;
      }
      try {
        const current = await api.getCurrentVpnSession(accessToken);
        if (run !== generation) return;
        if (current.session === null) {
          await manager.disconnect(accessToken);
          return;
        }
        healthFailures = 0;
        activate(current.session, accessToken);
      } catch {
        if (run !== generation) return;
        healthFailures += 1;
        if (healthFailures >= 3) {
          await fail(accessToken, session, "SERVER_UNREACHABLE", run);
          return;
        }
        if (run === generation)
          emit({
            phase: "DEGRADED",
            backend: "UNAVAILABLE",
            tunnel: "UP",
            session,
            failure_code: "SERVER_UNREACHABLE",
          });
      }
    } finally {
      checking = false;
    }
  };

  const manager: VpnConnectionManager = {
    async connectionDetails() {
      if (state.phase !== "CONNECTED" || !tunnel.connectionDetails) return null;
      const sessionId = state.session.sessionId;
      try {
        const details = await tunnel.connectionDetails();
        return state.phase === "CONNECTED" &&
          state.session.sessionId === sessionId
          ? details
          : null;
      } catch {
        return null;
      }
    },
    localTunnelStatus: () => tunnel.status(),
    current: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    async reconcile(accessToken) {
      if (inFlight) return;
      healthFailures = 0;
      const run = ++generation;
      stopMonitor();
      clearSessionTimers();
      emit({ phase: "RECONCILING", backend: "UNKNOWN", tunnel: "UNKNOWN" });
      const [backendResult, tunnelResult] = await Promise.allSettled([
        api.getCurrentVpnSession(accessToken),
        tunnel.status(),
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
            await tunnel.disconnect();
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
          await connectFirstCandidate(
            tunnel,
            provisioner.candidates(backendSession),
            progress(run, backendSession),
          );
        } catch (error) {
          if (run === generation)
            await fail(
              accessToken,
              productSession(backendSession),
              error instanceof ProtocolConnectionError ? error.code : "UNKNOWN",
              run,
            );
          return;
        }
      } else {
        try {
          await verifyExisting(run, backendSession);
        } catch (error) {
          if (run === generation)
            await fail(
              accessToken,
              productSession(backendSession),
              error instanceof ProtocolConnectionError ? error.code : "UNKNOWN",
              run,
            );
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
      healthFailures = 0;
      stopMonitor();
      clearSessionTimers();
      emit({ phase: "CONNECTING", backend: "UNKNOWN", tunnel: "UNKNOWN" });
      try {
        const backendSession = await provisioner.create(accessToken, selection);
        if (run !== generation) {
          await api
            .disconnectVpnSession(accessToken, backendSession.session_id)
            .catch(() => undefined);
          return;
        }
        try {
          await connectFirstCandidate(
            tunnel,
            provisioner.candidates(backendSession),
            progress(run, backendSession),
          );
        } catch (error) {
          const code =
            error instanceof ProtocolConnectionError ? error.code : "UNKNOWN";
          if (run === generation)
            await fail(accessToken, productSession(backendSession), code, run);
          throw new VpnConnectionError(code);
        }

        if (run !== generation) {
          await tunnel.disconnect().catch(() => undefined);
          await api
            .disconnectVpnSession(accessToken, backendSession.session_id)
            .catch(() => undefined);
          return;
        }
        if (run === generation) {
          activate(backendSession, accessToken);
        }
      } catch (error) {
        const mapped = mapError(error);
        const backendUnavailable = isBackendUnavailable(error);
        if (run === generation && state.phase !== "FAILED")
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
          stopped = (await tunnel.disconnect()) === "DOWN";
        } catch {
          try {
            stopped = (await tunnel.status()) === "DOWN";
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
