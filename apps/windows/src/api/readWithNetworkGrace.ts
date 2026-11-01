import { ApiError } from "./client";

export const NETWORK_WARNING_GRACE_MS = 15_000;

function wait(delay: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, delay);
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
  });
}

/** Read-only Home requests tolerate a brief handover; auth errors remain immediate. */
export async function readWithNetworkGrace<T>(
  read: () => Promise<T>,
  signal: AbortSignal,
): Promise<T> {
  let failedAt: number | undefined;
  while (!signal.aborted) {
    try {
      return await read();
    } catch (error) {
      if (
        signal.aborted ||
        !(error instanceof ApiError) ||
        !["NETWORK_ERROR", "TIMEOUT"].includes(error.code)
      )
        throw error;
      failedAt ??= performance.now();
      const remaining =
        NETWORK_WARNING_GRACE_MS - (performance.now() - failedAt);
      if (remaining <= 0) throw error;
      await wait(Math.min(3_000, remaining), signal);
    }
  }
  throw new DOMException("Aborted", "AbortError");
}
