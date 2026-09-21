import { createApiClient, ApiError } from "../api/client";
import { describe, expect, it, vi } from "vitest";
import { createProfileAdapter } from "../vpn/profileAdapter";
import { createProfileConfig } from "../vpn/profiles";
import {
  ObfuscationRegistry,
  obfuscationProviders,
  validObfuscation,
} from "../vpn/obfuscation";
import { connectFirstCandidate } from "../vpn/protocol";
import type { WireGuardTunnelController } from "../native/wireguardTransport";
import type { ExternalTunnelRuntime } from "../vpn/externalProtocol";

const parameters = {
  endpoint: { ipv4: "192.0.2.1", port: 443 },
  server_public_key: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
  client_address: "10.77.0.2/32",
  dns: ["1.1.1.1"],
  allowed_ips: ["0.0.0.0/0"],
};

describe("independent obfuscation providers", () => {
  it.each(["NONE", "SIMPLE_PACKET_WRAPPER_V1"])(
    "connects and reconnects WireGuard with %s",
    async (mode) => {
      const tunnel: WireGuardTunnelController = {
        start: vi.fn().mockResolvedValue("UP"),
        stop: vi.fn().mockResolvedValue("DOWN"),
        state: vi.fn().mockResolvedValue("UP"),
        diagnostics: vi.fn().mockResolvedValue(null),
      };
      const adapter = createProfileAdapter("WIREGUARD_UDP", {
        wireguard: tunnel,
      });
      const config = {
        ...createProfileConfig("WIREGUARD_UDP", "DE", 443),
        obfuscation_mode: mode,
        obfuscation_version: mode === "NONE" ? 0 : 1,
        parameters,
      };
      await connectFirstCandidate(adapter, [config]);
      await adapter.disconnect();
      await connectFirstCandidate(adapter, [config]);
      expect(tunnel.start).toHaveBeenCalledTimes(2);
      expect(tunnel.start).toHaveBeenLastCalledWith(
        expect.objectContaining(
          mode === "NONE"
            ? { direct: true }
            : { obfuscation: { mode, version: 1, maxDatagramSize: 1400 } },
        ),
      );
      expect(config.encryption_mode).toBe("WIREGUARD");
    },
  );
  it("delegates TLS transport only to a supporting runtime without changing VPN encryption", async () => {
    const runtime: ExternalTunnelRuntime = {
      obfuscation_modes: ["TLS_TRANSPORT:1"],
      start: vi.fn().mockResolvedValue({
        tunnel_established: true,
        internet_verified: true,
      }),
      stop: vi.fn().mockResolvedValue("DOWN"),
      status: vi.fn().mockResolvedValue("UP"),
      health: vi.fn(),
    };
    const config = {
      ...createProfileConfig("OPENVPN_TLS_TCP", "DE"),
      obfuscation_mode: "TLS_TRANSPORT",
      obfuscation_version: 1,
      parameters: {
        endpoint: "vpn.example.test",
        server_name: "vpn.example.test",
        credential_ref: "credential-1",
        trust_ref: "trust-1",
      },
    };
    const adapter = createProfileAdapter("OPENVPN_TLS_TCP", {
      openvpn: runtime,
    });
    await connectFirstCandidate(adapter, [config]);
    await adapter.disconnect();
    await connectFirstCandidate(adapter, [config]);
    expect(runtime.start).toHaveBeenLastCalledWith(
      expect.objectContaining({
        obfuscation: {
          mode: "TLS_TRANSPORT",
          version: 1,
          transport_parameters: {},
        },
        config: expect.objectContaining({
          encryption_mode: "TLS_1_3_AES_256_GCM",
        }),
        verify_certificate: true,
      }),
    );
    const unsupported = { ...runtime, obfuscation_modes: [] };
    vi.mocked(runtime.start).mockClear();
    expect(
      await createProfileAdapter("OPENVPN_TLS_TCP", {
        openvpn: unsupported,
      }).connect(config),
    ).toMatchObject({ failure_code: "UNSUPPORTED_CONFIGURATION" });
    expect(runtime.start).not.toHaveBeenCalled();
  });
  it("checks compatibility, version, secret-free parameters and exact MTU boundary", () => {
    const config = {
      ...createProfileConfig("WIREGUARD_UDP", "DE"),
      obfuscation_mode: "SIMPLE_PACKET_WRAPPER_V1",
      obfuscation_version: 1,
    };
    expect(
      validObfuscation({
        ...config,
        transport_parameters: { max_datagram_size: 1320 },
      }),
    ).toBe(true);
    for (const change of [
      { obfuscation_version: 2 },
      { transport_parameters: { max_datagram_size: 1319 } },
      { transport_parameters: { max_datagram_size: 65508 } },
      { transport_parameters: { secret: "secret" } },
      { transport: "TCP" },
      { protocol: "MASQUE" },
      { obfuscation_mode: "TLS_TRANSPORT" },
    ]) {
      expect(validObfuscation({ ...config, ...change })).toBe(false);
    }
    expect(
      validObfuscation({
        ...createProfileConfig("MASQUE_QUIC", "DE"),
        obfuscation_mode: "TLS_TRANSPORT",
        obfuscation_version: 1,
      }),
    ).toBe(false);
    expect(() =>
      obfuscationProviders.prepare({
        ...config,
        transport_parameters: { key: "secret" },
      }),
    ).toThrow("UNSUPPORTED_OBFUSCATION_CONFIGURATION");
  });
  it("registers a future provider without changing VpnProtocol", () => {
    const registry = new ObfuscationRegistry([
      {
        mode: "TEST_PROVIDER",
        version: 2,
        supports: () => true,
        prepare: () => ({
          mode: "TEST_PROVIDER",
          version: 2,
          transport_parameters: {},
        }),
      },
    ]);
    expect(
      registry.prepare({
        ...createProfileConfig("WIREGUARD_UDP", "DE"),
        obfuscation_mode: "TEST_PROVIDER",
        obfuscation_version: 2,
      }).mode,
    ).toBe("TEST_PROVIDER");
  });
});

it("preserves negotiated obfuscation fields across HTTP and rejects secret parameters", async () => {
  const candidate = {
    ...createProfileConfig("WIREGUARD_UDP", "DE", 443),
    obfuscation_mode: "SIMPLE_PACKET_WRAPPER_V1",
    obfuscation_version: 1,
    transport_parameters: { max_datagram_size: 1400 },
  };
  const session = {
    session_id: "123e4567-e89b-42d3-a456-426614174020",
    status: "ACTIVE",
    country_code: "DE",
    expires_at: null,
    server_time: "2026-09-21T10:00:00Z",
    candidates: [candidate],
    transport: parameters,
  };
  const http = vi.fn().mockResolvedValue(new Response(JSON.stringify(session)));
  const api = createApiClient("https://api.example.invalid", http, 5000);
  expect(
    (
      await api.createVpnSession("token", {
        mode: "AUTO",
        public_key: parameters.server_public_key,
      })
    ).candidates,
  ).toEqual([candidate]);
  http.mockResolvedValue(
    new Response(
      JSON.stringify({
        ...session,
        candidates: [
          { ...candidate, transport_parameters: { private_key: "secret" } },
        ],
      }),
    ),
  );
  await expect(
    api.createVpnSession("token", {
      mode: "AUTO",
      public_key: parameters.server_public_key,
    }),
  ).rejects.toEqual(new ApiError("INVALID_RESPONSE"));
});
