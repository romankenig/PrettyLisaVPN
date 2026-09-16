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
}
export type VpnConnectionState =
  | {
      readonly phase: "RECONCILING" | "CONNECTING";
      readonly backend: "UNKNOWN";
      readonly tunnel: "UNKNOWN";
    }
  | {
      readonly phase: "DISCONNECTED";
      readonly backend: "NONE";
      readonly tunnel: "DOWN";
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
  dispose(): void;
}

export class VpnConnectionError extends Error {
  constructor(
    readonly code:
      | "CONNECTION_IN_PROGRESS"
      | "COUNTRY_UNAVAILABLE"
      | "VPN_UNAVAILABLE"
      | "LOCAL_TUNNEL_FAILED"
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
  let inFlight = false;
  let timer: ReturnType<typeof setInterval> | undefined;
  const listeners = new Set<() => void>();
  const emit = (next: VpnConnectionState) => {
    state = next;
    listeners.forEach((listener) => listener());
  };
  const monitor = () => {
    if (timer !== undefined) clearInterval(timer);
    timer = setInterval(() => void checkNative(), monitorIntervalMs);
  };
  const checkNative = async () => {
    if (state.phase !== "CONNECTED") return;
    const observed = state;
    try {
      if ((await tunnel.state()) === "UP") return;
      if (state === observed)
        emit({
          phase: "UNAVAILABLE",
          backend: "ACTIVE",
          tunnel: "DOWN",
          reason: "TUNNEL_UNAVAILABLE",
          session: observed.session,
        });
    } catch {
      if (state === observed)
        emit({
          phase: "UNAVAILABLE",
          backend: "ACTIVE",
          tunnel: "UNAVAILABLE",
          reason: "TUNNEL_UNAVAILABLE",
          session: observed.session,
        });
    }
  };

  return {
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
        emit({
          phase: "CONNECTED",
          backend: "ACTIVE",
          tunnel: "UP",
          session: productSession(backendSession),
        });
        monitor();
      }
    },
    async connect(accessToken, selection) {
      if (inFlight) throw new VpnConnectionError("CONNECTION_IN_PROGRESS");
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
          emit({
            phase: "CONNECTED",
            backend: "ACTIVE",
            tunnel: "UP",
            session: productSession(backendSession),
          });
          monitor();
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
    dispose() {
      generation += 1;
      if (timer !== undefined) clearInterval(timer);
      timer = undefined;
      listeners.clear();
    },
  };
}

function productSession(
  session: ActiveVpnSessionResponse,
): ConnectedVpnSession {
  return {
    sessionId: session.session_id,
    countryCode: session.country_code,
    expiresAt: session.expires_at,
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
