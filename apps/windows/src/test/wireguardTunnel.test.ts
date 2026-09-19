import { describe, expect, it, vi } from "vitest";
import {
  createWireGuardTunnelController,
  type WireGuardTransportConfiguration,
  WireGuardTunnelError,
} from "../native/wireguardTransport";

const configuration: WireGuardTransportConfiguration = {
  endpoint: { ipv4: "204.48.17.50", port: 51820 },
  serverPublicKey: "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE=",
  clientAddress: "10.77.0.2/16",
  dns: ["1.1.1.1"],
  allowedIps: ["0.0.0.0/0"],
};

describe("native WireGuard tunnel controller", () => {
  it("passes only backend transport configuration to native start", async () => {
    const invokeNative = vi.fn().mockResolvedValue("UP");
    const controller = createWireGuardTunnelController(invokeNative);

    await expect(controller.start(configuration)).resolves.toBe("UP");
    expect(invokeNative).toHaveBeenCalledWith("start_wireguard_tunnel", {
      configuration,
    });
    expect(JSON.stringify(invokeNative.mock.calls)).not.toContain("private");
  });

  it.each(["PRETTYLISA_V1", "WG_OBFUSCATOR"])(
    "exposes WireGuardNT peer counters with %s transport",
    async (transportMode) => {
      const diagnostics = {
        peerPublicKey: "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE=",
        endpoint: "204.48.17.50:51820",
        allowedIps: ["0.0.0.0/0"],
        persistentKeepalive: 25,
        txBytes: 128,
        rxBytes: 256,
        transportMode,
        transportHealthy: true,
        publicEndpoint: "204.48.17.50:443",
      };
      const invokeNative = vi.fn().mockResolvedValue(diagnostics);
      const controller = createWireGuardTunnelController(invokeNative);

      await expect(controller.diagnostics()).resolves.toEqual(diagnostics);
      expect(invokeNative).toHaveBeenCalledWith(
        "get_wireguard_peer_diagnostics",
      );
    },
  );

  it("stops and queries state without configuration", async () => {
    const invokeNative = vi
      .fn()
      .mockResolvedValueOnce("DOWN")
      .mockResolvedValueOnce("DOWN");
    const controller = createWireGuardTunnelController(invokeNative);

    await expect(controller.stop()).resolves.toBe("DOWN");
    await expect(controller.state()).resolves.toBe("DOWN");
    expect(invokeNative.mock.calls).toEqual([
      ["stop_wireguard_tunnel", undefined],
      ["get_wireguard_tunnel_state", undefined],
    ]);
  });

  it("maps native failures to stable errors without echoing input", async () => {
    const controller = createWireGuardTunnelController(
      vi.fn().mockRejectedValue("administrator_privileges_required"),
    );

    await expect(controller.start(configuration)).rejects.toEqual(
      new WireGuardTunnelError("administrator_privileges_required"),
    );
  });
});
