import { invoke, isTauri } from "@tauri-apps/api/core";

export interface PaymentBrowser {
  open(url: string): Promise<void>;
}
export function validatePaymentUrl(raw: string, allowedHosts: readonly string[]): string {
  const url = new URL(raw);
  if (raw.length > 2048 || url.protocol !== "https:" || url.username || url.password ||
    url.hash || (url.port && url.port !== "443") || !allowedHosts.includes(url.hostname)) {
    throw new Error("PAYMENT_URL_NOT_ALLOWED");
  }
  return url.href;
}
export function createPaymentBrowser(allowedHosts: readonly string[]): PaymentBrowser {
  return {
    async open(raw) {
      const url = validatePaymentUrl(raw, allowedHosts);
      if (!isTauri()) throw new Error("NATIVE_PAYMENT_BROWSER_REQUIRED");
      await invoke("open_payment_url", { url });
    },
  };
}
