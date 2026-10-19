import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
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

beforeEach(() => localStorage.clear());

describe("authenticated Home", () => {
  it("shows public connection details only after confirmation", async () => {
    const connectedState: ReturnType<VpnConnectionManager["current"]> = {
      phase: "CONNECTED",
      backend: "ACTIVE",
      tunnel: "UP",
      session: {
        sessionId: "demo-session",
        countryCode: "DE",
        expiresAt: null,
        remainingSeconds: null,
      },
    };
    const vpnConnection: VpnConnectionManager = {
      ...createTestVpnConnection(),
      current: () => connectedState,
      connectionDetails: vi.fn().mockResolvedValue({
        protocol: "WireGuard",
        transport: "UDP",
        server: "192.0.2.20:51820",
        encryption: "ChaCha20-Poly1305",
        obfuscation: "без маскировки",
        mtu: 1280,
        dns: ["1.1.1.1"],
        serverPublicKey: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
      }),
    };
    renderRestored(mockApi(), createTestCredentialStorage(), vpnConnection);
    const info = await screen.findByLabelText("способ подключения");
    expect(info).toHaveTextContent("WireGuard · UDP · 192.0.2.20:51820");
    expect(info).toHaveTextContent("ChaCha20-Poly1305 · mtu 1280");
    fireEvent.click(within(info).getByText("параметры подключения"));
    expect(info).toHaveTextContent("публичный ключ сервера");
    expect(info).not.toHaveTextContent("access-token");
  });

  it.each([
    ["FREE", "FREE"],
    ["PREMIUM", "PREMIUM ⭐"],
    ["PLATINUM", "PLATINUM 💎"],
  ] as const)("shows the %s plan decoration", async (plan, label) => {
    const api = mockApi();
    vi.mocked(api.me).mockResolvedValue({ ...profile, plan });
    await renderFresh(api);
    expect(await screen.findByText(label)).toBeVisible();
  });

  it("keeps controls on the left and shows traffic modes on the right", async () => {
    renderRestored();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "CONNECT" })).toBeEnabled(),
    );
    expect(
      screen
        .getByRole("button", { name: "CONNECT" })
        .closest(".home-connect-panel"),
    ).not.toBeNull();
    expect(screen.getByRole("heading", { name: "что защищаем" })).toBeVisible();
    expect(screen.getByRole("radio", { name: /весь трафик/ })).toBeChecked();
    expect(
      screen.getByRole("radio", { name: /только выбранные сайты/ }),
    ).toBeDisabled();
    expect(
      screen.getByRole("radio", { name: /кроме выбранных сайтов/ }),
    ).toBeDisabled();
    expect(screen.queryByText("локация")).not.toBeInTheDocument();
  });

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
    expect(screen.getByText("PREMIUM ⭐")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.queryByText("активен")).not.toBeInTheDocument();
    expect(screen.getByText("home")).toBeInTheDocument();
    expect(screen.getByText("аккаунт")).toBeInTheDocument();
    expect(api.me).toHaveBeenCalledWith(
      "access-token",
      expect.any(AbortSignal),
    );
  });

  it("shows the restored profile while refreshing account data", () => {
    const api = mockApi();
    renderRestored(api);

    expect(screen.getByText(profile.email)).toBeInTheDocument();
    expect(api.me).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Not connected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "CONNECT" })).toBeDisabled();
    expect(
      screen.getByText("загружаем доступные локации…"),
    ).toBeInTheDocument();
  });

  it("refreshes plan and device count when returning Home", async () => {
    const api = mockApi();
    renderRestored(api);
    await waitFor(() => expect(api.me).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("link", { name: "настройки" }));
    vi.mocked(api.me).mockResolvedValue({
      ...profile,
      plan: "FREE",
      active_device_count: 1,
    });
    fireEvent.click(screen.getByRole("link", { name: "главная" }));
    expect(await screen.findByText("FREE")).toBeVisible();
    expect(screen.getByText("1")).toBeVisible();
    expect(screen.queryByText("PREMIUM ⭐")).not.toBeInTheDocument();
    expect(api.me).toHaveBeenCalledTimes(2);
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

    fireEvent.click(screen.getByRole("link", { name: "настройки" }));
    fireEvent.click(screen.getByRole("button", { name: /выйти/ }));

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

    fireEvent.click(screen.getByRole("link", { name: "настройки" }));
    fireEvent.click(screen.getByRole("button", { name: /выйти/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Не удалось завершить сессию",
    );
    expect(session.current()).not.toBeNull();
  });

  it("navigates to the Devices section", async () => {
    renderRestored();

    fireEvent.click(screen.getByRole("link", { name: "настройки" }));
    fireEvent.click(screen.getByRole("link", { name: /устройства/ }));

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
    const api = mockApi();
    vi.mocked(api.me).mockResolvedValue({ ...profile, plan: "FREE" });
    const rendered = renderRestored(
      api,
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
    expect(
      screen.getByRole("combobox", { name: /куда подключиться/ }),
    ).toBeDisabled();
    expect(screen.getByRole("timer")).toHaveTextContent("Осталось: 10:15");

    fireEvent.click(screen.getByRole("button", { name: "DISCONNECT" }));
    expect(
      await screen.findByRole("heading", { name: "Not connected" }),
    ).toBeInTheDocument();
    expect(vpnConnection.disconnect).toHaveBeenCalledOnce();
  });
});

it("UI never shows Connected when WireGuard handshake succeeds but Internet does not work", async () => {
  const { createVpnConnectionManager } = await import("../vpn/connection");
  const { createWireGuardProtocol, wireGuardDefaults } =
    await import("../vpn/wireguard");
  const api = mockApi();
  const transport = {
    endpoint: { ipv4: "192.0.2.1", port: 51820 },
    server_public_key: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    client_address: "10.77.0.2/32",
    dns: ["1.1.1.1"],
    allowed_ips: ["0.0.0.0/0"],
  };
  const backendSession = {
    session_id: "123e4567-e89b-42d3-a456-426614174020",
    status: "ACTIVE" as const,
    country_code: "DE",
    expires_at: null,
    server_time: "2026-09-21T00:00:00Z",
    transport,
  };
  let finishProbe!: (
    value: import("../native/wireguardTransport").InternetVerification,
  ) => void;
  const tunnel = {
    start: vi.fn().mockResolvedValue("UP"),
    stop: vi.fn().mockResolvedValue("DOWN"),
    state: vi.fn().mockResolvedValue("UP"),
    diagnostics: vi.fn().mockResolvedValue(null),
    verify: vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          finishProbe = resolve;
        }),
    ),
  };
  const connection = createVpnConnectionManager(
    api,
    {
      create: async () => backendSession,
      candidates: () => [
        { ...wireGuardDefaults("DE", 51820), parameters: transport },
      ],
    },
    createWireGuardProtocol(tunnel),
  );
  const phases: string[] = [];
  connection.subscribe(() => phases.push(connection.current().phase));
  renderRestored(api, createTestCredentialStorage(), connection);
  try {
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "CONNECT" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "CONNECT" }));
    await screen.findByRole("heading", { name: "VERIFYING INTERNET" });
    expect(tunnel.start).toHaveResolvedWith("UP");
    expect(
      screen.queryByRole("heading", { name: "Connected" }),
    ).not.toBeInTheDocument();
    finishProbe({
      tunnel_established: true,
      internet_verified: false,
      failure_code: "HTTPS_CHECK_FAILED",
    });
    await screen.findByRole("heading", { name: "FAILED" });
    expect(
      screen.queryByRole("heading", { name: "Connected" }),
    ).not.toBeInTheDocument();
    expect(phases).not.toContain("CONNECTED");
  } finally {
    connection.dispose();
  }
});

it("uses icon navigation in Home, Settings, About order and keeps Settings active for devices", async () => {
  renderRestored();
  const nav = screen.getByRole("navigation", { name: "основная навигация" });
  const links = within(nav).getAllByRole("link");
  expect(links.map((link) => link.getAttribute("aria-label"))).toEqual([
    "главная",
    "настройки",
    "о приложении",
  ]);
  for (const link of links) {
    expect(link.textContent).toBe("");
    expect(link.querySelector("svg")).not.toBeNull();
    expect(link).toHaveAttribute("title", link.getAttribute("aria-label"));
  }
  expect(screen.queryByText("windows desktop")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /выйти/ }),
  ).not.toBeInTheDocument();
  fireEvent.click(links[1]);
  fireEvent.click(screen.getByRole("link", { name: /устройства/ }));
  expect(
    await screen.findByRole("heading", { name: "устройства" }),
  ).toBeVisible();
  expect(links[1]).toHaveAttribute("aria-current", "page");
  fireEvent.click(screen.getByRole("link", { name: "← настройки" }));
  expect(screen.getByRole("heading", { name: "настройки" })).toBeVisible();
});

it("shows the backend version from /version without refetching on navigation", async () => {
  const api = mockApi();
  vi.mocked(api.getVersion).mockResolvedValue({
    application_name: "PrettyLisaVPN",
    application_version: "2.3.4",
    environment: "test",
  });
  renderRestored(api);
  expect(await screen.findByText("2.3.4")).toBeVisible();
  expect(await screen.findByText("0.1.0")).toBeVisible();
  expect(api.getVersion).toHaveBeenCalledWith(expect.any(AbortSignal));
  fireEvent.click(screen.getByRole("link", { name: "настройки" }));
  expect(screen.getByText("2.3.4")).toBeVisible();
  expect(api.getVersion).toHaveBeenCalledOnce();
});

it("keeps navigation usable when the backend version is unavailable", async () => {
  const api = mockApi();
  vi.mocked(api.getVersion).mockRejectedValue(new ApiError("NETWORK_ERROR"));
  renderRestored(api);
  expect(await screen.findByText("недоступна")).toBeVisible();
  fireEvent.click(screen.getByRole("link", { name: "о приложении" }));
  expect(screen.getByRole("heading", { name: "о приложении" })).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("does not submit logout twice while the request is pending", async () => {
  const api = mockApi();
  let finish!: (value: { status: "logged_out" }) => void;
  vi.mocked(api.logout).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const { session } = renderRestored(api);
  fireEvent.click(screen.getByRole("link", { name: "настройки" }));
  const button = screen.getByRole("button", { name: /выйти/ });
  fireEvent.click(button);
  expect(button).toBeDisabled();
  fireEvent.click(button);
  expect(api.logout).toHaveBeenCalledOnce();
  finish({ status: "logged_out" });
  await waitFor(() => expect(session.current()).toBeNull());
});
