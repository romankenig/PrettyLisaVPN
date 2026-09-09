import type { HttpTransport } from "../native/http";

export interface BackendHealth {
  readonly status: "ok";
}

export interface BackendVersion {
  readonly application_name: string;
  readonly application_version: string;
  readonly environment: string;
}

export interface RequestOtpResponse {
  readonly status: "accepted";
}

export interface VerifyOtpRequest {
  readonly email: string;
  readonly code: string;
  readonly installation_id: string;
  readonly platform: "WINDOWS";
  readonly device_name: string;
}

export interface VerifyOtpResponse {
  readonly token_type: "bearer";
  readonly access_token: string;
  readonly access_token_expires_in: number;
  readonly refresh_token: string;
  readonly refresh_token_expires_at: string;
  readonly session_id: string;
  readonly user: { readonly id: string };
  readonly device: {
    readonly id: string;
    readonly installation_id: string;
    readonly status: "ACTIVE" | "REVOKED";
  };
  readonly subscription: {
    readonly plan: "FREE" | "PREMIUM";
    readonly status: "ACTIVE" | "CANCELED" | "EXPIRED";
  };
}

export interface RefreshRequest {
  readonly session_id: string;
  readonly refresh_token: string;
}

export interface RefreshResponse {
  readonly token_type: "bearer";
  readonly access_token: string;
  readonly access_token_expires_in: number;
  readonly refresh_token: string;
  readonly refresh_token_expires_at: string;
  readonly session_id: string;
}

export interface MeResponse {
  readonly id: string;
  readonly email: string;
  readonly plan: "FREE" | "PREMIUM";
  readonly active_device_count: number;
}

export interface LogoutResponse {
  readonly status: "logged_out";
}

export type ApiErrorCode =
  | "NETWORK_ERROR"
  | "TIMEOUT"
  | "RATE_LIMITED"
  | "OTP_INVALID"
  | "DEVICE_LIMIT"
  | "AUTH_FORBIDDEN"
  | "AUTH_INVALID"
  | "SERVER_ERROR"
  | "HTTP_ERROR"
  | "INVALID_RESPONSE";

export class ApiError extends Error {
  constructor(readonly code: ApiErrorCode) {
    super(code);
    this.name = "ApiError";
  }
}

export interface ApiClient {
  getHealth(signal?: AbortSignal): Promise<BackendHealth>;
  getVersion(signal?: AbortSignal): Promise<BackendVersion>;
  requestOtp(email: string, signal?: AbortSignal): Promise<RequestOtpResponse>;
  verifyOtp(
    body: VerifyOtpRequest,
    signal?: AbortSignal,
  ): Promise<VerifyOtpResponse>;
  refresh(body: RefreshRequest, signal?: AbortSignal): Promise<RefreshResponse>;
  me(accessToken: string, signal?: AbortSignal): Promise<MeResponse>;
  logout(accessToken: string, signal?: AbortSignal): Promise<LogoutResponse>;
}

export function createApiClient(
  baseUrl: string,
  transport: HttpTransport,
  timeoutMs: number,
): ApiClient {
  async function requestJson(
    path: string,
    init: Pick<RequestInit, "method" | "headers" | "body">,
    signal?: AbortSignal,
  ): Promise<unknown> {
    const controller = new AbortController();
    let timedOut = false;
    const abortFromCaller = () => controller.abort();

    if (signal?.aborted) {
      controller.abort();
    } else {
      signal?.addEventListener("abort", abortFromCaller, { once: true });
    }

    let rejectOnAbort: () => void = () => undefined;
    const aborted = new Promise<never>((_, reject) => {
      rejectOnAbort = () =>
        reject(new ApiError(timedOut ? "TIMEOUT" : "NETWORK_ERROR"));
      if (controller.signal.aborted) {
        rejectOnAbort();
      } else {
        controller.signal.addEventListener("abort", rejectOnAbort, {
          once: true,
        });
      }
    });

    const timer = globalThis.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);

    const request = (async () => {
      let response: Response;
      try {
        response = await transport(`${baseUrl}${path}`, {
          ...init,
          signal: controller.signal,
          credentials: "omit",
        });
      } catch {
        throw new ApiError(timedOut ? "TIMEOUT" : "NETWORK_ERROR");
      }

      if (!response.ok) {
        const errorCode = await readErrorCode(response);
        if (response.status === 429 && errorCode === "otp_rate_limited") {
          throw new ApiError("RATE_LIMITED");
        }
        if (response.status === 401 && errorCode === "otp_invalid_or_expired") {
          throw new ApiError("OTP_INVALID");
        }
        if (response.status === 409 && errorCode === "device_limit_reached") {
          throw new ApiError("DEVICE_LIMIT");
        }
        if (response.status === 403 && errorCode === "user_blocked") {
          throw new ApiError("AUTH_FORBIDDEN");
        }
        if (
          response.status === 401 &&
          [
            "invalid_refresh_token",
            "invalid_access_token",
            "invalid_session",
          ].includes(String(errorCode))
        ) {
          throw new ApiError("AUTH_INVALID");
        }
        if (response.status === 403 && errorCode === "device_revoked") {
          throw new ApiError("AUTH_INVALID");
        }
        if (response.status >= 500) throw new ApiError("SERVER_ERROR");
        throw new ApiError("HTTP_ERROR");
      }

      try {
        return await response.json();
      } catch {
        throw new ApiError(timedOut ? "TIMEOUT" : "INVALID_RESPONSE");
      }
    })();

    try {
      return await Promise.race([request, aborted]);
    } finally {
      globalThis.clearTimeout(timer);
      signal?.removeEventListener("abort", abortFromCaller);
      controller.signal.removeEventListener("abort", rejectOnAbort);
    }
  }

  return {
    async getHealth(signal) {
      const value = await requestJson("/health", { method: "GET" }, signal);
      if (!isRecord(value) || value.status !== "ok") {
        throw new ApiError("INVALID_RESPONSE");
      }
      return { status: "ok" };
    },
    async getVersion(signal) {
      const value = await requestJson("/version", { method: "GET" }, signal);
      if (
        !isRecord(value) ||
        typeof value.application_name !== "string" ||
        typeof value.application_version !== "string" ||
        typeof value.environment !== "string"
      ) {
        throw new ApiError("INVALID_RESPONSE");
      }
      return {
        application_name: value.application_name,
        application_version: value.application_version,
        environment: value.environment,
      };
    },
    async requestOtp(email, signal) {
      const value = await requestJson(
        "/auth/request-otp",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ email }),
        },
        signal,
      );
      if (!isRecord(value) || value.status !== "accepted") {
        throw new ApiError("INVALID_RESPONSE");
      }
      return { status: "accepted" };
    },
    async verifyOtp(body, signal) {
      const value = await requestJson(
        "/auth/verify-otp",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        },
        signal,
      );
      if (!isVerifyOtpResponse(value)) throw new ApiError("INVALID_RESPONSE");
      return value;
    },
    async refresh(body, signal) {
      const value = await requestJson(
        "/auth/refresh",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        },
        signal,
      );
      if (!isRefreshResponse(value)) throw new ApiError("INVALID_RESPONSE");
      return value;
    },
    async me(accessToken, signal) {
      const value = await requestJson(
        "/me",
        {
          method: "GET",
          headers: { authorization: `Bearer ${accessToken}` },
        },
        signal,
      );
      if (!isMeResponse(value)) throw new ApiError("INVALID_RESPONSE");
      return value;
    },
    async logout(accessToken, signal) {
      const value = await requestJson(
        "/auth/logout",
        {
          method: "POST",
          headers: { authorization: `Bearer ${accessToken}` },
        },
        signal,
      );
      if (!isRecord(value) || value.status !== "logged_out") {
        throw new ApiError("INVALID_RESPONSE");
      }
      return { status: "logged_out" };
    },
  };
}

function isRefreshResponse(value: unknown): value is RefreshResponse {
  return (
    isRecord(value) &&
    value.token_type === "bearer" &&
    isNonEmptyString(value.access_token) &&
    isPositiveInteger(value.access_token_expires_in) &&
    isNonEmptyString(value.refresh_token) &&
    isIsoDate(value.refresh_token_expires_at) &&
    isUuid(value.session_id)
  );
}

function isMeResponse(value: unknown): value is MeResponse {
  return (
    isRecord(value) &&
    isUuid(value.id) &&
    isNonEmptyString(value.email) &&
    ["FREE", "PREMIUM"].includes(String(value.plan)) &&
    typeof value.active_device_count === "number" &&
    Number.isInteger(value.active_device_count) &&
    value.active_device_count >= 0
  );
}

function isVerifyOtpResponse(value: unknown): value is VerifyOtpResponse {
  if (
    !isRecord(value) ||
    value.token_type !== "bearer" ||
    !isNonEmptyString(value.access_token) ||
    !isPositiveInteger(value.access_token_expires_in) ||
    !isNonEmptyString(value.refresh_token) ||
    !isIsoDate(value.refresh_token_expires_at) ||
    !isUuid(value.session_id) ||
    !isRecord(value.user) ||
    !isUuid(value.user.id) ||
    !isRecord(value.device) ||
    !isUuid(value.device.id) ||
    !isUuid(value.device.installation_id) ||
    !["ACTIVE", "REVOKED"].includes(String(value.device.status)) ||
    !isRecord(value.subscription) ||
    !["FREE", "PREMIUM"].includes(String(value.subscription.plan)) ||
    !["ACTIVE", "CANCELED", "EXPIRED"].includes(
      String(value.subscription.status),
    )
  ) {
    return false;
  }
  return true;
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function isUuid(value: unknown): value is string {
  return typeof value === "string" && UUID_PATTERN.test(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function isPositiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

function isIsoDate(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

async function readErrorCode(response: Response): Promise<unknown> {
  try {
    const value: unknown = await response.json();
    if (!isRecord(value) || !isRecord(value.error)) return undefined;
    return value.error.code;
  } catch {
    return undefined;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
