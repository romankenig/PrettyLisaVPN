import { describe, expect, it, vi } from "vitest";
import { createWireGuardProtocol, wireGuardDefaults } from "../vpn/wireguard";
import { createVpnConnectionManager } from "../vpn/connection";
import type { WireGuardTunnelController } from "../native/wireguardTransport";
import type { ApiClient } from "../api/client";
import type { VpnProtocol } from "../vpn/protocol";

const key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
const parameters = {
  endpoint: { ipv4: "192.0.2.20", port: 51820 },
  server_public_key: key,
  client_address: "10.77.0.2/32",
  dns: ["1.1.1.1"],
  allowed_ips: ["0.0.0.0/0"],
};
function controller(): WireGuardTunnelController {
  return {
    start: vi.fn().mockResolvedValue("UP"),
    stop: vi.fn().mockResolvedValue("DOWN"),
    state: vi.fn().mockResolvedValue("UP"),
    verify: vi.fn().mockResolvedValue({
      tunnel_established: true,
      internet_verified: true,
      failure_code: null,
    }),
    diagnostics: vi.fn().mockResolvedValue({
      peerPublicKey: key,
      endpoint: "127.0.0.1:12345",
      publicEndpoint: "192.0.2.20:51820",
      allowedIps: ["0.0.0.0/0"],
      persistentKeepalive: 25,
      txBytes: 100,
      rxBytes: 200,
      transportMode: "WG_OBFUSCATOR",
      transportHealthy: true,
      private_key: "must-never-escape",
      token: "must-never-escape",
    }),
  };
}

describe("public connection facts", () => {
  it("uses runtime transport and public endpoint, not the backend's preferred mode or local proxy", async () => {
    const tunnel = controller();
    const protocol = createWireGuardProtocol(tunnel);
    await protocol.connect({ ...wireGuardDefaults("DE", 51820), parameters });
    const details = await protocol.connectionDetails!();
    expect(details).toMatchObject({
      protocol: "WireGuard",
      transport: "UDP",
      server: "192.0.2.20:51820",
      encryption: "ChaCha20-Poly1305",
      obfuscation: "wg-obfuscator",
      mtu: 1280,
      dns: ["1.1.1.1"],
      clientAddress: "10.77.0.2/32",
      serverPublicKey: key,
      keepalive: 25,
    });
    expect(JSON.stringify(details)).not.toContain("127.0.0.1");
    expect(JSON.stringify(details)).not.toContain("must-never-escape");
  });

  it("does not invent DNS/client configuration after restoration", async () => {
    const details =
      await createWireGuardProtocol(controller()).connectionDetails!();
    expect(details?.server).toBe("192.0.2.20:51820");
    expect(details).not.toHaveProperty("dns");
    expect(details).not.toHaveProperty("clientAddress");
  });

  it("rejects unknown transports and invalid public endpoints", async () => {
    const tunnel = controller();
    vi.mocked(tunnel.diagnostics).mockResolvedValueOnce({
      ...(await tunnel.diagnostics())!,
      publicEndpoint: "credentials@host.invalid",
    });
    expect(
      await createWireGuardProtocol(tunnel).connectionDetails!(),
    ).toBeNull();
    vi.mocked(tunnel.state).mockResolvedValue("DOWN");
    expect(
      await createWireGuardProtocol(tunnel).connectionDetails!(),
    ).toBeNull();
  });

  it("does not publish details from a session that ended during the read", async () => {
    let finish!: (value: null) => void;
    const protocol: VpnProtocol = {
      ...createWireGuardProtocol(controller()),
      connectionDetails: vi.fn(
        () =>
          new Promise<null>((resolve) => {
            finish = resolve;
          }),
      ),
    };
    const response = {
      session_id: "session",
      status: "ACTIVE" as const,
      country_code: "DE",
      expires_at: null,
      server_time: "2026-10-17T00:00:00Z",
      transport: parameters,
    };
    const api = {
      getCurrentVpnSession: vi.fn().mockResolvedValue({ session: response }),
      disconnectVpnSession: vi.fn().mockResolvedValue({}),
    } as unknown as ApiClient;
    const connection = createVpnConnectionManager(
      api,
      { create: async () => response, candidates: () => [] },
      protocol,
    );
    try {
      await connection.reconcile("access");
      const pending = connection.connectionDetails!();
      await connection.disconnect("access");
      finish(null);
      expect(await pending).toBeNull();
    } finally {
      connection.dispose();
    }
  });
});
