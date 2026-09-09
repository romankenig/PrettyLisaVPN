import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient } from "../api/client";
import { createInMemoryAuthenticationSession } from "../auth/session";
import { loadConfig } from "../config/config";
import type { HttpTransport } from "../native/http";
import type { InstallationId } from "../native/installationId";
import { ApplicationProvider } from "../state/application";
import { App } from "../ui/App";

const health = { status: "ok" } as const;
const version = {
  application_name: "PrettyLisaVPN",
  application_version: "0.2.0-dev",
  environment: "development",
};
const verifiedSession = {
  token_type: "bearer" as const,
  access_token: "access-token",
  access_token_expires_in: 900,
  refresh_token: "refresh-token",
  refresh_token_expires_at: "2026-10-09T00:00:00Z",
  session_id: "123e4567-e89b-42d3-a456-426614174001",
  user: { id: "123e4567-e89b-42d3-a456-426614174002" },
  device: {
    id: "123e4567-e89b-42d3-a456-426614174003",
    installation_id: "123e4567-e89b-42d3-a456-426614174000",
    status: "ACTIVE" as const,
  },
  subscription: { plan: "FREE" as const, status: "ACTIVE" as const },
};

function jsonResponse(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function renderApplication(transport: HttpTransport) {
  const config = loadConfig({});
  return render(
    <ApplicationProvider
      value={{
        config,
        api: createApiClient(
          config.backendBaseUrl,
          transport,
          config.backendTimeoutMs,
        ),
        desktop: { getVersion: async () => "0.1.0" },
        installationId: {
          getInstallationId: async () =>
            "123e4567-e89b-42d3-a456-426614174000" as InstallationId,
        },
        session: createInMemoryAuthenticationSession(),
      }}
    >
      <MemoryRouter>
        <App />
      </MemoryRouter>
    </ApplicationProvider>,
  );
}

afterEach(() => {
  vi.useRealTimers();
});

describe("configuration", () => {
  it("loads development defaults", () => {
    expect(loadConfig({})).toMatchObject({
      environment: "development",
      backendBaseUrl: "https://api.prettylisavpn.com",
      backendTimeoutMs: 5000,
      backendHealthIntervalMs: 15000,
    });
  });

  it("loads and normalizes configured backend settings", () => {
    expect(
      loadConfig({
        VITE_BACKEND_BASE_URL: "https://api.example.invalid/api/",
        VITE_BACKEND_TIMEOUT_MS: "3000",
        VITE_BACKEND_HEALTH_INTERVAL_MS: "10000",
      }),
    ).toMatchObject({
      backendBaseUrl: "https://api.example.invalid/api",
      backendTimeoutMs: 3000,
      backendHealthIntervalMs: 10000,
    });
  });

  it.each([
    "file:///tmp",
    "https://user:secret@example.invalid",
    "bad",
    "https://example.invalid?key=x",
  ])("rejects invalid URL %s", (url) => {
    expect(() => loadConfig({ VITE_BACKEND_BASE_URL: url })).toThrow(
      "INVALID_BACKEND_BASE_URL",
    );
  });

  it("requires production HTTPS and valid timing settings", () => {
    expect(() =>
      loadConfig({
        VITE_APP_ENVIRONMENT: "production",
        VITE_BACKEND_BASE_URL: "http://127.0.0.1:8000",
      }),
    ).toThrow("BACKEND_HTTPS_REQUIRED");
    expect(() => loadConfig({ VITE_BACKEND_TIMEOUT_MS: 999 })).toThrow(
      "INVALID_BACKEND_TIMEOUT",
    );
    expect(() => loadConfig({ VITE_BACKEND_HEALTH_INTERVAL_MS: 4999 })).toThrow(
      "INVALID_BACKEND_HEALTH_INTERVAL",
    );
  });
});

describe("typed API client", () => {
  it("calls health and version through the configured transport", async () => {
    const transport = vi.fn<HttpTransport>((input) =>
      Promise.resolve(
        jsonResponse(String(input).endsWith("/health") ? health : version),
      ),
    );
    const api = createApiClient("https://api.example.invalid", transport, 5000);

    await expect(api.getHealth()).resolves.toEqual(health);
    await expect(api.getVersion()).resolves.toEqual(version);
    expect(transport).toHaveBeenNthCalledWith(
      1,
      "https://api.example.invalid/health",
      expect.objectContaining({
        method: "GET",
        credentials: "omit",
        signal: expect.any(AbortSignal),
      }),
    );
    expect(transport).toHaveBeenNthCalledWith(
      2,
      "https://api.example.invalid/version",
      expect.any(Object),
    );
  });

  it("maps transport, HTTP, and schema failures to safe errors", async () => {
    const transport = vi.fn<HttpTransport>();
    const api = createApiClient("https://api.example.invalid", transport, 5000);

    transport.mockRejectedValueOnce(new Error("sensitive detail"));
    await expect(api.getHealth()).rejects.toEqual(
      new ApiError("NETWORK_ERROR"),
    );
    transport.mockResolvedValueOnce(jsonResponse({}, 503));
    await expect(api.getHealth()).rejects.toEqual(new ApiError("SERVER_ERROR"));
    transport.mockResolvedValueOnce(jsonResponse({ status: "wrong" }));
    await expect(api.getHealth()).rejects.toEqual(
      new ApiError("INVALID_RESPONSE"),
    );
  });

  it("requests an OTP with a JSON email body", async () => {
    const transport = vi
      .fn<HttpTransport>()
      .mockResolvedValue(jsonResponse({ status: "accepted" }, 202));
    const api = createApiClient("https://api.example.invalid", transport, 5000);

    await expect(api.requestOtp("user@example.com")).resolves.toEqual({
      status: "accepted",
    });
    expect(transport).toHaveBeenCalledWith(
      "https://api.example.invalid/auth/request-otp",
      expect.objectContaining({
        method: "POST",
        credentials: "omit",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: "user@example.com" }),
        signal: expect.any(AbortSignal),
      }),
    );
  });

  it("maps OTP rate limits and provider failures to typed errors", async () => {
    const transport = vi.fn<HttpTransport>();
    const api = createApiClient("https://api.example.invalid", transport, 5000);

    transport.mockResolvedValueOnce(
      jsonResponse({ error: { code: "otp_rate_limited" } }, 429),
    );
    await expect(api.requestOtp("user@example.com")).rejects.toEqual(
      new ApiError("RATE_LIMITED"),
    );

    transport.mockResolvedValueOnce(
      jsonResponse({ error: { code: "email_service_unavailable" } }, 503),
    );
    await expect(api.requestOtp("user@example.com")).rejects.toEqual(
      new ApiError("SERVER_ERROR"),
    );
  });

  it("verifies an OTP using the backend login contract", async () => {
    const transport = vi
      .fn<HttpTransport>()
      .mockResolvedValue(jsonResponse(verifiedSession));
    const api = createApiClient("https://api.example.invalid", transport, 5000);
    const body = {
      email: "user@example.com",
      code: "012345",
      installation_id: verifiedSession.device.installation_id,
      platform: "WINDOWS" as const,
      device_name: "Windows device",
    };

    await expect(api.verifyOtp(body)).resolves.toEqual(verifiedSession);
    expect(transport).toHaveBeenCalledWith(
      "https://api.example.invalid/auth/verify-otp",
      expect.objectContaining({
        method: "POST",
        credentials: "omit",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
        signal: expect.any(AbortSignal),
      }),
    );
  });

  it.each([
    [401, "otp_invalid_or_expired", "OTP_INVALID"],
    [409, "device_limit_reached", "DEVICE_LIMIT"],
    [403, "user_blocked", "AUTH_FORBIDDEN"],
    [429, "otp_rate_limited", "RATE_LIMITED"],
  ] as const)(
    "maps verify status %s and %s to %s",
    async (status, backendCode, clientCode) => {
      const transport = vi
        .fn<HttpTransport>()
        .mockResolvedValue(
          jsonResponse({ error: { code: backendCode } }, status),
        );
      const api = createApiClient(
        "https://api.example.invalid",
        transport,
        5000,
      );

      await expect(
        api.verifyOtp({
          email: "user@example.com",
          code: "012345",
          installation_id: verifiedSession.device.installation_id,
          platform: "WINDOWS",
          device_name: "Windows device",
        }),
      ).rejects.toEqual(new ApiError(clientCode));
    },
  );

  it("rejects a malformed verification response", async () => {
    const transport = vi.fn<HttpTransport>().mockResolvedValue(
      jsonResponse({
        ...verifiedSession,
        refresh_token: "",
      }),
    );
    const api = createApiClient("https://api.example.invalid", transport, 5000);

    await expect(
      api.verifyOtp({
        email: "user@example.com",
        code: "012345",
        installation_id: verifiedSession.device.installation_id,
        platform: "WINDOWS",
        device_name: "Windows device",
      }),
    ).rejects.toEqual(new ApiError("INVALID_RESPONSE"));
  });

  it("bounds a stalled request with a timeout", async () => {
    vi.useFakeTimers();
    const transport = vi.fn<HttpTransport>(
      (_input, init) =>
        new Promise((_resolve, reject) => {
          const abort = () => reject(new DOMException("aborted", "AbortError"));
          if (init?.signal?.aborted) abort();
          else init?.signal?.addEventListener("abort", abort, { once: true });
        }),
    );
    const result = createApiClient(
      "https://api.example.invalid",
      transport,
      1000,
    ).getHealth();
    const assertion = expect(result).rejects.toEqual(new ApiError("TIMEOUT"));

    await vi.advanceTimersByTimeAsync(1000);
    await assertion;
  });
});

describe("startup backend state", () => {
  it("shows online with version metadata", async () => {
    const transport: HttpTransport = (input) =>
      Promise.resolve(
        jsonResponse(String(input).endsWith("/health") ? health : version),
      );
    renderApplication(transport);

    expect(screen.getByText("backend: checking")).toBeInTheDocument();
    expect(await screen.findByText("backend: online")).toBeInTheDocument();
    expect(screen.getByText("0.2.0-dev")).toBeInTheDocument();
    expect(screen.getAllByText("development").length).toBeGreaterThan(0);
  });

  it("detects an outage and retry restores online state", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let online = true;
    const transport: HttpTransport = (input) => {
      if (!online) return Promise.reject(new Error("offline"));
      return Promise.resolve(
        jsonResponse(String(input).endsWith("/health") ? health : version),
      );
    };
    renderApplication(transport);

    expect(await screen.findByText("backend: online")).toBeInTheDocument();
    online = false;
    await vi.advanceTimersByTimeAsync(15000);
    expect(await screen.findByText("backend: offline")).toBeInTheDocument();

    online = true;
    fireEvent.click(screen.getByRole("button", { name: "retry" }));
    expect(screen.getByText("backend: checking")).toBeInTheDocument();
    expect(await screen.findByText("backend: online")).toBeInTheDocument();
    expect(screen.getByText("0.2.0-dev")).toBeInTheDocument();
  });
});

it("keeps native functionality behind the desktop adapter", async () => {
  const transport: HttpTransport = (input) =>
    Promise.resolve(
      jsonResponse(String(input).endsWith("/health") ? health : version),
    );
  renderApplication(transport);

  fireEvent.click(screen.getByRole("link", { name: "о приложении" }));
  await waitFor(() => expect(screen.getByText("0.1.0")).toBeInTheDocument());
});
