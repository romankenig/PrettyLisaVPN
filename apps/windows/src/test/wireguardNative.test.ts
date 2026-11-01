import { beforeEach, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { wireGuardNative } from "../vpn/wireguard";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("../vpn/traffic", () => ({
  getDeviceTrafficSelection: () => ({ current: () => ({}) }),
  routingPolicy: () => ({ mode: "all", domains: [] }),
}));
beforeEach(() => {
  vi.mocked(invoke).mockReset();
});

it("uses the installed service even for the full WireGuard tunnel", async () => {
  vi.mocked(invoke).mockResolvedValue(true);
  await wireGuardNative.prepare();
  await wireGuardNative.start(
    {
      address: "10.88.1.2/32",
      endpoint: "5.181.49.183:51820",
      server_public_key: "public",
      mtu: 1380,
      dns: [],
      allowed_ips: [],
    },
    { id: "session", country: "DE" },
  );
  await wireGuardNative.verify("10.88.1.2/32", "session", "token");
  await wireGuardNative.isUp();
  await wireGuardNative.stop();
  expect(vi.mocked(invoke).mock.calls.map(([name]) => name)).toEqual([
    "wg_prepare",
    "wg_start_routed",
    "engine_verify",
    "engine_is_up",
    "wg_stop",
  ]);
  expect(invoke).toHaveBeenCalledWith(
    "wg_start_routed",
    expect.objectContaining({
      routing: { mode: "all", domains: [] },
      sessionId: "session",
    }),
  );
});

it("does not hide unconfirmed service cleanup", async () => {
  vi.mocked(invoke).mockRejectedValue("ENGINE_CLEANUP_FAILED");
  await expect(wireGuardNative.stop()).rejects.toBe("ENGINE_CLEANUP_FAILED");
});
