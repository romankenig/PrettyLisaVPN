import { invoke, isTauri } from "@tauri-apps/api/core";

export interface PaymentBrowser {
  open(url: string): Promise<void>;
}
export function validatePaymentUrl(
  raw: string,
  allowedHosts: readonly string[],
  websiteOrigin = "https://prettylisavpn.com",
): string {
  if (
    ["https://prettylisavpn.com", "https://test.prettylisavpn.com"].includes(
      websiteOrigin,
    ) &&
    (raw === `${websiteOrigin}/account/` ||
      (raw.startsWith(`${websiteOrigin}/account/#handoff=`) &&
        /^[A-Za-z0-9_-]{43}$/.test(
          raw.slice(`${websiteOrigin}/account/#handoff=`.length),
        )))
  )
    return raw;
  const url = new URL(raw);
  if (
    raw.length > 2048 ||
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.hash ||
    (url.port && url.port !== "443") ||
    !allowedHosts.includes(url.hostname)
  ) {
    throw new Error("PAYMENT_URL_NOT_ALLOWED");
  }
  return url.href;
}
export function createPaymentBrowser(
  allowedHosts: readonly string[],
  websiteOrigin = "https://prettylisavpn.com",
): PaymentBrowser {
  return {
    async open(raw) {
      const url = validatePaymentUrl(raw, allowedHosts, websiteOrigin);
      if (!isTauri()) throw new Error("NATIVE_PAYMENT_BROWSER_REQUIRED");
      await invoke("open_payment_url", { url });
    },
  };
}
