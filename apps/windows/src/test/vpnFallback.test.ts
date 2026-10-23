import { describe, expect, it, vi } from "vitest";
import { connectCandidates, type VpnProtocol } from "../vpn/protocol";
import { wireGuardDefaults } from "../vpn/wireguard";

const candidates = [51820, 443, 5443].map((port) => ({
  ...wireGuardDefaults("DE", port),
  parameters: null,
}));
const failed = {
  tunnel_established: true,
  internet_verified: false,
  failure_code: "DNS_FAILED",
};
const verified = {
  tunnel_established: true,
  internet_verified: true,
  failure_code: null,
};
function runtime() {
  return {
    connect: vi.fn().mockResolvedValue(failed),
    disconnect: vi.fn().mockResolvedValue("DOWN"),
  } as unknown as VpnProtocol;
}
describe("verified candidate fallback", () => {
  it("stops failed attempts in order and stops trying after verified Internet", async () => {
    const protocol = runtime();
    vi.mocked(protocol.connect)
      .mockResolvedValueOnce(failed as never)
      .mockResolvedValueOnce(verified as never);
    expect(await connectCandidates(protocol, candidates)).toBe(candidates[1]);
    expect(protocol.connect).toHaveBeenCalledTimes(2);
    expect(protocol.disconnect).toHaveBeenCalledTimes(1);
    expect(
      vi.mocked(protocol.connect).mock.invocationCallOrder[0],
    ).toBeLessThan(vi.mocked(protocol.disconnect).mock.invocationCallOrder[0]);
    expect(
      vi.mocked(protocol.disconnect).mock.invocationCallOrder[0],
    ).toBeLessThan(vi.mocked(protocol.connect).mock.invocationCallOrder[1]);
  });
  it("tries every candidate once when handshake never proves usable Internet", async () => {
    const protocol = runtime();
    await expect(connectCandidates(protocol, candidates)).rejects.toMatchObject(
      { code: "DNS_FAILED" },
    );
    expect(protocol.connect).toHaveBeenCalledTimes(3);
    expect(protocol.disconnect).toHaveBeenCalledTimes(3);
  });
  it.each(["UP", "throws"])(
    "aborts when cleanup is unconfirmed (%s)",
    async (stop) => {
      const protocol = runtime();
      if (stop === "throws")
        vi.mocked(protocol.disconnect).mockRejectedValue(new Error("secret"));
      else vi.mocked(protocol.disconnect).mockResolvedValue("UP");
      await expect(
        connectCandidates(protocol, candidates),
      ).rejects.toMatchObject({ message: "CONNECTION_FAILED" });
      expect(protocol.connect).toHaveBeenCalledTimes(1);
    },
  );
  it("cancellation cleans a late successful attempt and prevents the next", async () => {
    const protocol = runtime();
    let current = true;
    vi.mocked(protocol.connect).mockImplementation(async () => {
      current = false;
      return verified as never;
    });
    await expect(
      connectCandidates(protocol, candidates, undefined, () => current),
    ).rejects.toBeDefined();
    expect(protocol.disconnect).toHaveBeenCalledTimes(1);
    expect(protocol.connect).toHaveBeenCalledTimes(1);
  });
  it("sanitizes a failed engine and can continue to a different one", async () => {
    const protocol = runtime();
    vi.mocked(protocol.connect)
      .mockRejectedValueOnce(new Error("secret endpoint"))
      .mockResolvedValueOnce(verified as never);
    expect(await connectCandidates(protocol, candidates)).toBe(candidates[1]);
  });
  it("rejects an oversized candidate list before touching native state", async () => {
    const protocol = runtime();
    await expect(
      connectCandidates(protocol, Array(65).fill(candidates[0])),
    ).rejects.toMatchObject({ code: "UNSUPPORTED_CONFIGURATION" });
    expect(protocol.connect).not.toHaveBeenCalled();
  });
});
