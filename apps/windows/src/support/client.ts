import type { HttpTransport } from "../native/http";
import type { SupportReceipt, SupportSender, SupportSubmission } from "./model";

export class SupportError extends Error {
  constructor(readonly code: string) {
    super(code);
    this.name = "SupportError";
  }
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const statuses = ["ACCEPTED", "RETRYING", "SENT", "FAILED", "EXPIRED"];

export function createSupportSender(
  base: string,
  transport: HttpTransport,
  timeout = 30000,
): SupportSender {
  async function request(
    id: string,
    token: string,
    signal: AbortSignal,
    submission?: SupportSubmission,
  ): Promise<SupportReceipt | null> {
    if (!uuid.test(id)) throw new SupportError("INVALID_REQUEST");
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) controller.abort();
    const timer = setTimeout(abort, timeout);
    try {
      let body: FormData | undefined;
      if (submission) {
        const { screenshots, ...report } = submission;
        body = new FormData();
        body.append("report", JSON.stringify(report));
        screenshots.forEach((file, index) =>
          body!.append("screenshots", file, `screenshot-${index + 1}`),
        );
      }
      const response = await transport(
        `${base}/support/requests${submission ? "" : `/${encodeURIComponent(id)}`}`,
        {
          method: submission ? "POST" : "GET",
          headers: { authorization: `Bearer ${token}` },
          body,
          signal: controller.signal,
          cache: "no-store",
          credentials: "omit",
          redirect: "error",
        },
      );
      if (!submission && response.status === 404) return null;
      if (response.status === 401 || response.status === 403)
        throw new SupportError("AUTH_INVALID");
      if (response.status === 409)
        throw new SupportError("IDEMPOTENCY_CONFLICT");
      if (response.status === 429) throw new SupportError("RATE_LIMITED");
      if (!response.ok) throw new SupportError("SUPPORT_UNAVAILABLE");
      if (!response.headers.get("content-type")?.includes("application/json"))
        throw new SupportError("INVALID_RESPONSE");
      const raw = await response.text();
      if (raw.length > 2048) throw new SupportError("INVALID_RESPONSE");
      const value = JSON.parse(raw) as Partial<SupportReceipt> | null;
      if (
        !value ||
        value.request_id !== id ||
        !statuses.includes(value.status ?? "")
      )
        throw new SupportError("INVALID_RESPONSE");
      return value as SupportReceipt;
    } catch (error) {
      if (error instanceof SupportError) throw error;
      throw new SupportError("SUPPORT_UNAVAILABLE");
    } finally {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
    }
  }
  return {
    getStatus: (id, token, signal) => request(id, token, signal),
    async send(submission, token, signal) {
      // A failed lookup must never be treated as absence. Only a definite 404
      // permits a POST; every POST still uses the original idempotency UUID.
      const existing = await request(submission.request_id, token, signal);
      if (existing) return existing;
      const accepted = await request(
        submission.request_id,
        token,
        signal,
        submission,
      );
      if (!accepted) throw new SupportError("INVALID_RESPONSE");
      return accepted;
    },
  };
}
