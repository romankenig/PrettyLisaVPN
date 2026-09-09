import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient } from "../api/client";
import { loadConfig } from "../config/config";
import type { HttpTransport } from "../native/http";
import type { InstallationId } from "../native/installationId";
import { ApplicationProvider } from "../state/application";
import { App } from "../ui/App";
import {
  createTestAuthenticationSession,
  createTestSessionRestoration,
} from "./fakes";

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
        session: createTestAuthenticationSession(),
        sessionRestoration: createTestSessionRestoration(),
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
      backendTimeoutMs: 15000,
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

  it("rotates refresh credentials using the backend contract", async () => {
    const response = {
      token_type: "bearer" as const,
      access_token: "new-access-token",
      access_token_expires_in: 900,
      refresh_token: "new-refresh-token",
      refresh_token_expires_at: "2026-11-09T00:00:00Z",
      session_id: verifiedSession.session_id,
    };
    const transport = vi
      .fn<HttpTransport>()
      .mockResolvedValue(jsonResponse(response));
    const api = createApiClient("https://api.example.invalid", transport, 5000);
    const body = {
      session_id: verifiedSession.session_id,
      refresh_token: "old-refresh-token",
    };

    await expect(api.refresh(body)).resolves.toEqual(response);
    expect(transport).toHaveBeenCalledWith(
      "https://api.example.invalid/auth/refresh",
      expect.objectContaining({
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    );
  });

  it("loads /me with the in-memory access token", async () => {
    const response = {
      id: verifiedSession.user.id,
      email: "user@example.com",
      plan: "PREMIUM" as const,
      active_device_count: 2,
    };
    const transport = vi
      .fn<HttpTransport>()
      .mockResolvedValue(jsonResponse(response));
    const api = createApiClient("https://api.example.invalid", transport, 5000);

    await expect(api.me("access-token")).resolves.toEqual(response);
    expect(transport).toHaveBeenCalledWith(
      "https://api.example.invalid/me",
      expect.objectContaining({
        method: "GET",
        headers: { authorization: "Bearer access-token" },
      }),
    );
  });

  it("logs out with the in-memory access token", async () => {
    const transport = vi
      .fn<HttpTransport>()
      .mockResolvedValue(jsonResponse({ status: "logged_out" }));
    const api = createApiClient("https://api.example.invalid", transport, 5000);

    await expect(api.logout("access-token")).resolves.toEqual({
      status: "logged_out",
    });
    expect(transport).toHaveBeenCalledWith(
      "https://api.example.invalid/auth/logout",
      expect.objectContaining({
        method: "POST",
        headers: { authorization: "Bearer access-token" },
      }),
    );
  });

  it("loads and validates devices with the in-memory access token", async () => {
    const response = [
      {
        id: "123e4567-e89b-42d3-a456-426614174010",
        installation_id: "123e4567-e89b-42d3-a456-426614174011",
        device_name: "Windows device",
        platform: "WINDOWS",
        status: "ACTIVE",
        created_at: "2026-09-01T10:00:00Z",
        updated_at: "2026-09-01T10:00:00Z",
        revoked_at: null,
        is_current: true,
      },
    ];
    const transport = vi
      .fn<HttpTransport>()
      .mockResolvedValue(jsonResponse(response));
    const api = createApiClient("https://api.example.invalid", transport, 5000);

    await expect(api.listDevices("access-token")).resolves.toEqual(response);
    expect(transport).toHaveBeenCalledWith(
      "https://api.example.invalid/devices",
      expect.objectContaining({
        method: "GET",
        headers: { authorization: "Bearer access-token" },
      }),
    );
  });

  it("revokes a device through the typed API contract", async () => {
    const device = {
      id: "123e4567-e89b-42d3-a456-426614174010",
      installation_id: "123e4567-e89b-42d3-a456-426614174011",
      device_name: "Android device",
      platform: "ANDROID",
      status: "REVOKED",
      created_at: "2026-09-01T10:00:00Z",
      updated_at: "2026-09-02T10:00:00Z",
      revoked_at: "2026-09-02T10:00:00Z",
      is_current: false,
    };
    const transport = vi
      .fn<HttpTransport>()
      .mockResolvedValue(jsonResponse({ status: "revoked", device }));
    const api = createApiClient("https://api.example.invalid", transport, 5000);

    await expect(api.revokeDevice("access-token", device.id)).resolves.toEqual({
      status: "revoked",
      device,
    });
    expect(transport).toHaveBeenCalledWith(
      `https://api.example.invalid/devices/${device.id}`,
      expect.objectContaining({
        method: "DELETE",
        headers: { authorization: "Bearer access-token" },
      }),
    );
  });

  it("maps device ownership and authentication errors", async () => {
    const transport = vi
      .fn<HttpTransport>()
      .mockResolvedValueOnce(
        jsonResponse({ error: { code: "device_not_found" } }, 404),
      )
      .mockResolvedValueOnce(
        jsonResponse({ error: { code: "authentication_required" } }, 401),
      );
    const api = createApiClient("https://api.example.invalid", transport, 5000);

    await expect(
      api.revokeDevice("access-token", "123e4567-e89b-42d3-a456-426614174010"),
    ).rejects.toEqual(new ApiError("DEVICE_NOT_FOUND"));
    await expect(api.listDevices("access-token")).rejects.toEqual(
      new ApiError("AUTH_INVALID"),
    );
  });

  it.each([
    [401, "invalid_refresh_token"],
    [403, "device_revoked"],
  ] as const)("maps invalid session status %s and %s", async (status, code) => {
    const transport = vi
      .fn<HttpTransport>()
      .mockResolvedValue(jsonResponse({ error: { code } }, status));
    const api = createApiClient("https://api.example.invalid", transport, 5000);

    await expect(
      api.refresh({
        session_id: verifiedSession.session_id,
        refresh_token: "old-refresh-token",
      }),
    ).rejects.toEqual(new ApiError("AUTH_INVALID"));
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

it("keeps native functionality behind the desktop adapter", async () => {
  const transport: HttpTransport = (input) =>
    Promise.resolve(
      jsonResponse(String(input).endsWith("/health") ? health : version),
    );
  renderApplication(transport);

  fireEvent.click(screen.getByRole("link", { name: "о приложении" }));
  await waitFor(() => expect(screen.getByText("0.1.0")).toBeInTheDocument());
});
