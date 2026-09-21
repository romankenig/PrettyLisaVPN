import {
  createWireGuardProtocol,
  createWireGuardProvisioner,
} from "../vpn/wireguard";
import { describe, expect, it, vi } from "vitest";
import {
  ApiError,
  type ActiveVpnSessionResponse,
  type ApiClient,
} from "../api/client";
import type { WireGuardKeyManager } from "../native/wireguardKeys";
import {
  WireGuardTunnelError,
  type WireGuardTunnelController,
} from "../native/wireguardTransport";
import {
  createVpnConnectionManager,
  VpnConnectionError,
} from "../vpn/connection";

const PUBLIC_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
const backendSession: ActiveVpnSessionResponse = {
  session_id: "123e4567-e89b-42d3-a456-426614174020",
  status: "ACTIVE",
  country_code: "DE",
  expires_at: "2026-09-16T10:15:00Z",
  server_time: "2026-09-16T10:00:00Z",
  transport: {
    endpoint: { ipv4: "204.48.17.50", port: 51820 },
    server_public_key: "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE=",
    client_address: "10.77.0.2/32",
    dns: ["1.1.1.1"],
    allowed_ips: ["0.0.0.0/0"],
  },
};

function dependencies() {
  const api = {
    getCurrentVpnSession: vi.fn().mockResolvedValue({ session: null }),
    createVpnSession: vi.fn().mockResolvedValue(backendSession),
    disconnectVpnSession: vi.fn().mockResolvedValue({
      session_id: backendSession.session_id,
      status: "DISCONNECTED",
    }),
  } as unknown as ApiClient;
  const keys: WireGuardKeyManager = {
    ensurePublicKey: vi.fn().mockResolvedValue(PUBLIC_KEY),
    loadPublicKey: vi.fn(),
    delete: vi.fn(),
  };
  const tunnel: WireGuardTunnelController = {
    start: vi.fn().mockResolvedValue("UP"),
    stop: vi.fn().mockResolvedValue("DOWN"),
    state: vi.fn().mockResolvedValue("UP"),
    diagnostics: vi.fn().mockResolvedValue(null),
  };
  return { api, keys, tunnel };
}

describe("Windows VPN connection orchestration", () => {
  it("connects AUTO using only the local public key and confirms native UP", async () => {
    const { api, keys, tunnel } = dependencies();
    const connection = createVpnConnectionManager(
      api,
      createWireGuardProvisioner(api, keys),
      createWireGuardProtocol(tunnel),
      60_000,
    );

    await expect(
      connection.connect("access-token", { mode: "AUTO" }),
    ).resolves.toBeUndefined();
    expect(connection.current()).toMatchObject({
      phase: "CONNECTED",
      backend: "ACTIVE",
      tunnel: "UP",
    });
    expect(api.createVpnSession).toHaveBeenCalledWith("access-token", {
      mode: "AUTO",
      public_key: PUBLIC_KEY,
    });
    expect(
      JSON.stringify(vi.mocked(api.createVpnSession).mock.calls),
    ).not.toContain("private");
    expect(tunnel.start).toHaveBeenCalledWith({
      endpoint: backendSession.transport.endpoint,
      serverPublicKey: backendSession.transport.server_public_key,
      clientAddress: backendSession.transport.client_address,
      dns: backendSession.transport.dns,
      allowedIps: backendSession.transport.allowed_ips,
    });
    expect(tunnel.state).toHaveBeenCalledOnce();
    expect(api.disconnectVpnSession).not.toHaveBeenCalled();
  });

  it("preserves COUNTRY targeting without selecting a node in React", async () => {
    const { api, keys, tunnel } = dependencies();
    const connection = createVpnConnectionManager(
      api,
      createWireGuardProvisioner(api, keys),
      createWireGuardProtocol(tunnel),
      60_000,
    );

    await connection.connect("access-token", {
      mode: "COUNTRY",
      country_code: "DE",
    });

    expect(api.createVpnSession).toHaveBeenCalledWith("access-token", {
      mode: "COUNTRY",
      country_code: "DE",
      public_key: PUBLIC_KEY,
    });
  });

  it.each([
    ["COUNTRY_UNAVAILABLE", { mode: "COUNTRY", country_code: "DE" } as const],
    ["VPN_UNAVAILABLE", { mode: "AUTO" } as const],
  ] as const)(
    "does not touch local networking when backend returns %s",
    async (code, selection) => {
      const { api, keys, tunnel } = dependencies();
      vi.mocked(api.createVpnSession).mockRejectedValue(new ApiError(code));
      const connection = createVpnConnectionManager(
        api,
        createWireGuardProvisioner(api, keys),
        createWireGuardProtocol(tunnel),
        60_000,
      );

      await expect(
        connection.connect("access-token", selection),
      ).rejects.toEqual(new VpnConnectionError(code));
      expect(tunnel.start).not.toHaveBeenCalled();
      expect(tunnel.state).not.toHaveBeenCalled();
      expect(tunnel.stop).not.toHaveBeenCalled();
    },
  );

  it("cleans up backend and local state when native startup fails", async () => {
    const { api, keys, tunnel } = dependencies();
    vi.mocked(tunnel.start).mockRejectedValue(new Error("native failure"));
    const connection = createVpnConnectionManager(
      api,
      createWireGuardProvisioner(api, keys),
      createWireGuardProtocol(tunnel),
      60_000,
    );

    await expect(
      connection.connect("access-token", { mode: "AUTO" }),
    ).rejects.toEqual(new VpnConnectionError("LOCAL_TUNNEL_FAILED"));
    expect(tunnel.stop).toHaveBeenCalledOnce();
    expect(api.disconnectVpnSession).toHaveBeenCalledWith(
      "access-token",
      backendSession.session_id,
    );
  });

  it("reports when another network filter intercepts the VPN data plane", async () => {
    const { api, keys, tunnel } = dependencies();
    vi.mocked(tunnel.start).mockRejectedValue(
      new WireGuardTunnelError("wireguard_data_plane_unavailable"),
    );
    const connection = createVpnConnectionManager(
      api,
      createWireGuardProvisioner(api, keys),
      createWireGuardProtocol(tunnel),
      60_000,
    );

    await expect(
      connection.connect("access-token", { mode: "AUTO" }),
    ).rejects.toEqual(new VpnConnectionError("VPN_TRAFFIC_INTERCEPTED"));
    expect(tunnel.stop).toHaveBeenCalledOnce();
    expect(api.disconnectVpnSession).toHaveBeenCalledWith(
      "access-token",
      backendSession.session_id,
    );
  });

  it("does not report success when native state confirmation is DOWN", async () => {
    const { api, keys, tunnel } = dependencies();
    vi.mocked(tunnel.state).mockResolvedValue("DOWN");
    const connection = createVpnConnectionManager(
      api,
      createWireGuardProvisioner(api, keys),
      createWireGuardProtocol(tunnel),
      60_000,
    );

    await expect(
      connection.connect("access-token", { mode: "AUTO" }),
    ).rejects.toEqual(new VpnConnectionError("LOCAL_TUNNEL_FAILED"));
    expect(api.disconnectVpnSession).toHaveBeenCalledOnce();
  });

  it("rejects duplicate attempts while setup is in progress", async () => {
    const { api, keys, tunnel } = dependencies();
    let resolveKey!: (key: string) => void;
    vi.mocked(keys.ensurePublicKey).mockImplementation(
      () => new Promise((resolve) => (resolveKey = resolve)),
    );
    const connection = createVpnConnectionManager(
      api,
      createWireGuardProvisioner(api, keys),
      createWireGuardProtocol(tunnel),
      60_000,
    );
    const first = connection.connect("access-token", { mode: "AUTO" });

    await expect(
      connection.connect("access-token", { mode: "AUTO" }),
    ).rejects.toEqual(new VpnConnectionError("CONNECTION_IN_PROGRESS"));
    resolveKey(PUBLIC_KEY);
    await first;
    expect(api.createVpnSession).toHaveBeenCalledOnce();
  });

  it("recovers a backend session after application restart", async () => {
    const { api, keys, tunnel } = dependencies();
    vi.mocked(api.getCurrentVpnSession).mockResolvedValue({
      session: backendSession,
    });
    vi.mocked(tunnel.state)
      .mockResolvedValueOnce("DOWN")
      .mockResolvedValueOnce("UP");
    const connection = createVpnConnectionManager(
      api,
      createWireGuardProvisioner(api, keys),
      createWireGuardProtocol(tunnel),
      60_000,
    );

    await connection.reconcile("access-token");

    expect(tunnel.start).toHaveBeenCalledOnce();
    expect(connection.current()).toMatchObject({
      phase: "CONNECTED",
      backend: "ACTIVE",
      tunnel: "UP",
    });
  });

  it("distinguishes backend unavailability from a native tunnel failure", async () => {
    const first = dependencies();
    vi.mocked(first.api.getCurrentVpnSession).mockRejectedValue(
      new ApiError("NETWORK_ERROR"),
    );
    const backendUnavailable = createVpnConnectionManager(
      first.api,
      createWireGuardProvisioner(first.api, first.keys),
      createWireGuardProtocol(first.tunnel),
      60_000,
    );
    await backendUnavailable.reconcile("access-token");
    expect(backendUnavailable.current()).toMatchObject({
      phase: "UNAVAILABLE",
      reason: "BACKEND_UNAVAILABLE",
      tunnel: "UP",
    });

    const second = dependencies();
    vi.mocked(second.api.getCurrentVpnSession).mockResolvedValue({
      session: backendSession,
    });
    vi.mocked(second.tunnel.state).mockRejectedValue(
      new Error("native unavailable"),
    );
    const tunnelUnavailable = createVpnConnectionManager(
      second.api,
      createWireGuardProvisioner(second.api, second.keys),
      createWireGuardProtocol(second.tunnel),
      60_000,
    );
    await tunnelUnavailable.reconcile("access-token");
    expect(tunnelUnavailable.current()).toMatchObject({
      phase: "UNAVAILABLE",
      reason: "TUNNEL_UNAVAILABLE",
      backend: "ACTIVE",
    });
  });

  it("detects unexpected native termination without reporting Connected", async () => {
    vi.useFakeTimers();
    const { api, keys, tunnel } = dependencies();
    const connection = createVpnConnectionManager(
      api,
      createWireGuardProvisioner(api, keys),
      createWireGuardProtocol(tunnel),
      100,
    );
    await connection.connect("access-token", { mode: "AUTO" });
    vi.mocked(tunnel.state).mockResolvedValue("DOWN");

    await vi.advanceTimersByTimeAsync(100);

    expect(connection.current()).toMatchObject({
      phase: "UNAVAILABLE",
      reason: "TUNNEL_UNAVAILABLE",
      backend: "ACTIVE",
      tunnel: "DOWN",
    });
    connection.dispose();
    vi.useRealTimers();
  });

  it("ignores a stale restart reconciliation after a newer connect wins the race", async () => {
    const { api, keys, tunnel } = dependencies();
    let resolveCurrent!: (value: { session: null }) => void;
    vi.mocked(api.getCurrentVpnSession).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCurrent = resolve;
        }),
    );
    const connection = createVpnConnectionManager(
      api,
      createWireGuardProvisioner(api, keys),
      createWireGuardProtocol(tunnel),
      60_000,
    );
    const stale = connection.reconcile("access-token");
    await connection.connect("access-token", { mode: "AUTO" });
    resolveCurrent({ session: null });
    await stale;

    expect(connection.current()).toMatchObject({ phase: "CONNECTED" });
  });

  it("stops the native tunnel before terminating the backend session", async () => {
    const { api, keys, tunnel } = dependencies();
    const connection = createVpnConnectionManager(
      api,
      createWireGuardProvisioner(api, keys),
      createWireGuardProtocol(tunnel),
      60_000,
    );
    await connection.connect("access-token", { mode: "AUTO" });

    await connection.disconnect("access-token");

    expect(tunnel.stop).toHaveBeenCalledOnce();
    expect(api.disconnectVpnSession).toHaveBeenCalledWith(
      "access-token",
      backendSession.session_id,
    );
    expect(vi.mocked(tunnel.stop).mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(api.disconnectVpnSession).mock.invocationCallOrder[0],
    );
    expect(connection.current()).toEqual({
      phase: "DISCONNECTED",
      backend: "NONE",
      tunnel: "DOWN",
    });
  });

  it("stays locally disconnected and retries backend cleanup after an outage", async () => {
    vi.useFakeTimers();
    const { api, keys, tunnel } = dependencies();
    vi.mocked(api.disconnectVpnSession)
      .mockRejectedValueOnce(new ApiError("NETWORK_ERROR"))
      .mockResolvedValue({
        session_id: backendSession.session_id,
        status: "DISCONNECTED",
      });
    const connection = createVpnConnectionManager(
      api,
      createWireGuardProvisioner(api, keys),
      createWireGuardProtocol(tunnel),
      100,
    );
    await connection.connect("access-token", { mode: "AUTO" });

    await connection.disconnect("access-token");
    expect(connection.current()).toMatchObject({
      phase: "DISCONNECTED",
      backend: "UNAVAILABLE",
      tunnel: "DOWN",
    });

    await vi.advanceTimersByTimeAsync(100);
    expect(api.disconnectVpnSession).toHaveBeenCalledTimes(2);
    expect(connection.current()).toEqual({
      phase: "DISCONNECTED",
      backend: "NONE",
      tunnel: "DOWN",
    });
    connection.dispose();
    vi.useRealTimers();
  });

  it("does not remove the backend peer when local tunnel stop cannot be confirmed", async () => {
    const { api, keys, tunnel } = dependencies();
    const connection = createVpnConnectionManager(
      api,
      createWireGuardProvisioner(api, keys),
      createWireGuardProtocol(tunnel),
      60_000,
    );
    await connection.connect("access-token", { mode: "AUTO" });
    vi.mocked(tunnel.stop).mockRejectedValue(new Error("stop failed"));
    vi.mocked(tunnel.state).mockResolvedValue("UP");

    await expect(connection.disconnect("access-token")).rejects.toEqual(
      new VpnConnectionError("LOCAL_TUNNEL_STOP_FAILED"),
    );

    expect(api.disconnectVpnSession).not.toHaveBeenCalled();
    expect(connection.current()).toMatchObject({
      phase: "UNAVAILABLE",
      backend: "ACTIVE",
      tunnel: "UP",
    });
  });

  it("coalesces duplicate disconnect requests into one operation", async () => {
    const { api, keys, tunnel } = dependencies();
    const connection = createVpnConnectionManager(
      api,
      createWireGuardProvisioner(api, keys),
      createWireGuardProtocol(tunnel),
      60_000,
    );
    await connection.connect("access-token", { mode: "AUTO" });
    let finishStop!: () => void;
    vi.mocked(tunnel.stop).mockImplementation(
      () =>
        new Promise((resolve) => {
          finishStop = () => resolve("DOWN");
        }),
    );

    const first = connection.disconnect("access-token");
    const second = connection.disconnect("access-token");
    expect(first).toBe(second);
    finishStop();
    await Promise.all([first, second]);

    expect(tunnel.stop).toHaveBeenCalledOnce();
    expect(api.disconnectVpnSession).toHaveBeenCalledOnce();
  });

  it("derives the FREE countdown from server time despite Windows clock skew", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2035-01-01T00:00:00Z"));
    const { api, keys, tunnel } = dependencies();
    const connection = createVpnConnectionManager(
      api,
      createWireGuardProvisioner(api, keys),
      createWireGuardProtocol(tunnel),
      2_000_000,
    );

    await connection.connect("access-token", { mode: "AUTO" });
    expect(connection.current()).toMatchObject({
      phase: "CONNECTED",
      session: { remainingSeconds: 900 },
    });
    vi.setSystemTime(new Date("1999-01-01T00:00:00Z"));
    await vi.advanceTimersByTimeAsync(1_000);
    expect(connection.current()).toMatchObject({
      phase: "CONNECTED",
      session: { remainingSeconds: 899 },
    });
    connection.dispose();
    vi.useRealTimers();
  });

  it("stops an expired tunnel promptly after a sleep-sized timer jump without granting another session", async () => {
    vi.useFakeTimers();
    const { api, keys, tunnel } = dependencies();
    const connection = createVpnConnectionManager(
      api,
      createWireGuardProvisioner(api, keys),
      createWireGuardProtocol(tunnel),
      2_000_000,
    );
    await connection.connect("access-token", { mode: "AUTO" });

    await vi.advanceTimersByTimeAsync(900_000);

    expect(tunnel.stop).toHaveBeenCalledOnce();
    expect(api.disconnectVpnSession).toHaveBeenCalledWith(
      "access-token",
      backendSession.session_id,
    );
    expect(api.createVpnSession).toHaveBeenCalledOnce();
    expect(connection.current()).toEqual({
      phase: "DISCONNECTED",
      backend: "NONE",
      tunnel: "DOWN",
    });
    connection.dispose();
    vi.useRealTimers();
  });

  it("restores the authoritative remaining time on app restart", async () => {
    const { api, keys, tunnel } = dependencies();
    vi.mocked(api.getCurrentVpnSession).mockResolvedValue({
      session: {
        ...backendSession,
        server_time: "2026-09-16T10:10:00Z",
      },
    });
    const connection = createVpnConnectionManager(
      api,
      createWireGuardProvisioner(api, keys),
      createWireGuardProtocol(tunnel),
      60_000,
    );

    await connection.reconcile("access-token");

    expect(connection.current()).toMatchObject({
      phase: "CONNECTED",
      session: { remainingSeconds: 300 },
    });
  });

  it("stops locally when backend reports that the peer session is already gone", async () => {
    vi.useFakeTimers();
    const { api, keys, tunnel } = dependencies();
    const connection = createVpnConnectionManager(
      api,
      createWireGuardProvisioner(api, keys),
      createWireGuardProtocol(tunnel),
      100,
    );
    await connection.connect("access-token", { mode: "AUTO" });
    vi.mocked(api.getCurrentVpnSession).mockResolvedValue({ session: null });

    await vi.advanceTimersByTimeAsync(100);

    expect(tunnel.stop).toHaveBeenCalledOnce();
    expect(connection.current()).toEqual({
      phase: "DISCONNECTED",
      backend: "NONE",
      tunnel: "DOWN",
    });
    connection.dispose();
    vi.useRealTimers();
  });
});
