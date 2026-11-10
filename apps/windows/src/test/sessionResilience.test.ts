import { afterEach, expect, it, vi } from "vitest";
import { ApiError, type RefreshResponse } from "../api/client";
import { createAuthenticationSession } from "../auth/session";
import { createSessionTransport } from "../auth/transport";
import { CredentialStorageError } from "../native/credentialStorage";
import { createTestCredentialStorage } from "./fakes";

afterEach(() => vi.useRealTimers());
const credentials = {
  accessToken: "original-access",
  accessTokenExpiresIn: 900,
  refreshToken: "original-refresh",
  refreshTokenExpiresAt: "2035-01-01T00:00:00Z",
  sessionId: crypto.randomUUID(),
  userId: crypto.randomUUID(),
  deviceId: crypto.randomUUID(),
  plan: "PREMIUM" as const,
};
const refreshed: RefreshResponse = {
  token_type: "bearer",
  access_token: "new-access",
  access_token_expires_in: 900,
  refresh_token: "new-refresh",
  refresh_token_expires_at: credentials.refreshTokenExpiresAt,
  session_id: credentials.sessionId,
};
async function setup(expired = true) {
  const storage = createTestCredentialStorage();
  const session = createAuthenticationSession(storage);
  await session.establish({
    ...credentials,
    accessTokenExpiresIn: expired ? 0 : 900,
  });
  const api = { refresh: vi.fn().mockResolvedValue(refreshed), me: vi.fn() };
  return { storage, session, api };
}

it.each([
  "NETWORK_ERROR",
  "TIMEOUT",
  "SERVER_ERROR",
  "INVALID_RESPONSE",
] as const)(
  "keeps login on %s and retries the same durable operation",
  async (code) => {
    const { storage, session, api } = await setup();
    api.refresh.mockRejectedValueOnce(new ApiError(code));
    const results = await Promise.allSettled([
      session.bearer(api),
      session.bearer(api),
    ]);
    expect(results.every((r) => r.status === "rejected")).toBe(true);
    expect(session.current()?.userId).toBe(credentials.userId);
    expect(api.refresh).toHaveBeenCalledOnce();
    const pending = await storage.retrieve();
    expect(pending?.refreshToken).toBe(credentials.refreshToken);
    expect(pending?.rotationId).toBeTruthy();
    await expect(session.bearer(api)).resolves.toBe("new-access");
    expect(api.refresh.mock.calls[0][0]).toEqual(api.refresh.mock.calls[1][0]);
    expect((await storage.retrieve())?.rotationId).toBeUndefined();
  },
);

it("retains a pending rotation when saving its response fails", async () => {
  const { storage, session, api } = await setup();
  const replace = storage.replace;
  storage.replace = vi
    .fn()
    .mockImplementationOnce(replace)
    .mockRejectedValueOnce(new CredentialStorageError())
    .mockImplementation(replace);
  await expect(session.bearer(api)).rejects.toBeInstanceOf(
    CredentialStorageError,
  );
  expect(session.current()).not.toBeNull();
  await expect(session.bearer(api)).resolves.toBe("new-access");
  expect(api.refresh.mock.calls[0][0]).toEqual(api.refresh.mock.calls[1][0]);
});

it.each(["AUTH_INVALID", "AUTH_FORBIDDEN"] as const)(
  "ends a confirmed %s session",
  async (code) => {
    const { storage, session, api } = await setup();
    api.refresh.mockRejectedValue(new ApiError(code));
    await expect(session.bearer(api)).rejects.toEqual(new ApiError(code));
    expect(session.current()).toBeNull();
    expect(await storage.retrieve()).toBeNull();
  },
);

it("a late refresh cannot restore login after explicit logout", async () => {
  const { storage, session, api } = await setup();
  let resolve!: (value: RefreshResponse) => void;
  api.refresh.mockImplementation(
    () =>
      new Promise<RefreshResponse>((r) => {
        resolve = r;
      }),
  );
  const renewing = session.bearer(api);
  await vi.waitFor(() => expect(api.refresh).toHaveBeenCalledOnce());
  const result = renewing.catch(() => undefined);
  const clearing = session.clear();
  resolve(refreshed);
  await Promise.all([result, clearing]);
  expect(session.current()).toBeNull();
  expect(await storage.retrieve()).toBeNull();
});

it("refreshes an idle UI request before using an expired access token", async () => {
  vi.useFakeTimers();
  const { session, api } = await setup(false);
  await vi.advanceTimersByTimeAsync(901000);
  const transport = vi.fn().mockResolvedValue(Response.json({ ok: true }));
  const send = createSessionTransport(
    "https://api.example.test",
    transport,
    session,
    api,
  );
  await send("https://api.example.test/me", {
    headers: { Authorization: `Bearer ${credentials.accessToken}` },
  });
  expect(api.refresh).toHaveBeenCalledOnce();
  expect(
    new Headers(transport.mock.calls[0][1].headers).get("Authorization"),
  ).toBe("Bearer new-access");
  expect(session.current()).not.toBeNull();
});

it("retries an expired-token response once, sharing the refresh with VPN requests", async () => {
  const { session, api } = await setup(false);
  const transport = vi
    .fn()
    .mockResolvedValueOnce(
      Response.json(
        { error: { code: "invalid_access_token" } },
        { status: 401 },
      ),
    )
    .mockResolvedValueOnce(Response.json({ ok: true }));
  const send = createSessionTransport(
    "https://api.example.test",
    transport,
    session,
    api,
  );
  expect(
    (
      await send("https://api.example.test/me", {
        headers: { Authorization: `Bearer ${credentials.accessToken}` },
      })
    ).status,
  ).toBe(200);
  expect(api.refresh).toHaveBeenCalledOnce();
  expect(transport).toHaveBeenCalledTimes(2);
});

it("does not refresh revoked sessions or substitute credentials into foreign/old-account requests", async () => {
  const { session, api } = await setup(false);
  const transport = vi
    .fn()
    .mockImplementation(async () =>
      Response.json({ error: { code: "invalid_session" } }, { status: 401 }),
    );
  const send = createSessionTransport(
    "https://api.example.test",
    transport,
    session,
    api,
  );
  const init = {
    headers: { Authorization: `Bearer ${credentials.accessToken}` },
  };
  expect((await send("https://api.example.test/me", init)).status).toBe(401);
  await expect(send("https://other.example.test/me", init)).rejects.toThrow(
    "AUTH_DESTINATION_INVALID",
  );
  expect(api.refresh).not.toHaveBeenCalled();
  await session.establish({
    ...credentials,
    userId: "other",
    sessionId: "other",
    accessToken: "other",
  });
  await expect(send("https://api.example.test/me", init)).rejects.toThrow(
    "AUTH_CHANGED",
  );
  expect(transport).toHaveBeenCalledOnce();
});
