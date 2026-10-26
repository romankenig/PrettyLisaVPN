import type { ConnectionAdapter } from "../protocol";

export const PLACEHOLDER_DELAY_MS = 3_000;

/** No network, keys, native commands, server sessions or quota consumption. */
export function placeholder(id: string, name: string): ConnectionAdapter {
  return {
    id,
    name,
    connect(_selection, signal) {
      return new Promise((resolve, reject) => {
        if (signal.aborted) {
          reject(new DOMException("Cancelled", "AbortError"));
          return;
        }
        const abort = () => {
          clearTimeout(timer);
          signal.removeEventListener("abort", abort);
          reject(new DOMException("Cancelled", "AbortError"));
        };
        const timer = setTimeout(() => {
          signal.removeEventListener("abort", abort);
          resolve({ connected: false });
        }, PLACEHOLDER_DELAY_MS);
        signal.addEventListener("abort", abort, { once: true });
      });
    },
    async disconnect() {},
  };
}
