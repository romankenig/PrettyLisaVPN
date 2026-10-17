import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  createApiClient,
  type ApiClient,
  type VerifyOtpResponse,
} from "../api/client";
import {
  createAuthenticationSession,
  type AuthenticationSession,
} from "../auth/session";
import { loadConfig } from "../config/config";
import type { HttpTransport } from "../native/http";
import type {
  InstallationId,
  InstallationIdProvider,
} from "../native/installationId";
import { ApplicationProvider } from "../state/application";
import { App } from "../ui/App";
import {
  createTestCredentialStorage,
  createTestSessionRestoration,
  createTestVpnConnection,
} from "./fakes";

const email = "user@example.com";
const installationId = "123e4567-e89b-42d3-a456-426614174000" as InstallationId;
const verifiedSession: VerifyOtpResponse = {
  token_type: "bearer",
  access_token: "access-token",
  access_token_expires_in: 900,
  refresh_token: "refresh-token",
  refresh_token_expires_at: "2026-10-09T00:00:00Z",
  session_id: "123e4567-e89b-42d3-a456-426614174001",
  user: { id: "123e4567-e89b-42d3-a456-426614174002" },
  device: {
    id: "123e4567-e89b-42d3-a456-426614174003",
    installation_id: installationId,
    status: "ACTIVE",
  },
  subscription: { plan: "FREE", status: "ACTIVE" },
};

interface RenderOptions {
  readonly api?: ApiClient;
  readonly session?: AuthenticationSession;
  readonly installationIdProvider?: InstallationIdProvider;
}

function mockApi(): ApiClient {
  return {
    getHealth: vi.fn(),
    getVersion: vi.fn(),
    requestOtp: vi.fn().mockResolvedValue({ status: "accepted" }),
    verifyOtp: vi.fn().mockResolvedValue(verifiedSession),
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
}

function renderVerification(options: RenderOptions = {}) {
  const api = options.api ?? mockApi();
  const session =
    options.session ??
    createAuthenticationSession(createTestCredentialStorage());
  const installationIdProvider = options.installationIdProvider ?? {
    getInstallationId: async () => installationId,
  };
  const result = render(
    <ApplicationProvider
      value={{
        config: loadConfig({}),
        api,
        desktop: { getVersion: async () => "0.1.0" },
        installationId: installationIdProvider,
        session,
        sessionRestoration: createTestSessionRestoration(),
        vpnConnection: createTestVpnConnection(),
      }}
    >
      <MemoryRouter
        initialEntries={[{ pathname: "/auth/verify-otp", state: { email } }]}
      >
        <App />
      </MemoryRouter>
    </ApplicationProvider>,
  );
  return { ...result, api, session };
}

function codeInput() {
  return screen.getByRole("textbox", { name: "Шестизначный код" });
}

function enterCode(value: string) {
  fireEvent.change(codeInput(), { target: { value } });
}

async function finishCooldown() {
  for (let second = 0; second < 60; second += 1) {
    await act(() => vi.advanceTimersByTimeAsync(1000));
  }
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.useRealTimers());

describe("OTP verification component", () => {
  it("shows the email and exposes numeric one-time-code keyboard hints", () => {
    renderVerification();

    expect(screen.getByText(email)).toBeInTheDocument();
    expect(codeInput()).toHaveAttribute("inputmode", "numeric");
    expect(codeInput()).toHaveAttribute("autocomplete", "one-time-code");
    expect(codeInput()).toHaveAttribute("maxlength", "6");
  });

  it("accepts pasted digits, preserves a leading zero, and submits with the form", async () => {
    const api = mockApi();
    renderVerification({ api });

    enterCode("01 23a45");
    expect(codeInput()).toHaveValue("012345");
    fireEvent.submit(codeInput().closest("form")!);

    expect(
      await screen.findByRole("heading", { name: "вход выполнен" }),
    ).toBeInTheDocument();
    expect(api.verifyOtp).toHaveBeenCalledOnce();
  });

  it("validates six digits before reading installation identity", () => {
    const api = mockApi();
    const installationIdProvider = { getInstallationId: vi.fn() };
    renderVerification({ api, installationIdProvider });

    enterCode("12345");
    fireEvent.click(screen.getByRole("button", { name: "подтвердить" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Введите шестизначный код.",
    );
    expect(installationIdProvider.getInstallationId).not.toHaveBeenCalled();
    expect(api.verifyOtp).not.toHaveBeenCalled();
  });

  it("prevents duplicate submissions while verification is pending", async () => {
    let resolveVerification!: (value: VerifyOtpResponse) => void;
    const api = mockApi();
    vi.mocked(api.verifyOtp).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveVerification = resolve;
        }),
    );
    renderVerification({ api });
    enterCode("123456");
    const form = codeInput().closest("form")!;

    fireEvent.submit(form);
    fireEvent.submit(form);

    expect(screen.getByRole("button", { name: "проверяем…" })).toBeDisabled();
    await waitFor(() => expect(api.verifyOtp).toHaveBeenCalledOnce());
    await act(async () => {
      resolveVerification(verifiedSession);
    });
    await screen.findByRole("heading", { name: "вход выполнен" });
  });

  it.each(["invalid", "expired", "replayed"])(
    "shows one safe message for an %s OTP",
    async () => {
      const api = mockApi();
      vi.mocked(api.verifyOtp).mockRejectedValue(new ApiError("OTP_INVALID"));
      renderVerification({ api });

      enterCode("123456");
      fireEvent.click(screen.getByRole("button", { name: "подтвердить" }));

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Код неверен, истёк или уже использован.",
      );
      expect(codeInput()).toHaveValue("");
    },
  );

  it.each([
    ["RATE_LIMITED", "Слишком много попыток. Попробуйте позже."],
    [
      "NETWORK_ERROR",
      "Не удалось подключиться. Проверьте сеть и попробуйте снова.",
    ],
    ["TIMEOUT", "Не удалось подключиться. Проверьте сеть и попробуйте снова."],
    ["SERVER_ERROR", "Сервис входа временно недоступен. Попробуйте позже."],
  ] as const)("shows the %s verification state", async (errorCode, message) => {
    const api = mockApi();
    vi.mocked(api.verifyOtp).mockRejectedValue(new ApiError(errorCode));
    renderVerification({ api });

    enterCode("123456");
    fireEvent.click(screen.getByRole("button", { name: "подтвердить" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("button", { name: "подтвердить" })).toBeEnabled();
  });

  it("enforces resend cooldown and starts a new cooldown after success", async () => {
    vi.useFakeTimers();
    const api = mockApi();
    renderVerification({ api });

    expect(
      screen.getByRole("button", { name: "отправить повторно через 60 с" }),
    ).toBeDisabled();
    await finishCooldown();
    fireEvent.click(
      screen.getByRole("button", { name: "отправить код повторно" }),
    );

    await act(async () => undefined);
    expect(api.requestOtp).toHaveBeenCalledWith(email, expect.any(AbortSignal));
    expect(screen.getByRole("status")).toHaveTextContent("Новый код запрошен.");
    expect(
      screen.getByRole("button", { name: "отправить повторно через 60 с" }),
    ).toBeDisabled();
  });

  it("shows rate-limit state for resend and restarts cooldown", async () => {
    vi.useFakeTimers();
    const api = mockApi();
    vi.mocked(api.requestOtp).mockRejectedValue(new ApiError("RATE_LIMITED"));
    renderVerification({ api });
    await finishCooldown();

    fireEvent.click(
      screen.getByRole("button", { name: "отправить код повторно" }),
    );

    await act(async () => undefined);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Новый код пока нельзя запросить. Попробуйте позже.",
    );
    expect(
      screen.getByRole("button", { name: "отправить повторно через 60 с" }),
    ).toBeDisabled();
  });
});

describe("OTP login integration", () => {
  it("sends device context and hands credentials to the in-memory session layer", async () => {
    const transport = vi.fn<HttpTransport>(
      async (input) =>
        new Response(
          JSON.stringify(
            String(input).endsWith("/version")
              ? {
                  application_name: "PrettyLisaVPN",
                  application_version: "0.2.0",
                  environment: "test",
                }
              : verifiedSession,
          ),
          {
            status: 200,
            headers: { "content-type": "application/json" },
          },
        ),
    );
    const api = createApiClient("https://api.example.invalid", transport, 5000);
    const credentialStorage = createTestCredentialStorage();
    const session = createAuthenticationSession(credentialStorage);
    renderVerification({ api, session });

    enterCode("012345");
    fireEvent.click(screen.getByRole("button", { name: "подтвердить" }));

    expect(
      await screen.findByRole("heading", { name: "вход выполнен" }),
    ).toBeInTheDocument();
    const request = JSON.parse(
      String(
        vi
          .mocked(transport)
          .mock.calls.find(([input]) =>
            String(input).endsWith("/auth/verify-otp"),
          )?.[1]?.body,
      ),
    );
    expect(request).toEqual({
      email,
      code: "012345",
      installation_id: installationId,
      platform: "WINDOWS",
      device_name: "Windows device",
    });
    expect(session.current()).toEqual({
      accessToken: "access-token",
      accessTokenExpiresIn: 900,
      sessionId: "123e4567-e89b-42d3-a456-426614174001",
      userId: "123e4567-e89b-42d3-a456-426614174002",
      deviceId: "123e4567-e89b-42d3-a456-426614174003",
      plan: "FREE",
      profile: null,
    });
    await expect(credentialStorage.retrieve()).resolves.toEqual({
      sessionId: "123e4567-e89b-42d3-a456-426614174001",
      refreshToken: "refresh-token",
      expiresAt: "2026-10-09T00:00:00Z",
    });
    expect(localStorage).toHaveLength(0);
    expect(sessionStorage).toHaveLength(0);
  });
});
