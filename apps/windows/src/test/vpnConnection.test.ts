import { describe, expect, it, vi } from "vitest";
import {
  ApiError,
  type ActiveVpnSessionResponse,
  type ApiClient,
} from "../api/client";
import type { WireGuardKeyManager } from "../native/wireguardKeys";
import type { WireGuardTunnelController } from "../native/wireguardTransport";
import {
  createVpnConnectionOrchestrator,
  VpnConnectionError,
} from "../vpn/connection";

const PUBLIC_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
const backendSession: ActiveVpnSessionResponse = {
  session_id: "123e4567-e89b-42d3-a456-426614174020",
  status: "ACTIVE",
  country_code: "DE",
  expires_at: "2026-09-16T10:15:00Z",
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
  };
  return { api, keys, tunnel };
}

describe("Windows VPN connection orchestration", () => {
  it("connects AUTO using only the local public key and confirms native UP", async () => {
    const { api, keys, tunnel } = dependencies();
    const connection = createVpnConnectionOrchestrator(api, keys, tunnel);

    await expect(
      connection.connect("access-token", { mode: "AUTO" }),
    ).resolves.toEqual({
      sessionId: backendSession.session_id,
      countryCode: "DE",
      expiresAt: backendSession.expires_at,
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
    const connection = createVpnConnectionOrchestrator(api, keys, tunnel);

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
      const connection = createVpnConnectionOrchestrator(api, keys, tunnel);

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
    const connection = createVpnConnectionOrchestrator(api, keys, tunnel);

    await expect(
      connection.connect("access-token", { mode: "AUTO" }),
    ).rejects.toEqual(new VpnConnectionError("LOCAL_TUNNEL_FAILED"));
    expect(tunnel.stop).toHaveBeenCalledOnce();
    expect(api.disconnectVpnSession).toHaveBeenCalledWith(
      "access-token",
      backendSession.session_id,
    );
  });

  it("does not report success when native state confirmation is DOWN", async () => {
    const { api, keys, tunnel } = dependencies();
    vi.mocked(tunnel.state).mockResolvedValue("DOWN");
    const connection = createVpnConnectionOrchestrator(api, keys, tunnel);

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
    const connection = createVpnConnectionOrchestrator(api, keys, tunnel);
    const first = connection.connect("access-token", { mode: "AUTO" });

    await expect(
      connection.connect("access-token", { mode: "AUTO" }),
    ).rejects.toEqual(new VpnConnectionError("CONNECTION_IN_PROGRESS"));
    resolveKey(PUBLIC_KEY);
    await first;
    expect(api.createVpnSession).toHaveBeenCalledOnce();
  });
});
