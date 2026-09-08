import { describe, expect, it, vi } from "vitest";
import { createInstallationIdProvider } from "../native/installationId";

describe("installation ID native boundary", () => {
  it("returns the persisted UUID supplied by the native store", async () => {
    const load = vi
      .fn<() => Promise<unknown>>()
      .mockResolvedValue("123e4567-e89b-42d3-a456-426614174000");
    const provider = createInstallationIdProvider(load);

    await expect(provider.getInstallationId()).resolves.toBe(
      "123e4567-e89b-42d3-a456-426614174000",
    );
    await expect(provider.getInstallationId()).resolves.toBe(
      "123e4567-e89b-42d3-a456-426614174000",
    );
    expect(load).toHaveBeenCalledTimes(2);
  });

  it.each(["not-a-uuid", "123e4567-e89b-12d3-a456-426614174000", null])(
    "rejects invalid native value %s",
    async (value) => {
      const provider = createInstallationIdProvider(async () => value);

      await expect(provider.getInstallationId()).rejects.toThrow(
        "INSTALLATION_ID_UNAVAILABLE",
      );
    },
  );

  it("does not expose native error details", async () => {
    const provider = createInstallationIdProvider(async () => {
      throw new Error("C:\\Users\\secret\\configuration");
    });

    await expect(provider.getInstallationId()).rejects.toThrow(
      "INSTALLATION_ID_UNAVAILABLE",
    );
  });
});
