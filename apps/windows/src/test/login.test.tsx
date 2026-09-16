import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  type ApiClient,
  type RequestOtpResponse,
} from "../api/client";
import { loadConfig } from "../config/config";
import type { InstallationId } from "../native/installationId";
import { ApplicationProvider } from "../state/application";
import { App } from "../ui/App";
import {
  createTestAuthenticationSession,
  createTestSessionRestoration,
  createTestVpnConnection,
} from "./fakes";

type RequestOtp = ApiClient["requestOtp"];

function renderLogin(requestOtp: RequestOtp) {
  const api: ApiClient = {
    getHealth: vi.fn(),
    getVersion: vi.fn(),
    requestOtp,
    verifyOtp: vi.fn(),
    refresh: vi.fn(),
    me: vi.fn(),
    logout: vi.fn(),
    listDevices: vi.fn(),
    revokeDevice: vi.fn(),
    listVpnCountries: vi.fn().mockResolvedValue({
      autopilot: { quality: 90, available: true },
      countries: [],
    }),
    createVpnSession: vi.fn(),
    getCurrentVpnSession: vi.fn().mockResolvedValue({ session: null }),
    disconnectVpnSession: vi.fn(),
  };
  return render(
    <ApplicationProvider
      value={{
        config: loadConfig({}),
        api,
        desktop: { getVersion: async () => "0.1.0" },
        installationId: {
          getInstallationId: async () =>
            "123e4567-e89b-42d3-a456-426614174000" as InstallationId,
        },
        session: createTestAuthenticationSession(),
        sessionRestoration: createTestSessionRestoration(),
        vpnConnection: createTestVpnConnection(),
      }}
    >
      <MemoryRouter initialEntries={["/login"]}>
        <App />
      </MemoryRouter>
    </ApplicationProvider>,
  );
}

function enterEmail(value: string) {
  fireEvent.change(screen.getByRole("textbox", { name: "Email" }), {
    target: { value },
  });
  fireEvent.click(screen.getByRole("button", { name: "продолжить" }));
}

beforeEach(() => localStorage.clear());

describe("email login", () => {
  it("validates email before calling the API", () => {
    const requestOtp = vi.fn<RequestOtp>();
    renderLogin(requestOtp);

    enterEmail("not-an-email");

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Введите корректный email.",
    );
    expect(requestOtp).not.toHaveBeenCalled();
  });

  it("normalizes email and navigates to the generic OTP screen", async () => {
    const requestOtp = vi
      .fn<RequestOtp>()
      .mockResolvedValue({ status: "accepted" });
    renderLogin(requestOtp);

    enterEmail("  User@Example.COM  ");

    expect(
      await screen.findByRole("heading", { name: "введите код" }),
    ).toBeInTheDocument();
    expect(requestOtp).toHaveBeenCalledWith(
      "user@example.com",
      expect.any(AbortSignal),
    );
    expect(screen.getByText("user@example.com")).toBeInTheDocument();
    expect(localStorage).toHaveLength(0);
  });

  it("disables submission while the request is pending", async () => {
    let resolveRequest!: (value: RequestOtpResponse) => void;
    const requestOtp = vi.fn<RequestOtp>(
      () =>
        new Promise((resolve) => {
          resolveRequest = resolve;
        }),
    );
    renderLogin(requestOtp);

    enterEmail("user@example.com");

    expect(screen.getByRole("button", { name: "отправляем…" })).toBeDisabled();
    resolveRequest({ status: "accepted" });
    await screen.findByRole("heading", { name: "введите код" });
  });

  it.each([
    ["RATE_LIMITED", "Слишком много запросов. Попробуйте позже."],
    [
      "NETWORK_ERROR",
      "Не удалось подключиться. Проверьте сеть и попробуйте снова.",
    ],
    [
      "TIMEOUT",
      "Сервис входа отвечает слишком долго. Попробуйте ещё раз позже.",
    ],
    ["SERVER_ERROR", "Сервис входа временно недоступен. Попробуйте позже."],
  ] as const)("shows the %s state", async (code, message) => {
    const requestOtp = vi
      .fn<RequestOtp>()
      .mockRejectedValue(new ApiError(code));
    renderLogin(requestOtp);

    enterEmail("user@example.com");

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("button", { name: "продолжить" })).toBeEnabled();
  });

  it("redirects direct OTP navigation without transient email state", async () => {
    const api: ApiClient = {
      getHealth: vi.fn(),
      getVersion: vi.fn(),
      requestOtp: vi.fn(),
      verifyOtp: vi.fn(),
      refresh: vi.fn(),
      me: vi.fn(),
      logout: vi.fn(),
      listDevices: vi.fn(),
      revokeDevice: vi.fn(),
      listVpnCountries: vi.fn().mockResolvedValue({
        autopilot: { quality: 90, available: true },
        countries: [],
      }),
      createVpnSession: vi.fn(),
      getCurrentVpnSession: vi.fn().mockResolvedValue({ session: null }),
      disconnectVpnSession: vi.fn(),
    };
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
          session: createTestAuthenticationSession(),
          sessionRestoration: createTestSessionRestoration(),
          vpnConnection: createTestVpnConnection(),
        }}
      >
        <MemoryRouter initialEntries={["/auth/verify-otp"]}>
          <App />
        </MemoryRouter>
      </ApplicationProvider>,
    );

    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "войти по email" }),
      ).toBeInTheDocument(),
    );
  });
});
