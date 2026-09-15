import { describe, expect, it, vi } from "vitest";
import {
  createWireGuardKeyManager,
  WireGuardKeyStorageError,
} from "../native/wireguardKeys";

const PUBLIC_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";

describe("native WireGuard key manager", () => {
  it("returns only the native-derived public key", async () => {
    const invokeNative = vi.fn().mockResolvedValue({ public_key: PUBLIC_KEY });
    const manager = createWireGuardKeyManager(invokeNative);

    await expect(manager.ensurePublicKey()).resolves.toBe(PUBLIC_KEY);
    expect(invokeNative).toHaveBeenCalledWith("ensure_wireguard_public_key");
    expect(JSON.stringify(invokeNative.mock.calls)).not.toContain("private");
  });

  it("loads and deletes through narrow native commands", async () => {
    const invokeNative = vi
      .fn()
      .mockResolvedValueOnce({ public_key: PUBLIC_KEY })
      .mockResolvedValueOnce(undefined);
    const manager = createWireGuardKeyManager(invokeNative);

    await expect(manager.loadPublicKey()).resolves.toBe(PUBLIC_KEY);
    await manager.delete();

    expect(invokeNative.mock.calls).toEqual([
      ["load_wireguard_public_key"],
      ["delete_wireguard_key"],
    ]);
  });

  it("returns null when no key exists", async () => {
    const manager = createWireGuardKeyManager(vi.fn().mockResolvedValue(null));
    await expect(manager.loadPublicKey()).resolves.toBeNull();
  });

  it("rejects malformed native output without echoing sensitive details", async () => {
    const manager = createWireGuardKeyManager(
      vi.fn().mockResolvedValue({ private_key: "must-not-cross-boundary" }),
    );

    await expect(manager.ensurePublicKey()).rejects.toEqual(
      new WireGuardKeyStorageError(),
    );
  });
});
