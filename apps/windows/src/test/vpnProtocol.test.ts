import { ApiError, createApiClient } from "../api/client";
import type { HttpTransport } from "../native/http";
import { describe, expect, it, vi } from "vitest";
import {
  connectFirstCandidate,
  ProtocolConnectionError,
  type VpnProtocol,
} from "../vpn/protocol";
import {
  createWireGuardProtocol,
  createWireGuardProvisioner,
  wireGuardDefaults,
} from "../vpn/wireguard";
import {
  WireGuardTunnelError,
  type WireGuardTunnelController,
} from "../native/wireguardTransport";
import type { ActiveVpnSessionResponse, ApiClient } from "../api/client";

const parameters = {
  endpoint: { ipv4: "192.0.2.1", port: 51820 },
  server_public_key: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
  client_address: "10.77.0.2/32",
  dns: ["1.1.1.1"],
  allowed_ips: ["0.0.0.0/0"],
};
const config = { ...wireGuardDefaults("DE", 51820), parameters };
function native(): WireGuardTunnelController {
  return {
    start: vi.fn().mockResolvedValue("UP"),
    stop: vi.fn().mockResolvedValue("DOWN"),
    state: vi.fn().mockResolvedValue("UP"),
    diagnostics: vi.fn().mockResolvedValue({
      transportHealthy: true,
      txBytes: 5,
      rxBytes: 10,
      privateKey: "secret",
      endpoint: "sensitive",
      peerPublicKey: "key",
      token: "secret-token",
    }),
  };
}

describe("protocol boundary", () => {
  it("attempts only the first candidate and never falls back after failure", async () => {
    const protocol = {
      connect: vi.fn().mockResolvedValue({
        tunnel_established: false,
        internet_verified: false,
        failure_code: "CONNECTION_FAILED",
        diagnostics: {},
      }),
    } as unknown as VpnProtocol;
    await expect(
      connectFirstCandidate(protocol, [config, { ...config, port: 443 }]),
    ).rejects.toEqual(new ProtocolConnectionError("CONNECTION_FAILED"));
    expect(protocol.connect).toHaveBeenCalledExactlyOnceWith(config);
  });
  it("rejects empty candidate lists without invoking a protocol", async () => {
    const protocol = { connect: vi.fn() } as unknown as VpnProtocol;
    await expect(connectFirstCandidate(protocol, [])).rejects.toEqual(
      new ProtocolConnectionError("UNSUPPORTED_CONFIGURATION"),
    );
    expect(protocol.connect).not.toHaveBeenCalled();
  });
  it("does not equate tunnel establishment with verified Internet", async () => {
    const protocol = {
      connect: vi.fn().mockResolvedValue({
        tunnel_established: true,
        internet_verified: false,
        failure_code: "INTERNET_UNVERIFIED",
      }),
    } as unknown as VpnProtocol;
    await expect(connectFirstCandidate(protocol, [config])).rejects.toEqual(
      new ProtocolConnectionError("INTERNET_UNVERIFIED"),
    );
  });
  it("preserves backend candidate order and explicit empty lists", () => {
    const provisioner = createWireGuardProvisioner({} as ApiClient);
    const session: ActiveVpnSessionResponse = {
      session_id: "123e4567-e89b-42d3-a456-426614174020",
      status: "ACTIVE",
      expires_at: null,
      server_time: "2026-09-20T00:00:00Z",
      country_code: "DE",
      transport: parameters,
      candidates: [
        wireGuardDefaults("DE", 443),
        wireGuardDefaults("DE", 51820),
      ],
    };
    expect(provisioner.candidates(session).map((item) => item.port)).toEqual([
      443, 51820,
    ]);
    expect(provisioner.candidates({ ...session, candidates: [] })).toEqual([]);
    expect(
      provisioner.candidates({ ...session, candidates: undefined }),
    ).toEqual([config]);
  });
});

describe("WireGuard protocol adapter", () => {
  it("delegates lifecycle and reports native startup verification", async () => {
    const tunnel = native();
    const protocol = createWireGuardProtocol(tunnel);
    expect(await protocol.connect(config)).toMatchObject({
      tunnel_established: true,
      internet_verified: true,
      failure_code: null,
    });
    expect(await protocol.status()).toBe("UP");
    expect(await protocol.health()).toMatchObject({ internet_verified: true });
    expect(await protocol.disconnect()).toBe("DOWN");
    expect(await protocol.health()).toMatchObject({ internet_verified: false });
  });
  it.each([
    "protocol",
    "transport",
    "encryption_mode",
    "obfuscation_mode",
    "dns_mode",
    "routing_mode",
    "mtu",
    "port",
  ])("rejects unsupported %s without starting", async (key) => {
    const tunnel = native();
    expect(
      await createWireGuardProtocol(tunnel).connect({
        ...config,
        [key]: "unsupported",
      }),
    ).toMatchObject({ failure_code: "UNSUPPORTED_CONFIGURATION" });
    expect(tunnel.start).not.toHaveBeenCalled();
  });
  it("allowlists diagnostics and discards arbitrary native error text", async () => {
    const tunnel = native();
    const protocol = createWireGuardProtocol(tunnel);
    expect(await protocol.diagnostics()).toEqual({
      status: "UP",
      transport_healthy: true,
      tx_bytes: 5,
      rx_bytes: 10,
    });
    vi.mocked(tunnel.start).mockRejectedValue(
      new WireGuardTunnelError("private-key=secret"),
    );
    const result = await protocol.connect(config);
    expect(result.failure_code).toBe("CONNECTION_FAILED");
    expect(JSON.stringify(result)).not.toContain("secret");
    vi.mocked(tunnel.diagnostics).mockRejectedValue(new Error("secret-token"));
    expect(await protocol.diagnostics()).toEqual({
      status: "UNKNOWN",
      transport_healthy: false,
      tx_bytes: 0,
      rx_bytes: 0,
    });
  });
  it("maps native Internet verification failures to a stable generic code", async () => {
    const tunnel = native();
    vi.mocked(tunnel.start).mockRejectedValue(
      new WireGuardTunnelError("wireguard_data_plane_unavailable"),
    );
    expect(await createWireGuardProtocol(tunnel).connect(config)).toMatchObject(
      { internet_verified: false, failure_code: "INTERNET_UNVERIFIED" },
    );
  });
  it("loses verification when the transport becomes unhealthy", async () => {
    const tunnel = native();
    const protocol = createWireGuardProtocol(tunnel);
    await protocol.connect(config);
    vi.mocked(tunnel.diagnostics).mockResolvedValue(null);
    expect(await protocol.health()).toMatchObject({
      tunnel_established: true,
      internet_verified: false,
    });
  });
});

describe("candidate HTTP contract", () => {
  const session = {
    session_id: "123e4567-e89b-42d3-a456-426614174020",
    status: "ACTIVE",
    country_code: "DE",
    expires_at: null,
    server_time: "2026-09-20T00:00:00Z",
    transport: parameters,
  };
  it("negotiates and preserves candidate order for create and restore", async () => {
    const payload = {
      ...session,
      candidates: [
        wireGuardDefaults("DE", 51820),
        wireGuardDefaults("DE", 443),
      ],
    };
    const http = vi
      .fn<HttpTransport>()
      .mockResolvedValueOnce(new Response(JSON.stringify(payload)))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ session: payload })),
      );
    const api = createApiClient("https://api.example.invalid", http, 5000);
    expect(
      await api.createVpnSession("token", {
        mode: "AUTO",
        public_key: parameters.server_public_key,
      }),
    ).toEqual(payload);
    expect(await api.getCurrentVpnSession("token")).toEqual({
      session: payload,
    });
    for (const [, init] of http.mock.calls) {
      expect(init?.headers).toMatchObject({ "x-vpn-candidates": "1" });
    }
  });
  it.each([
    { ...wireGuardDefaults("DE", 51820), node_id: "internal" },
    { ...wireGuardDefaults("DE", 51820), mtu: 0 },
    { ...wireGuardDefaults("DE", 51820), port: 65536 },
    { ...wireGuardDefaults("DE", 51820), protocol: "" },
    { ...wireGuardDefaults("DE", 51820), country: "invalid" },
  ])("rejects malformed or internal candidate fields", async (candidate) => {
    const http = vi
      .fn<HttpTransport>()
      .mockResolvedValue(
        new Response(JSON.stringify({ ...session, candidates: [candidate] })),
      );
    const api = createApiClient("https://api.example.invalid", http, 5000);
    await expect(
      api.createVpnSession("token", {
        mode: "AUTO",
        public_key: parameters.server_public_key,
      }),
    ).rejects.toEqual(new ApiError("INVALID_RESPONSE"));
  });
});
