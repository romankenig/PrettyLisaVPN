import { describe, expect, it, vi } from "vitest";
import { createAuthenticationSession } from "../auth/session";
import {
  CredentialStorageError,
  createCredentialStorage,
  type RefreshCredential,
} from "../native/credentialStorage";
import { createTestCredentialStorage } from "./fakes";

const credential: RefreshCredential = {
  sessionId: "123e4567-e89b-42d3-a456-426614174001",
  refreshToken: "refresh-token",
  expiresAt: "2026-10-09T00:00:00Z",
};

describe("native credential storage adapter", () => {
  it.each([
    ["save", "save_refresh_credential"],
    ["replace", "replace_refresh_credential"],
  ] as const)(
    "maps %s to its narrow Tauri command",
    async (operation, command) => {
      const invokeNative = vi.fn().mockResolvedValue(undefined);
      const storage = createCredentialStorage(invokeNative);

      await storage[operation](credential);

      expect(invokeNative).toHaveBeenCalledWith(command, {
        credential: {
          session_id: credential.sessionId,
          refresh_token: credential.refreshToken,
          expires_at: credential.expiresAt,
        },
      });
    },
  );

  it("retrieves and deletes through dedicated commands", async () => {
    const invokeNative = vi
      .fn()
      .mockResolvedValueOnce({
        session_id: credential.sessionId,
        refresh_token: credential.refreshToken,
        expires_at: credential.expiresAt,
      })
      .mockResolvedValueOnce(undefined);
    const storage = createCredentialStorage(invokeNative);

    await expect(storage.retrieve()).resolves.toEqual(credential);
    await storage.delete();

    expect(invokeNative.mock.calls).toEqual([
      ["load_refresh_credential"],
      ["delete_refresh_credential"],
    ]);
  });

  it("returns null when no native credential exists", async () => {
    const storage = createCredentialStorage(vi.fn().mockResolvedValue(null));

    await expect(storage.retrieve()).resolves.toBeNull();
  });

  it("maps native and malformed-response failures without credential details", async () => {
    const nativeFailure = createCredentialStorage(
      vi
        .fn()
        .mockRejectedValue(new Error(`failed for ${credential.refreshToken}`)),
    );
    const malformed = createCredentialStorage(
      vi.fn().mockResolvedValue({ refresh_token: credential.refreshToken }),
    );

    await expect(nativeFailure.save(credential)).rejects.toEqual(
      new CredentialStorageError(),
    );
    await expect(malformed.retrieve()).rejects.toEqual(
      new CredentialStorageError(),
    );
  });
});

describe("authentication session", () => {
  it("keeps access credentials in memory and refresh credentials in secure storage", async () => {
    const storage = createTestCredentialStorage();
    const session = createAuthenticationSession(storage);

    await session.establish({
      accessToken: "access-token",
      accessTokenExpiresIn: 900,
      refreshToken: credential.refreshToken,
      refreshTokenExpiresAt: credential.expiresAt,
      sessionId: credential.sessionId,
      userId: "123e4567-e89b-42d3-a456-426614174002",
      deviceId: "123e4567-e89b-42d3-a456-426614174003",
      plan: "FREE",
    });

    expect(session.current()).toEqual({
      accessToken: "access-token",
      accessTokenExpiresIn: 900,
      sessionId: credential.sessionId,
      userId: "123e4567-e89b-42d3-a456-426614174002",
      deviceId: "123e4567-e89b-42d3-a456-426614174003",
      plan: "FREE",
    });
    await expect(storage.retrieve()).resolves.toEqual(credential);

    const replacement = { ...credential, refreshToken: "rotated-token" };
    await storage.replace(replacement);
    await expect(storage.retrieve()).resolves.toEqual(replacement);
    await session.clear();
    expect(session.current()).toBeNull();
    await expect(storage.retrieve()).resolves.toBeNull();
  });

  it("does not activate a session when secure storage fails", async () => {
    const storage = createTestCredentialStorage();
    storage.save = vi.fn().mockRejectedValue(new CredentialStorageError());
    const session = createAuthenticationSession(storage);

    await expect(
      session.establish({
        accessToken: "access-token",
        accessTokenExpiresIn: 900,
        refreshToken: credential.refreshToken,
        refreshTokenExpiresAt: credential.expiresAt,
        sessionId: credential.sessionId,
        userId: "123e4567-e89b-42d3-a456-426614174002",
        deviceId: "123e4567-e89b-42d3-a456-426614174003",
        plan: "FREE",
      }),
    ).rejects.toEqual(new CredentialStorageError());
    expect(session.current()).toBeNull();
  });
});
