import { describe, expect, it, vi } from "vitest";
import {
  connectionProfiles,
  createProfileConfig,
  validateProfileConfig,
  type ProfileId,
} from "../vpn/profiles";
import { createProfileAdapter } from "../vpn/profileAdapter";
import { connectFirstCandidate } from "../vpn/protocol";
import type { ExternalTunnelRuntime } from "../vpn/externalProtocol";
import type { WireGuardTunnelController } from "../native/wireguardTransport";

const secureParameters = {
  endpoint: "vpn.example.test",
  server_name: "vpn.example.test",
  credential_ref: "credential-1",
  trust_ref: "trust-1",
};
const wireguardParameters = {
  endpoint: { ipv4: "192.0.2.1", port: 51820 },
  server_public_key: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
  client_address: "10.77.0.2/32",
  dns: ["1.1.1.1"],
  allowed_ips: ["0.0.0.0/0"],
};
function runtime(): ExternalTunnelRuntime {
  return {
    start: vi.fn().mockResolvedValue({
      tunnel_established: true,
      internet_verified: true,
      verification: {
        dns_verified: true,
        https_verified: true,
        route_verified: true,
      },
    }),
    stop: vi.fn().mockResolvedValue("DOWN"),
    status: vi.fn().mockResolvedValue("UP"),
    health: vi.fn().mockResolvedValue({
      tunnel_established: true,
      internet_verified: true,
      verification: {
        dns_verified: true,
        https_verified: true,
        route_verified: true,
      },
    }),
  };
}
function wireguard(): WireGuardTunnelController {
  return {
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
}

describe("connection profile capabilities", () => {
  it.each(Object.keys(connectionProfiles) as ProfileId[])(
    "instantiates and connects %s through VpnProtocol",
    async (id) => {
      const external = runtime();
      const native = wireguard();
      const adapter = createProfileAdapter(id, {
        wireguard: native,
        openvpn: external,
        masque: external,
      });
      const config = {
        ...createProfileConfig(id, "DE"),
        parameters:
          id === "WIREGUARD_UDP" ? wireguardParameters : secureParameters,
      };
      expect(adapter.capabilities).toEqual(connectionProfiles[id]);
      expect(validateProfileConfig(adapter.capabilities, config)).toBe(true);
      await expect(
        connectFirstCandidate(adapter, [config]),
      ).resolves.toBeUndefined();
      expect(await adapter.status()).toBe("UP");
      expect(await adapter.disconnect()).toBe("DOWN");
      if (id === "WIREGUARD_UDP") {
        expect(native.start).toHaveBeenCalledWith(
          expect.objectContaining({ direct: true }),
        );
      } else {
        expect(external.start).toHaveBeenCalledExactlyOnceWith({
          profile: id,
          config: createProfileConfig(id, "DE"),
          parameters: secureParameters,
          minimum_tls_version: "1.3",
          verify_certificate: true,
        });
      }
    },
  );
  it("supports configurable standard WireGuard UDP ports without legacy wrappers", async () => {
    const native = wireguard();
    const config = {
      ...createProfileConfig("WIREGUARD_UDP", "DE", 53),
      parameters: {
        ...wireguardParameters,
        endpoint: { ipv4: "192.0.2.1", port: 53 },
      },
    };
    await connectFirstCandidate(
      createProfileAdapter("WIREGUARD_UDP", { wireguard: native }),
      [config],
    );
    expect(native.start).toHaveBeenCalledWith(
      expect.objectContaining({
        endpoint: config.parameters.endpoint,
        direct: true,
      }),
    );
  });
  it.each([0, -1, 65536, 1.5, NaN])("rejects invalid ports %s", (port) => {
    expect(() => createProfileConfig("WIREGUARD_UDP", "DE", port)).toThrow(
      "UNSUPPORTED_CONFIGURATION",
    );
  });
  it.each(Object.keys(connectionProfiles) as ProfileId[])(
    "rejects incompatible settings for %s",
    (id) => {
      const profile = connectionProfiles[id];
      const config = createProfileConfig(id, "DE");
      for (const change of [
        { transport: "invalid" },
        { encryption_mode: "TLS_1_2" },
        { obfuscation_mode: "CUSTOM" },
        { routing_mode: "SPLIT" },
        { dns_mode: "SYSTEM" },
        { country: "invalid" },
        { mtu: 9000 },
      ]) {
        expect(validateProfileConfig(profile, { ...config, ...change })).toBe(
          false,
        );
      }
      expect(profile.supports_ipv6).toBe(false);
      expect(profile.supports_obfuscation).toBe(id !== "MASQUE_QUIC");
    },
  );
});

describe.each(["OPENVPN_TLS_TCP", "MASQUE_QUIC"] as const)(
  "%s external adapter",
  (id) => {
    const config = {
      ...createProfileConfig(id, "DE"),
      parameters: secureParameters,
    };
    it("fails explicitly without an installed runtime", async () => {
      const adapter = createProfileAdapter(id);
      expect(await adapter.connect(config)).toMatchObject({
        failure_code: "RUNTIME_UNAVAILABLE",
        tunnel_established: false,
      });
      expect(await adapter.health()).toMatchObject({
        failure_code: "RUNTIME_UNAVAILABLE",
      });
    });
    it("never forwards insecure or executable configuration", async () => {
      const external = runtime();
      const adapter = createProfileAdapter(id, {
        openvpn: external,
        masque: external,
      });
      for (const parameters of [
        { ...secureParameters, verify_certificate: false },
        { ...secureParameters, credential_ref: "secret\ncommand" },
        { ...secureParameters, endpoint: "host;run" },
        { ...secureParameters, trust_ref: "" },
      ]) {
        expect(await adapter.connect({ ...config, parameters })).toMatchObject({
          failure_code: "UNSUPPORTED_CONFIGURATION",
        });
      }
      expect(
        await adapter.connect({
          ...config,
          transport: id === "MASQUE_QUIC" ? "TCP" : "UDP",
        }),
      ).toMatchObject({ failure_code: "UNSUPPORTED_CONFIGURATION" });
      expect(external.start).not.toHaveBeenCalled();
    });
    it("redacts runtime output, rolls back failure and does not try another candidate", async () => {
      const external = runtime();
      vi.mocked(external.start).mockRejectedValue(new Error("password=secret"));
      const adapter = createProfileAdapter(id, {
        openvpn: external,
        masque: external,
      });
      await expect(
        connectFirstCandidate(adapter, [config, config]),
      ).rejects.toThrow("UNKNOWN");
      expect(external.start).toHaveBeenCalledOnce();
      expect(external.stop).toHaveBeenCalledOnce();
      vi.mocked(external.health).mockResolvedValue({
        tunnel_established: true,
        internet_verified: true,
        private_key: "secret",
        diagnostics: { token: "secret" },
      });
      expect(JSON.stringify(await adapter.health())).not.toContain("secret");
      expect(await adapter.diagnostics()).toEqual({
        status: "UP",
        transport_healthy: true,
        tx_bytes: 0,
        rx_bytes: 0,
      });
      vi.mocked(external.status).mockRejectedValue(new Error("secret"));
      await expect(adapter.status()).rejects.toThrow(
        "PROTOCOL_STATUS_UNAVAILABLE",
      );
      vi.mocked(external.stop).mockRejectedValue(new Error("secret"));
      await expect(adapter.disconnect()).rejects.toThrow(
        "PROTOCOL_DISCONNECT_FAILED",
      );
    });
    it("does not forward unknown configuration fields or ignore a runtime failure", async () => {
      const external = runtime();
      vi.mocked(external.start).mockResolvedValue({
        tunnel_established: true,
        internet_verified: true,
        failure_code: "secret-error",
      });
      const adapter = createProfileAdapter(id, {
        openvpn: external,
        masque: external,
      });
      const injected = {
        ...config,
        command: "unexpected",
        node_id: "internal",
      };
      expect(await adapter.connect(injected)).toMatchObject({
        failure_code: "UNKNOWN",
        internet_verified: false,
      });
      expect(vi.mocked(external.start).mock.calls[0][0].config).toEqual(
        createProfileConfig(id, "DE"),
      );
      expect(external.stop).toHaveBeenCalledOnce();
    });

    it("requires Internet verification and rolls back an unverified tunnel", async () => {
      const external = runtime();
      vi.mocked(external.health).mockResolvedValue({
        tunnel_established: true,
        internet_verified: false,
      });
      const adapter = createProfileAdapter(id, {
        openvpn: external,
        masque: external,
      });
      expect(await adapter.connect(config)).toMatchObject({
        failure_code: "TUNNEL_ESTABLISHED_NO_TRAFFIC",
      });
      expect(external.stop).toHaveBeenCalledOnce();
    });
  },
);

it.each([
  [undefined, "TUNNEL_ESTABLISHED_NO_TRAFFIC"],
  [
    { dns_verified: false, https_verified: true, route_verified: true },
    "DNS_FAILED",
  ],
  [
    { dns_verified: true, https_verified: false, route_verified: true },
    "HTTPS_CHECK_FAILED",
  ],
  [
    { dns_verified: true, https_verified: true, route_verified: false },
    "ROUTE_LEAK_DETECTED",
  ],
  [
    {
      dns_verified: true,
      https_verified: true,
      route_verified: true,
      egress_matches: false,
    },
    "EGRESS_MISMATCH",
  ],
])(
  "external adapters require independent evidence: %j",
  async (verification, failure_code) => {
    const external = runtime();
    vi.mocked(external.health).mockResolvedValue({
      tunnel_established: true,
      internet_verified: true,
      verification,
    });
    const adapter = createProfileAdapter("OPENVPN_TLS_TCP", {
      openvpn: external,
    });
    const result = await adapter.connect({
      ...createProfileConfig("OPENVPN_TLS_TCP", "DE"),
      parameters: secureParameters,
    });
    expect(result).toMatchObject({ internet_verified: false, failure_code });
    expect(external.health).toHaveBeenCalledOnce();
    expect(external.stop).toHaveBeenCalledOnce();
  },
);
