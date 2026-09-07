import type { HttpTransport } from "../native/http";

export interface BackendHealth {
  readonly status: "ok";
}

export interface BackendVersion {
  readonly application_name: string;
  readonly application_version: string;
  readonly environment: string;
}

export type ApiErrorCode =
  "NETWORK_ERROR" | "TIMEOUT" | "HTTP_ERROR" | "INVALID_RESPONSE";

export class ApiError extends Error {
  constructor(readonly code: ApiErrorCode) {
    super(code);
    this.name = "ApiError";
  }
}

export interface ApiClient {
  getHealth(signal?: AbortSignal): Promise<BackendHealth>;
  getVersion(signal?: AbortSignal): Promise<BackendVersion>;
}

export function createApiClient(
  baseUrl: string,
  transport: HttpTransport,
  timeoutMs: number,
): ApiClient {
  async function requestJson(
    path: string,
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
          method: "GET",
          signal: controller.signal,
          credentials: "omit",
        });
      } catch {
        throw new ApiError(timedOut ? "TIMEOUT" : "NETWORK_ERROR");
      }

      if (!response.ok) throw new ApiError("HTTP_ERROR");

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
      const value = await requestJson("/health", signal);
      if (!isRecord(value) || value.status !== "ok") {
        throw new ApiError("INVALID_RESPONSE");
      }
      return { status: "ok" };
    },
    async getVersion(signal) {
      const value = await requestJson("/version", signal);
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
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
