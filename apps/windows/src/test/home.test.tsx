import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ApiError, type ApiClient, type MeResponse } from "../api/client";
import { createAuthenticationSession } from "../auth/session";
import { loadConfig } from "../config/config";
import type { CredentialStorage } from "../native/credentialStorage";
import type { InstallationId } from "../native/installationId";
import type { VpnConnectionManager } from "../vpn/connection";
import { ApplicationProvider } from "../state/application";
import { App } from "../ui/App";
import {
  createTestCredentialStorage,
  createTestSessionRestoration,
  createTestVpnConnection,
} from "./fakes";

const profile: MeResponse = {
  id: "123e4567-e89b-42d3-a456-426614174002",
  email: "user@example.com",
  plan: "PREMIUM",
  active_device_count: 3,
};

function mockApi(): ApiClient {
  return {
    getHealth: vi.fn(),
    getVersion: vi.fn(),
    requestOtp: vi.fn(),
    verifyOtp: vi.fn(),
    refresh: vi.fn(),
    me: vi.fn().mockResolvedValue(profile),
    logout: vi.fn().mockResolvedValue({ status: "logged_out" }),
    listDevices: vi.fn().mockResolvedValue([]),
    revokeDevice: vi.fn(),
    listVpnCountries: vi.fn().mockResolvedValue({
      autopilot: { quality: 90, available: true },
      countries: [],
    }),
    createVpnSession: vi.fn(),
    getCurrentVpnSession: vi.fn().mockResolvedValue({ session: null }),
    disconnectVpnSession: vi.fn(),
  };
}

function renderWithSession(
  api: ApiClient,
  storage: CredentialStorage,
  session: ReturnType<typeof createAuthenticationSession>,
  vpnConnection: VpnConnectionManager = createTestVpnConnection(),
) {
  const result = render(
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
        sessionRestoration: createTestSessionRestoration(),
        vpnConnection,
      }}
    >
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    </ApplicationProvider>,
  );
  return { ...result, session, storage };
}

function renderRestored(
  api = mockApi(),
  storage = createTestCredentialStorage(),
  vpnConnection: VpnConnectionManager = createTestVpnConnection(),
) {
  const session = createAuthenticationSession(storage);
  session.activateRestored({
    accessToken: "access-token",
    accessTokenExpiresIn: 900,
    sessionId: "123e4567-e89b-42d3-a456-426614174001",
    userId: profile.id,
    plan: profile.plan,
    profile,
  });
  return renderWithSession(api, storage, session, vpnConnection);
}

async function renderFresh(api: ApiClient) {
  const storage = createTestCredentialStorage();
  const session = createAuthenticationSession(storage);
  await session.establish({
    accessToken: "access-token",
    accessTokenExpiresIn: 900,
    refreshToken: "refresh-token",
    refreshTokenExpiresAt: "2026-10-09T00:00:00Z",
    sessionId: "123e4567-e89b-42d3-a456-426614174001",
    userId: profile.id,
    deviceId: "123e4567-e89b-42d3-a456-426614174003",
    plan: "FREE",
  });
  return renderWithSession(api, storage, session);
}

describe("authenticated Home", () => {
  it("loads real /me data after a fresh login", async () => {
    let resolveProfile!: (value: MeResponse) => void;
    const api = mockApi();
    vi.mocked(api.me).mockImplementation(
      () => new Promise((resolve) => (resolveProfile = resolve)),
    );
    await renderFresh(api);

    expect(screen.getByText(/загружаем данные аккаунта/)).toHaveTextContent(
      "загружаем данные аккаунта",
    );
    resolveProfile(profile);

    expect(await screen.findByText(profile.email)).toBeInTheDocument();
    expect(screen.getByText("PREMIUM")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("активен")).toBeInTheDocument();
    expect(api.me).toHaveBeenCalledWith(
      "access-token",
      expect.any(AbortSignal),
    );
  });

  it("reuses the /me profile loaded during restoration", () => {
    const api = mockApi();
    renderRestored(api);

    expect(screen.getByText(profile.email)).toBeInTheDocument();
    expect(api.me).not.toHaveBeenCalled();
    expect(screen.getByText("Not connected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "CONNECT" })).toBeDisabled();
    expect(
      screen.getByText("загружаем доступные локации…"),
    ).toBeInTheDocument();
  });

  it("shows backend errors and retries /me", async () => {
    const api = mockApi();
    vi.mocked(api.me)
      .mockRejectedValueOnce(new ApiError("NETWORK_ERROR"))
      .mockResolvedValueOnce(profile);
    await renderFresh(api);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Не удалось подключиться",
    );
    fireEvent.click(screen.getByRole("button", { name: "повторить" }));

    expect(await screen.findByText(profile.email)).toBeInTheDocument();
    expect(api.me).toHaveBeenCalledTimes(2);
  });

  it("logs out through the backend and clears secure credentials", async () => {
    const api = mockApi();
    const storage = createTestCredentialStorage();
    storage.delete = vi.fn(storage.delete);
    const { session } = renderRestored(api, storage);

    fireEvent.click(screen.getByRole("button", { name: "выйти" }));

    await waitFor(() =>
      expect(api.logout).toHaveBeenCalledWith("access-token"),
    );
    await waitFor(() => expect(storage.delete).toHaveBeenCalledOnce());
    expect(session.current()).toBeNull();
  });

  it("preserves the session when logout fails temporarily", async () => {
    const api = mockApi();
    vi.mocked(api.logout).mockRejectedValue(new ApiError("NETWORK_ERROR"));
    const { session } = renderRestored(api);

    fireEvent.click(screen.getByRole("button", { name: "выйти" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Не удалось завершить сессию",
    );
    expect(session.current()).not.toBeNull();
  });

  it("navigates to the Devices section", async () => {
    renderRestored();

    fireEvent.click(screen.getAllByRole("link", { name: "устройства" })[0]);

    expect(
      await screen.findByRole("heading", { name: "устройства" }),
    ).toBeInTheDocument();
  });

  it("shows CONNECTING and only reports Connected after orchestration confirmation", async () => {
    let finishConnection!: () => void;
    let connectionState: ReturnType<VpnConnectionManager["current"]> = {
      phase: "DISCONNECTED",
      backend: "NONE",
      tunnel: "DOWN",
    };
    const listeners = new Set<() => void>();
    const vpnConnection: VpnConnectionManager = {
      current: () => connectionState,
      subscribe: (listener) => {
        listeners.add(listener);
        return () => listeners.delete(listener);
      },
      reconcile: vi.fn().mockResolvedValue(undefined),
      connect: vi.fn(async () => {
        connectionState = {
          phase: "CONNECTING",
          backend: "UNKNOWN",
          tunnel: "UNKNOWN",
        };
        listeners.forEach((listener) => listener());
        await new Promise<void>((resolve) => {
          finishConnection = resolve;
        });
        connectionState = {
          phase: "CONNECTED",
          backend: "ACTIVE",
          tunnel: "UP",
          session: {
            sessionId: "123e4567-e89b-42d3-a456-426614174020",
            countryCode: "DE",
            expiresAt: null,
            remainingSeconds: 615,
          },
        };
        listeners.forEach((listener) => listener());
      }),
      disconnect: vi.fn(async () => {
        const session =
          connectionState.phase === "CONNECTED"
            ? connectionState.session
            : {
                sessionId: "123e4567-e89b-42d3-a456-426614174020",
                countryCode: "DE",
                expiresAt: null,
                remainingSeconds: null,
              };
        connectionState = {
          phase: "DISCONNECTING",
          backend: "ACTIVE",
          tunnel: "UP",
          session,
        };
        listeners.forEach((listener) => listener());
        connectionState = {
          phase: "DISCONNECTED",
          backend: "NONE",
          tunnel: "DOWN",
        };
        listeners.forEach((listener) => listener());
      }),
      dispose: vi.fn(),
    };
    const rendered = renderRestored(
      mockApi(),
      createTestCredentialStorage(),
      vpnConnection,
    );
    rendered.session.updateProfile("access-token", {
      ...profile,
      plan: "FREE",
    });
    const connectButton = await screen.findByRole("button", {
      name: "CONNECT",
    });
    await waitFor(() => expect(connectButton).toBeEnabled());

    fireEvent.click(connectButton);
    expect(screen.getByRole("button", { name: "CONNECTING" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "CONNECTING" }));
    expect(vpnConnection.connect).toHaveBeenCalledOnce();

    finishConnection();
    expect(
      await screen.findByRole("heading", { name: "Connected" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Локация: Германия")).toBeInTheDocument();
    expect(screen.getByRole("timer")).toHaveTextContent("Осталось: 10:15");

    fireEvent.click(screen.getByRole("button", { name: "DISCONNECT" }));
    expect(
      await screen.findByRole("heading", { name: "Not connected" }),
    ).toBeInTheDocument();
    expect(vpnConnection.disconnect).toHaveBeenCalledOnce();
  });
});
