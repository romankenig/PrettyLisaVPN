import { placeholderAdapters } from "../review/placeholders";
import { emptyTraffic, getDeviceTrafficSelection } from "../vpn/traffic";
import {
  act,
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

beforeEach(() => {
  localStorage.clear();
  getDeviceTrafficSelection().save(emptyTraffic());
});

describe("authenticated Home", () => {
  it("hides missing logos and keeps an ellipsis with spare room without changing rules", async () => {
    let width = 72;
    let resize = () => {};
    const bounds = HTMLElement.prototype.getBoundingClientRect;
    const measured = vi
      .spyOn(HTMLElement.prototype, "getBoundingClientRect")
      .mockImplementation(function (this: HTMLElement) {
        return this.classList.contains("traffic-selected")
          ? new DOMRect(0, 0, width, 20)
          : bounds.call(this);
      });
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(callback: () => void) {
          resize = callback;
        }
        observe() {}
        disconnect() {}
      },
    );
    const selection = {
      ...emptyTraffic(),
      mode: "include" as const,
      include: {
        services: [
          {
            id: "0bd811da-f080-4f25-887a-67bf534ac2c6",
            slug: "youtube",
            name: "YouTube",
            icon: "youtube",
            domains: ["youtube.com"],
          },
          {
            id: "4e2b8d7c-289f-4c57-8f26-aeb680408cda",
            slug: "instagram",
            name: "Instagram",
            icon: "instagram",
            domains: ["instagram.com"],
          },
          {
            id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            slug: "telegram",
            name: "Telegram",
            icon: "telegram",
            domains: ["t.me"],
          },
          {
            id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            slug: "yandex",
            name: "Yandex",
            icon: "yandex",
            domains: ["ya.ru"],
          },
        ],
        masks: ["one.example.com", "two.example.com"],
      },
    };
    getDeviceTrafficSelection().save(selection);
    const rendered = renderRestored();
    try {
      expect(await screen.findByRole("img", { name: "YouTube" })).toHaveStyle({
        color: "#FF0000",
      });
      expect(screen.getByRole("img", { name: "Instagram" })).toHaveStyle({
        color: "#FF0069",
      });
      expect(screen.getByText("…")).toHaveAttribute(
        "title",
        "Telegram, Yandex, one.example.com, two.example.com",
      );
      expect(screen.queryByRole("img", { name: "one.example.com" })).toBeNull();
      act(() => {
        width = 120;
        resize();
      });
      expect(screen.getByRole("img", { name: "Telegram" })).toBeVisible();
      expect(screen.queryByRole("img", { name: "Yandex" })).toBeNull();
      expect(screen.queryByRole("img", { name: "two.example.com" })).toBeNull();
      expect(screen.getByText("…")).toHaveAttribute(
        "title",
        "Yandex, one.example.com, two.example.com",
      );
      expect(getDeviceTrafficSelection().current()).toEqual(selection);
      act(() => {
        getDeviceTrafficSelection().save({
          ...selection,
          include: {
            services: selection.include.services.slice(0, 3),
            masks: [],
          },
        });
      });
      expect(screen.queryByText("…")).toBeNull();
      act(() => {
        width = 48;
        resize();
      });
      expect(screen.getByText("…")).toHaveAttribute(
        "title",
        "Instagram, Telegram",
      );
    } finally {
      rendered.unmount();
      measured.mockRestore();
      vi.unstubAllGlobals();
    }
  });
  it("uses name-only service switches and restores independent lists and Home icons", async () => {
    // jsdom has no native dialog; the CI native review also exercises showModal.
    const originalModal = Object.getOwnPropertyDescriptor(
      HTMLDialogElement.prototype,
      "showModal",
    );
    Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
      configurable: true,
      value: function (this: HTMLDialogElement) {
        this.open = true;
      },
    });
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          services: [
            {
              id: "0bd811da-f080-4f25-887a-67bf534ac2c6",
              slug: "youtube",
              name: "YouTube",
              icon: "youtube",
              domains: ["youtube.com", "*.youtube.com"],
            },
            {
              id: "4e2b8d7c-289f-4c57-8f26-aeb680408cda",
              slug: "instagram",
              name: "Instagram",
              icon: "instagram",
              domains: ["instagram.com"],
            },
          ],
        }),
        { status: 200 },
      ),
    );
    try {
      const rendered = renderRestored();
      expect(screen.queryByLabelText("локация VPN")).toBeNull();
      fireEvent.change(
        await screen.findByRole("combobox", { name: "режим трафика" }),
        { target: { value: "include" } },
      );
      await waitFor(() =>
        expect(getDeviceTrafficSelection().current().mode).toBe("include"),
      );
      expect(screen.getByLabelText("локация VPN")).toBeVisible();
      fireEvent.click(screen.getByRole("button", { name: /Выбрать сервисы/ }));
      const dialog = within(await screen.findByRole("dialog"));
      fireEvent.click(await dialog.findByRole("switch", { name: "YouTube" }));
      expect(dialog.queryByText("youtube.com, *.youtube.com")).toBeNull();
      fireEvent.change(dialog.getByLabelText("Маска сервиса"), {
        target: { value: "ifconfig.me" },
      });
      fireEvent.click(dialog.getByRole("button", { name: "Добавить" }));
      fireEvent.click(
        dialog.getByRole("button", { name: "кроме выбранных сайтов" }),
      );
      expect(dialog.getByRole("switch", { name: "YouTube" })).not.toBeChecked();
      expect(dialog.queryByText("ifconfig.me")).toBeNull();
      fireEvent.click(dialog.getByRole("switch", { name: "Instagram" }));
      fireEvent.click(dialog.getByRole("button", { name: "Сохранить" }));
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
      expect(screen.getByRole("img", { name: "YouTube" })).toBeVisible();
      expect(screen.queryByText("ifconfig.me")).toBeNull();
      expect(getDeviceTrafficSelection().current().include.masks).toEqual([
        "ifconfig.me",
      ]);
      expect(getDeviceTrafficSelection().current().exclude.masks).toEqual([]);
      rendered.unmount();
      renderRestored();
      fireEvent.change(
        screen.getByRole("combobox", { name: "режим трафика" }),
        { target: { value: "exclude" } },
      );
      await waitFor(() =>
        expect(screen.getByRole("img", { name: "Instagram" })).toBeVisible(),
      );
      expect(screen.queryByRole("img", { name: "YouTube" })).toBeNull();
      expect(screen.getByLabelText("локация VPN")).toBeVisible();
      fireEvent.change(
        screen.getByRole("combobox", { name: "режим трафика" }),
        { target: { value: "all" } },
      );
      await waitFor(() =>
        expect(screen.queryByLabelText("локация VPN")).toBeNull(),
      );
    } finally {
      if (originalModal)
        Object.defineProperty(
          HTMLDialogElement.prototype,
          "showModal",
          originalModal,
        );
      else Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
      fetch.mockRestore();
    }
  });
  it("keeps previous traffic rules when cleanup fails", async () => {
    const state = {
      phase: "CONNECTED",
      backend: "ACTIVE",
      tunnel: "UP",
      session: {
        sessionId: "cleanup-test",
        countryCode: "DE",
        expiresAt: null,
        remainingSeconds: null,
      },
    } as const;
    const vpn = {
      ...createTestVpnConnection(),
      current: () => state,
      disconnect: vi.fn(async () => {
        throw new Error("CLEANUP_FAILED");
      }),
      connect: vi.fn(),
    };
    renderRestored(mockApi(), createTestCredentialStorage(), vpn);
    fireEvent.change(
      await screen.findByRole("combobox", { name: "режим трафика" }),
      { target: { value: "include" } },
    );
    expect(
      await screen.findByText(
        "Не удалось сохранить правила. Повторите попытку.",
      ),
    ).toBeVisible();
    expect(getDeviceTrafficSelection().current().mode).toBe("all");
    expect(vpn.connect).not.toHaveBeenCalled();
  });
  it("stops the current attempt before applying new rules without reconnecting", async () => {
    let confirm!: () => void;
    const state = {
      phase: "CONNECTING",
      backend: "ACTIVE",
      tunnel: "DOWN",
    } as const;
    const vpn = {
      ...createTestVpnConnection(),
      current: () => state,
      disconnect: vi.fn(
        () =>
          new Promise<void>((resolve) => {
            confirm = resolve;
          }),
      ),
      connect: vi.fn(),
    };
    renderRestored(mockApi(), createTestCredentialStorage(), vpn);
    fireEvent.change(
      await screen.findByRole("combobox", { name: "режим трафика" }),
      { target: { value: "include" } },
    );
    expect(vpn.disconnect).toHaveBeenCalledWith("access-token");
    expect(getDeviceTrafficSelection().current().mode).toBe("all");
    expect(
      screen.getByRole("combobox", { name: "режим трафика" }),
    ).toBeDisabled();
    await act(async () => confirm());
    expect(getDeviceTrafficSelection().current().mode).toBe("include");
    expect(vpn.connect).not.toHaveBeenCalled();
  });
  it("shows concise attempt progress and clears it when checking the tunnel", async () => {
    let state: ReturnType<VpnConnectionManager["current"]> = {
      phase: "CONNECTING",
      backend: "ACTIVE",
      tunnel: "DOWN",
      attempt: { method: "OpenVPN", previousMethod: "WireGuard", retry: true },
    };
    const listeners = new Set<() => void>();
    renderRestored(mockApi(), createTestCredentialStorage(), {
      ...createTestVpnConnection(),
      current: () => state,
      subscribe: (listener) => {
        listeners.add(listener);
        return () => {
          listeners.delete(listener);
        };
      },
    });
    expect(
      await screen.findByText("WireGuard не подключился, пробую OpenVPN…"),
    ).toBeVisible();
    state = {
      phase: "VERIFYING_INTERNET",
      backend: "ACTIVE",
      tunnel: "UP",
      session: {
        sessionId: "session",
        countryCode: "DE",
        expiresAt: null,
        remainingSeconds: null,
      },
    };
    act(() => listeners.forEach((listener) => listener()));
    expect(
      screen.queryByText("WireGuard не подключился, пробую OpenVPN…"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("способ подключения"),
    ).not.toBeInTheDocument();
  });
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
    const modes = screen.getByRole("combobox", { name: "режим трафика" });
    expect(modes).toHaveValue("all");
    expect(modes).toBeEnabled();
    expect(
      within(modes)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Всё", "Выбранное", "Кроме выбранного"]);
    expect(modes.closest(".traffic-mode__heading")).toContainElement(
      screen.getByRole("heading", { name: "что защищаем" }),
    );
    expect(modes).toHaveAccessibleDescription(
      "все сайты и приложения через VPN",
    );
    expect(
      screen.queryByRole("button", { name: /Выбрать сервисы/ }),
    ).toBeNull();
    expect(screen.queryByLabelText("Выбранные сервисы")).toBeNull();
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
    expect(screen.getByRole("button", { name: "CONNECT" })).toBeEnabled();
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
    expect(screen.getByRole("button", { name: "Отменить" })).toBeEnabled();
    expect(vpnConnection.connect).toHaveBeenCalledOnce();

    finishConnection();
    expect(
      await screen.findByRole("heading", { name: "Connected" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("combobox", { name: /куда подключиться/ }),
    ).toBeDisabled();
    expect(
      screen.getByRole("timer", { name: "Остаток Free" }),
    ).toHaveTextContent("—");

    fireEvent.click(screen.getByRole("button", { name: "DISCONNECT" }));
    expect(
      await screen.findByRole("heading", { name: "Not connected" }),
    ).toBeInTheDocument();
    expect(vpnConnection.disconnect).toHaveBeenCalledOnce();
  });
});

it("executes placeholders in the actual Home and cancels from its button", async () => {
  const { createVpnConnectionManager } = await import("../vpn/connection");
  const connection = createVpnConnectionManager(placeholderAdapters());
  renderRestored(mockApi(), createTestCredentialStorage(), connection);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "CONNECT" })).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "CONNECT" }));
  expect(await screen.findByText("Пробую WireGuard…")).toBeVisible();
  expect(
    screen.getByText("Первое подключение может занять пару минут."),
  ).toBeVisible();
  expect(
    screen.queryByRole("heading", { name: "Connected" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Отменить" }));
  await waitFor(() => expect(connection.current().phase).toBe("DISCONNECTED"));
  expect(screen.queryByText("Пробую WireGuard…")).not.toBeInTheDocument();
  expect(
    screen.queryByText("Первое подключение может занять пару минут."),
  ).not.toBeInTheDocument();
  connection.dispose();
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
    application_version:
      "2.3.4-dev.40321791718+g177a078abd4f1e60fcba49f8acc849da622939f7",
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
  await waitFor(() => expect(api.logout).toHaveBeenCalledOnce());
  finish({ status: "logged_out" });
  await waitFor(() => expect(session.current()).toBeNull());
});
