import { ApiError } from "../api/client";
import type { HttpTransport } from "../native/http";
import {
  parseOperation,
  parseOverview,
  parseOffers,
  type BillingClient,
} from "./model";

// Server overview; operation methods remain guarded by backend capabilities.
export function createBillingClient(
  base: string,
  transport: HttpTransport,
  timeout: number,
): BillingClient {
  async function request(
    path: string,
    token: string,
    signal: AbortSignal,
    body?: unknown,
  ): Promise<unknown> {
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) controller.abort();
    const timer = setTimeout(abort, timeout);
    try {
      const response = await transport(base + path, {
        method: body === undefined ? "GET" : "POST",
        headers: {
          authorization: `Bearer ${token}`,
          "content-type": "application/json",
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
        credentials: "omit",
        cache: "no-store",
        redirect: "error",
      });
      if (response.status === 401 || response.status === 403)
        throw new ApiError("AUTH_INVALID");
      if (!response.ok)
        throw new ApiError(
          response.status >= 500 ? "SERVER_ERROR" : "HTTP_ERROR",
        );
      return await response.json();
    } finally {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
    }
  }
  return {
    catalog: async (signal) => {
      const response = await transport(base + "/billing/catalog", {
        signal: AbortSignal.any([signal, AbortSignal.timeout(timeout)]),
        credentials: "omit",
        redirect: "error",
        cache: "no-store",
      });
      if (!response.ok) throw new ApiError("SERVER_ERROR");
      const value = await response.json();
      return parseOffers(value?.offers);
    },
    portal: async (token, signal) => {
      const value = await request("/billing/portal", token, signal, {});
      const raw =
        value && typeof value === "object" && "url" in value ? value.url : null;
      if (
        typeof raw !== "string" ||
        !/^https:\/\/prettylisavpn\.com\/account\/#handoff=[A-Za-z0-9_-]{43}$/.test(
          raw,
        )
      )
        throw new Error("PAYMENT_URL_NOT_ALLOWED");
      return raw;
    },
    overview: async (token, signal) =>
      parseOverview(await request("/billing/overview", token, signal)),
    start: async (token, command, signal) =>
      parseOperation(
        await request("/billing/operations", token, signal, command),
      ),
    operation: async (token, id, signal) =>
      parseOperation(
        await request(
          `/billing/operations/${encodeURIComponent(id)}`,
          token,
          signal,
        ),
      ),
  };
}
