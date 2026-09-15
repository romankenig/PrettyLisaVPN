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
