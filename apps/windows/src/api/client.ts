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

export type ApiErrorCode =
  | "NETWORK_ERROR"
  | "TIMEOUT"
  | "RATE_LIMITED"
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
        if (
          response.status === 429 &&
          (await readErrorCode(response)) === "otp_rate_limited"
        ) {
          throw new ApiError("RATE_LIMITED");
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
  };
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
