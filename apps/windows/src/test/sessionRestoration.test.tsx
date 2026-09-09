import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import {
  ApiError,
  type ApiClient,
  type MeResponse,
  type RefreshResponse,
} from "../api/client";
import { createSessionRestoration } from "../auth/restoration";
import { createAuthenticationSession } from "../auth/session";
import { loadConfig } from "../config/config";
import type {
  CredentialStorage,
  RefreshCredential,
} from "../native/credentialStorage";
import type { InstallationId } from "../native/installationId";
import { ApplicationProvider } from "../state/application";
import { App } from "../ui/App";
import { SessionRestorationGate } from "../ui/SessionRestorationGate";

const stored: RefreshCredential = {
  sessionId: "123e4567-e89b-42d3-a456-426614174001",
  refreshToken: "stored-refresh-token",
  expiresAt: "2026-10-09T00:00:00Z",
};
const refreshed: RefreshResponse = {
  token_type: "bearer",
  access_token: "restored-access-token",
  access_token_expires_in: 900,
  refresh_token: "rotated-refresh-token",
  refresh_token_expires_at: "2026-11-09T00:00:00Z",
  session_id: stored.sessionId,
};
const profile: MeResponse = {
  id: "123e4567-e89b-42d3-a456-426614174002",
  email: "user@example.com",
  plan: "PREMIUM",
  active_device_count: 2,
};

function mockApi(): ApiClient {
  return {
    getHealth: vi.fn().mockResolvedValue({ status: "ok" }),
    getVersion: vi.fn().mockResolvedValue({
      application_name: "PrettyLisaVPN Backend",
      application_version: "test",
      environment: "test",
    }),
    requestOtp: vi.fn(),
    verifyOtp: vi.fn(),
    refresh: vi.fn().mockResolvedValue(refreshed),
    me: vi.fn().mockResolvedValue(profile),
    logout: vi.fn().mockResolvedValue({ status: "logged_out" }),
  };
}

function mockStorage(
  value: RefreshCredential | null = stored,
): CredentialStorage {
  return {
    save: vi.fn().mockResolvedValue(undefined),
    retrieve: vi.fn().mockResolvedValue(value),
    replace: vi.fn().mockResolvedValue(undefined),
    delete: vi.fn().mockResolvedValue(undefined),
  };
}

function renderStartup(
  api: ApiClient,
  storage: CredentialStorage,
  now: () => number = () => Date.parse("2026-09-09T00:00:00Z"),
) {
  const session = createAuthenticationSession(storage);
  const restoration = createSessionRestoration(api, storage, session, now);
  render(
    <ApplicationProvider
      value={{
        config: loadConfig({}),
        api,
        desktop: { getVersion: async () => "0.1.0" },
        installationId: {
          getInstallationId: async () =>
            "123e4567-e89b-42d3-a456-426614174000" as InstallationId,
        },
        session,
        sessionRestoration: restoration,
      }}
    >
      <MemoryRouter initialEntries={["/"]}>
        <SessionRestorationGate restoration={restoration} session={session}>
          <App />
        </SessionRestorationGate>
      </MemoryRouter>
    </ApplicationProvider>,
  );
  return { session, restoration };
}

describe("authentication session restoration", () => {
  it("shows Email login on first launch without stored credentials", async () => {
    const api = mockApi();
    renderStartup(api, mockStorage(null));

    expect(
      await screen.findByRole("heading", { name: "войти по email" }),
    ).toBeInTheDocument();
    expect(api.refresh).not.toHaveBeenCalled();
  });

  it("rotates credentials, loads /me, and opens Home", async () => {
    const api = mockApi();
    const storage = mockStorage();
    const { session } = renderStartup(api, storage);

    expect(await screen.findByText(profile.email)).toBeInTheDocument();
    expect(api.refresh).toHaveBeenCalledWith({
      session_id: stored.sessionId,
      refresh_token: stored.refreshToken,
    });
    expect(storage.replace).toHaveBeenCalledWith({
      sessionId: refreshed.session_id,
      refreshToken: refreshed.refresh_token,
      expiresAt: refreshed.refresh_token_expires_at,
    });
    expect(api.me).toHaveBeenCalledWith(refreshed.access_token);
    expect(session.current()).toEqual({
      accessToken: refreshed.access_token,
      accessTokenExpiresIn: 900,
      sessionId: stored.sessionId,
      userId: profile.id,
      deviceId: null,
      plan: "PREMIUM",
      profile,
    });
  });

  it("clears a locally expired session without refreshing", async () => {
    const api = mockApi();
    const storage = mockStorage({
      ...stored,
      expiresAt: "2026-09-01T00:00:00Z",
    });
    renderStartup(api, storage);

    expect(
      await screen.findByRole("heading", { name: "войти по email" }),
    ).toBeInTheDocument();
    expect(storage.delete).toHaveBeenCalledOnce();
    expect(api.refresh).not.toHaveBeenCalled();
  });

  it("clears a revoked server session and returns to Login", async () => {
    const api = mockApi();
    vi.mocked(api.refresh).mockRejectedValue(new ApiError("AUTH_INVALID"));
    const storage = mockStorage();
    renderStartup(api, storage);

    expect(
      await screen.findByRole("heading", { name: "войти по email" }),
    ).toBeInTheDocument();
    expect(storage.delete).toHaveBeenCalledOnce();
  });

  it("preserves credentials on temporary network failure and allows retry", async () => {
    const api = mockApi();
    vi.mocked(api.refresh)
      .mockRejectedValueOnce(new ApiError("NETWORK_ERROR"))
      .mockResolvedValueOnce(refreshed);
    const storage = mockStorage();
    renderStartup(api, storage);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Backend временно недоступен",
    );
    expect(storage.delete).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "повторить" }));

    expect(await screen.findByText(profile.email)).toBeInTheDocument();
    expect(api.refresh).toHaveBeenCalledTimes(2);
  });

  it("deduplicates concurrent startup refresh attempts", async () => {
    let resolveRefresh!: (value: RefreshResponse) => void;
    const api = mockApi();
    vi.mocked(api.refresh).mockImplementation(
      () => new Promise((resolve) => (resolveRefresh = resolve)),
    );
    const storage = mockStorage();
    const session = createAuthenticationSession(storage);
    const restoration = createSessionRestoration(api, storage, session);

    const first = restoration.restore();
    const second = restoration.restore();
    await waitFor(() => expect(api.refresh).toHaveBeenCalledOnce());
    resolveRefresh(refreshed);

    await expect(Promise.all([first, second])).resolves.toEqual([
      "authenticated",
      "authenticated",
    ]);
    expect(storage.replace).toHaveBeenCalledOnce();
  });
});
