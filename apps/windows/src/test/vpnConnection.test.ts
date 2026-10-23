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
    verify: vi.fn().mockResolvedValue({
      tunnel_established: true,
      internet_verified: true,
      failure_code: null,
    }),
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
    ).rejects.toEqual(new VpnConnectionError("UNKNOWN"));
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
    ).rejects.toEqual(new VpnConnectionError("TUNNEL_ESTABLISHED_NO_TRAFFIC"));
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
    ).rejects.toEqual(new VpnConnectionError("HANDSHAKE_FAILED"));
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
    vi.mocked(tunnel.verify).mockResolvedValue({
      tunnel_established: false,
      internet_verified: false,
      failure_code: "HANDSHAKE_FAILED",
    });

    await vi.advanceTimersByTimeAsync(100);

    expect(connection.current()).toMatchObject({
      phase: "FAILED",
      failure_code: "HANDSHAKE_FAILED",
      backend: "NONE",
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

  it("charges failed startup and fallback against the original server deadline", async () => {
    vi.useFakeTimers();
    const { api, keys, tunnel } = dependencies();
    const provisioner = createWireGuardProvisioner(api, keys);
    const candidate = provisioner.candidates(backendSession)[0];
    vi.spyOn(provisioner, "candidates").mockReturnValue([candidate, candidate]);
    vi.mocked(tunnel.start).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve("UP"), 5_000)),
    );
    vi.mocked(tunnel.verify).mockResolvedValueOnce({
      tunnel_established: true,
      internet_verified: false,
      failure_code: "DNS_FAILED",
    });
    const connection = createVpnConnectionManager(
      api,
      provisioner,
      createWireGuardProtocol(tunnel),
      2_000_000,
    );
    try {
      const pending = connection.connect("token", { mode: "AUTO" });
      await vi.advanceTimersByTimeAsync(10_000);
      await pending;
      expect(connection.current()).toMatchObject({
        phase: "CONNECTED",
        session: { remainingSeconds: 890 },
      });
      expect(tunnel.start).toHaveBeenCalledTimes(2);
      await vi.advanceTimersByTimeAsync(890_000);
      expect(connection.current().phase).toBe("DISCONNECTED");
      expect(tunnel.stop).toHaveBeenCalledTimes(2);
      expect(api.createVpnSession).toHaveBeenCalledOnce();
    } finally {
      connection.dispose();
      vi.useRealTimers();
    }
  });

  it("rejects late verification after expiry and never starts the next candidate", async () => {
    vi.useFakeTimers();
    const { api, keys, tunnel } = dependencies();
    vi.mocked(api.createVpnSession).mockResolvedValue({
      ...backendSession,
      expires_at: "2026-09-16T10:00:01Z",
    });
    const provisioner = createWireGuardProvisioner(api, keys);
    const candidate = provisioner.candidates(backendSession)[0];
    vi.spyOn(provisioner, "candidates").mockReturnValue([candidate, candidate]);
    vi.mocked(tunnel.start).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve("UP"), 5_000)),
    );
    const connection = createVpnConnectionManager(
      api,
      provisioner,
      createWireGuardProtocol(tunnel),
    );
    const phases: string[] = [];
    connection.subscribe(() => phases.push(connection.current().phase));
    try {
      const pending = expect(
        connection.connect("token", { mode: "AUTO" }),
      ).rejects.toBeInstanceOf(VpnConnectionError);
      await vi.advanceTimersByTimeAsync(5_000);
      await pending;
      expect(phases).not.toContain("CONNECTED");
      expect(tunnel.start).toHaveBeenCalledOnce();
      expect(tunnel.stop).toHaveBeenCalledOnce();
      expect(api.disconnectVpnSession).toHaveBeenCalledOnce();
    } finally {
      connection.dispose();
      vi.useRealTimers();
    }
  });

  it("counts native reconciliation delay from receipt of the backend response", async () => {
    vi.useFakeTimers();
    const { api, keys, tunnel } = dependencies();
    vi.mocked(api.getCurrentVpnSession).mockResolvedValue({
      session: backendSession,
    });
    vi.mocked(tunnel.state).mockImplementationOnce(
      () => new Promise((resolve) => setTimeout(() => resolve("UP"), 5_000)),
    );
    const connection = createVpnConnectionManager(
      api,
      createWireGuardProvisioner(api, keys),
      createWireGuardProtocol(tunnel),
    );
    try {
      const pending = connection.reconcile("token");
      await vi.advanceTimersByTimeAsync(5_000);
      await pending;
      expect(connection.current()).toMatchObject({
        phase: "CONNECTED",
        session: { remainingSeconds: 895 },
      });
    } finally {
      connection.dispose();
      vi.useRealTimers();
    }
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

describe("strict Internet verification transitions", () => {
  function setup() {
    const { api, keys, tunnel } = dependencies();
    vi.mocked(api.getCurrentVpnSession).mockResolvedValue({
      session: backendSession,
    });
    const connection = createVpnConnectionManager(
      api,
      createWireGuardProvisioner(api, keys),
      createWireGuardProtocol(tunnel),
      100,
    );
    const phases: string[] = [];
    connection.subscribe(() => phases.push(connection.current().phase));
    return { api, tunnel, connection, phases };
  }
  it("A: only verifies CONNECTED after tunnel and independent Internet verification", async () => {
    const { tunnel, connection, phases } = setup();
    let complete!: (value: Awaited<ReturnType<typeof tunnel.verify>>) => void;
    vi.mocked(tunnel.verify).mockImplementation(
      () =>
        new Promise((resolve) => {
          complete = resolve;
        }),
    );
    const connecting = connection.connect("token", { mode: "AUTO" });
    await vi.waitFor(() =>
      expect(connection.current().phase).toBe("VERIFYING_INTERNET"),
    );
    expect(phases).toEqual([
      "CONNECTING",
      "CONNECTING", // The authorized method is now available to the UI.
      "TUNNEL_ESTABLISHED",
      "VERIFYING_INTERNET",
    ]);
    complete({
      tunnel_established: true,
      internet_verified: true,
      failure_code: null,
    });
    await connecting;
    expect(connection.current().phase).toBe("CONNECTED");
    await connection.disconnect("token");
    expect(connection.current().phase).toBe("DISCONNECTED");
    connection.dispose();
  });
  it.each([
    "DNS_FAILED",
    "HTTPS_CHECK_FAILED",
    "TUNNEL_ESTABLISHED_NO_TRAFFIC",
    "ROUTE_LEAK_DETECTED",
    "EGRESS_MISMATCH",
    "TRANSPORT_TIMEOUT",
    "OBFUSCATION_FAILED",
    "SERVER_UNREACHABLE",
    "UNKNOWN",
  ] as const)(
    "B/C: handshake succeeds but %s must never emit CONNECTED",
    async (code) => {
      const { tunnel, connection, phases } = setup();
      vi.mocked(tunnel.verify).mockResolvedValue({
        tunnel_established: true,
        internet_verified: false,
        failure_code: code,
      });
      await expect(
        connection.connect("token", { mode: "AUTO" }),
      ).rejects.toMatchObject({ code });
      expect(tunnel.start).toHaveResolvedWith("UP");
      expect(phases).toContain("TUNNEL_ESTABLISHED");
      expect(phases).not.toContain("CONNECTED");
      expect(connection.current()).toMatchObject({
        phase: "FAILED",
        failure_code: code,
        tunnel: "DOWN",
      });
      connection.dispose();
    },
  );
  it("D: failed handshake never emits tunnel established or CONNECTED", async () => {
    const { tunnel, connection, phases } = setup();
    vi.mocked(tunnel.start).mockRejectedValue(
      new WireGuardTunnelError("wireguard_handshake_timeout"),
    );
    await expect(
      connection.connect("token", { mode: "AUTO" }),
    ).rejects.toMatchObject({ code: "HANDSHAKE_FAILED" });
    expect(phases).not.toContain("CONNECTED");
    expect(phases).not.toContain("TUNNEL_ESTABLISHED");
    expect(tunnel.verify).not.toHaveBeenCalled();
    connection.dispose();
  });
  it("reconciles an existing UP tunnel only after a fresh probe", async () => {
    const { tunnel, connection, phases } = setup();
    vi.mocked(tunnel.verify).mockResolvedValue({
      tunnel_established: true,
      internet_verified: false,
      failure_code: "DNS_FAILED",
    });
    await connection.reconcile("token");
    expect(tunnel.start).not.toHaveBeenCalled();
    expect(connection.current().phase).toBe("FAILED");
    expect(phases).not.toContain("CONNECTED");
    connection.dispose();
  });
  it("CONNECTED -> DEGRADED -> CONNECTED on recovery; three consecutive failures -> FAILED", async () => {
    vi.useFakeTimers();
    const { tunnel, connection } = setup();
    try {
      await connection.connect("token", { mode: "AUTO" });
      vi.mocked(tunnel.verify).mockResolvedValue({
        tunnel_established: true,
        internet_verified: false,
        failure_code: "HTTPS_CHECK_FAILED",
      });
      await vi.advanceTimersByTimeAsync(100);
      expect(connection.current().phase).toBe("DEGRADED");
      vi.mocked(tunnel.verify).mockResolvedValue({
        tunnel_established: true,
        internet_verified: true,
        failure_code: null,
      });
      await vi.advanceTimersByTimeAsync(100);
      expect(connection.current().phase).toBe("CONNECTED");
      vi.mocked(tunnel.verify).mockResolvedValue({
        tunnel_established: true,
        internet_verified: false,
        failure_code: "DNS_FAILED",
      });
      await vi.advanceTimersByTimeAsync(200);
      expect(connection.current().phase).toBe("DEGRADED");
      await vi.advanceTimersByTimeAsync(100);
      expect(connection.current()).toMatchObject({
        phase: "FAILED",
        tunnel: "DOWN",
        failure_code: "DNS_FAILED",
      });
      expect(tunnel.stop).toHaveBeenCalledOnce();
    } finally {
      connection.dispose();
      vi.useRealTimers();
    }
  });
  it("fails immediately on a route leak during monitoring", async () => {
    vi.useFakeTimers();
    const { tunnel, connection } = setup();
    try {
      await connection.connect("token", { mode: "AUTO" });
      vi.mocked(tunnel.verify).mockResolvedValue({
        tunnel_established: true,
        internet_verified: false,
        failure_code: "ROUTE_LEAK_DETECTED",
      });
      await vi.advanceTimersByTimeAsync(100);
      expect(connection.current()).toMatchObject({
        phase: "FAILED",
        failure_code: "ROUTE_LEAK_DETECTED",
      });
    } finally {
      connection.dispose();
      vi.useRealTimers();
    }
  });
  it("does not overlap health calls and ignores a success arriving after disconnect", async () => {
    vi.useFakeTimers();
    const { tunnel, connection, phases } = setup();
    try {
      await connection.connect("token", { mode: "AUTO" });
      let complete!: (value: Awaited<ReturnType<typeof tunnel.verify>>) => void;
      vi.mocked(tunnel.verify).mockImplementation(
        () =>
          new Promise((resolve) => {
            complete = resolve;
          }),
      );
      await vi.advanceTimersByTimeAsync(500);
      expect(tunnel.verify).toHaveBeenCalledTimes(2);
      await connection.disconnect("token");
      phases.length = 0;
      complete({
        tunnel_established: true,
        internet_verified: true,
        failure_code: null,
      });
      await vi.advanceTimersByTimeAsync(100);
      expect(connection.current().phase).toBe("DISCONNECTED");
      expect(phases).not.toContain("CONNECTED");
    } finally {
      connection.dispose();
      vi.useRealTimers();
    }
  });
});

it("a hung Internet check times out without promoting the tunnel to CONNECTED", async () => {
  vi.useFakeTimers();
  const { api, keys, tunnel } = dependencies();
  vi.mocked(tunnel.verify).mockImplementation(
    () => new Promise(() => undefined),
  );
  const connection = createVpnConnectionManager(
    api,
    createWireGuardProvisioner(api, keys),
    createWireGuardProtocol(tunnel),
  );
  const phases: string[] = [];
  connection.subscribe(() => phases.push(connection.current().phase));
  try {
    const pending = connection.connect("token", { mode: "AUTO" });
    const rejected = expect(pending).rejects.toMatchObject({
      code: "TRANSPORT_TIMEOUT",
    });
    await vi.advanceTimersByTimeAsync(20_001);
    await rejected;
    expect(connection.current()).toMatchObject({
      phase: "FAILED",
      failure_code: "TRANSPORT_TIMEOUT",
    });
    expect(phases).not.toContain("CONNECTED");
  } finally {
    connection.dispose();
    vi.useRealTimers();
  }
});

it("session expiry still disconnects while Internet connectivity is DEGRADED", async () => {
  vi.useFakeTimers();
  const { api, keys, tunnel } = dependencies();
  vi.mocked(api.createVpnSession).mockResolvedValue({
    ...backendSession,
    expires_at: "2026-09-16T10:00:01Z",
  });
  const connection = createVpnConnectionManager(
    api,
    createWireGuardProvisioner(api, keys),
    createWireGuardProtocol(tunnel),
    600,
  );
  try {
    await connection.connect("token", { mode: "AUTO" });
    vi.mocked(tunnel.verify).mockResolvedValue({
      tunnel_established: true,
      internet_verified: false,
      failure_code: "HTTPS_CHECK_FAILED",
    });
    await vi.advanceTimersByTimeAsync(600);
    expect(connection.current().phase).toBe("DEGRADED");
    await vi.advanceTimersByTimeAsync(400);
    expect(connection.current().phase).toBe("DISCONNECTED");
  } finally {
    connection.dispose();
    vi.useRealTimers();
  }
});

it("a late initial verification cannot restore CONNECTED after user disconnect", async () => {
  const { api, keys, tunnel } = dependencies();
  let complete!: (value: Awaited<ReturnType<typeof tunnel.verify>>) => void;
  vi.mocked(tunnel.verify).mockImplementation(
    () =>
      new Promise((resolve) => {
        complete = resolve;
      }),
  );
  const connection = createVpnConnectionManager(
    api,
    createWireGuardProvisioner(api, keys),
    createWireGuardProtocol(tunnel),
  );
  const phases: string[] = [];
  connection.subscribe(() => phases.push(connection.current().phase));
  try {
    const pending = connection.connect("token", { mode: "AUTO" });
    await vi.waitFor(() =>
      expect(connection.current().phase).toBe("VERIFYING_INTERNET"),
    );
    await connection.disconnect("token");
    complete({
      tunnel_established: true,
      internet_verified: true,
      failure_code: null,
    });
    await pending;
    expect(connection.current().phase).toBe("DISCONNECTED");
    expect(phases).not.toContain("CONNECTED");
  } finally {
    connection.dispose();
  }
});

it("a canceled attempt retains backend ownership if every local stop fails", async () => {
  const { api, keys, tunnel } = dependencies();
  let complete!: (value: Awaited<ReturnType<typeof tunnel.verify>>) => void;
  vi.mocked(tunnel.verify).mockImplementation(
    () =>
      new Promise((resolve) => {
        complete = resolve;
      }),
  );
  vi.mocked(tunnel.stop).mockRejectedValue(new Error("private native failure"));
  const connection = createVpnConnectionManager(
    api,
    createWireGuardProvisioner(api, keys),
    createWireGuardProtocol(tunnel),
  );
  try {
    const pending = connection.connect("token", { mode: "AUTO" });
    await vi.waitFor(() =>
      expect(connection.current().phase).toBe("VERIFYING_INTERNET"),
    );
    await expect(connection.disconnect("token")).rejects.toEqual(
      new VpnConnectionError("LOCAL_TUNNEL_STOP_FAILED"),
    );
    complete({
      tunnel_established: true,
      internet_verified: true,
      failure_code: null,
    });
    await pending;
    expect(api.disconnectVpnSession).not.toHaveBeenCalled();
    expect(connection.current()).toMatchObject({
      phase: "UNAVAILABLE",
      backend: "ACTIVE",
      tunnel: "UP",
    });
  } finally {
    connection.dispose();
  }
});

it("persistent backend monitoring failure also leaves DEGRADED for FAILED", async () => {
  vi.useFakeTimers();
  const { api, keys, tunnel } = dependencies();
  const connection = createVpnConnectionManager(
    api,
    createWireGuardProvisioner(api, keys),
    createWireGuardProtocol(tunnel),
    100,
  );
  try {
    await connection.connect("token", { mode: "AUTO" });
    vi.mocked(api.getCurrentVpnSession).mockRejectedValue(
      new ApiError("NETWORK_ERROR"),
    );
    await vi.advanceTimersByTimeAsync(100);
    expect(connection.current().phase).toBe("DEGRADED");
    await vi.advanceTimersByTimeAsync(200);
    expect(connection.current()).toMatchObject({
      phase: "FAILED",
      failure_code: "SERVER_UNREACHABLE",
    });
  } finally {
    connection.dispose();
    vi.useRealTimers();
  }
});
