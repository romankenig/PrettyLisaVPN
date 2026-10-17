import type { HttpTransport } from "../native/http";
import { MessagesError, parseMessages, validateAcknowledgement, type MessagesClient } from "./model";

// Proposed authenticated API; absence must not delay or invalidate login.
export function createMessagesClient(base: string, transport: HttpTransport, timeout = 5000): MessagesClient {
  async function request(path: string, token: string, signal: AbortSignal, body?: unknown) {
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) controller.abort();
    const timer = setTimeout(abort, timeout);
    try {
      const response = await transport(base + path, {
        method: body === undefined ? "GET" : "POST",
        headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
        cache: "no-store",
        credentials: "omit",
        redirect: "error",
      });
      if (response.status === 404 || response.status === 501) throw new MessagesError("UNSUPPORTED");
      if (response.status === 401 || response.status === 403) throw new MessagesError("AUTH_INVALID");
      if (!response.ok) throw new MessagesError("UNAVAILABLE");
      const raw = await response.text();
      if (raw.length > 65536) throw new MessagesError("INVALID_RESPONSE");
      return JSON.parse(raw) as unknown;
    } catch (error) {
      if (error instanceof MessagesError) throw error;
      throw new MessagesError("UNAVAILABLE");
    } finally {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
    }
  }
  return {
    async list(token, context, signal) {
      const query = new URLSearchParams({
        platform: context.platform,
        app_version: context.app_version,
        locale: context.locale,
        schema_version: String(context.schema_version),
      });
      return parseMessages(await request(`/messages?${query}`, token, signal));
    },
    async acknowledge(token, message, signal) {
      validateAcknowledgement(await request(`/messages/${encodeURIComponent(message.id)}/acknowledgements`, token, signal, { revision: message.revision }), message);
    },
  };
}
