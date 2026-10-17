import type { Currency, PaymentRoute } from "./model";

const COUNTRY_KEY = "prettylisavpn:country-before-vpn";
const memoryRequests = new Map<string, { fingerprint: string; id: string }>();
export const COUNTRY_EVENT = "billing-country-changed";
export function rememberHomeCountry(country: string | null): void {
  if (!country || !/^[A-Z]{2}$/.test(country)) return;
  try {
    localStorage.setItem(COUNTRY_KEY, country);
  } catch {
    /* Optional preference. */
  }
  window.dispatchEvent(new Event(COUNTRY_EVENT));
}
export function preferredCurrency(user: string): Currency {
  try {
    const manual = localStorage.getItem(`prettylisavpn:currency:${user}`);
    if (manual === "RUB" || manual === "USD") return manual;
    return localStorage.getItem(COUNTRY_KEY) === "RU" ? "RUB" : "USD";
  } catch {
    return "USD";
  }
}
export function saveCurrency(user: string, currency: Currency): void {
  try {
    localStorage.setItem(`prettylisavpn:currency:${user}`, currency);
  } catch {
    /* Optional preference. */
  }
}

// Keep a request ID across navigation/retries so a timeout cannot duplicate a charge.
export function requestId(
  user: string,
  revision: string,
  action: string,
  offer: string | null,
  currency: Currency,
  route: PaymentRoute | null = null,
): string {
  const key = `prettylisavpn:billing-request:${user}`;
  const fingerprint = JSON.stringify([revision, action, offer, currency, route]);
  const cached = readSession(key) ?? memoryRequests.get(key);
  if (cached?.fingerprint === fingerprint && typeof cached.id === "string")
    return cached.id;
  const id = crypto.randomUUID();
  memoryRequests.set(key, { fingerprint, id });
  writeSession(key, { fingerprint, id });
  return id;
}
export function pendingOperation(user: string): string | null {
  const value = readSession(`prettylisavpn:billing-pending:${user}`);
  return typeof value?.id === "string" ? value.id : null;
}
export function savePendingOperation(user: string, id: string | null): void {
  writeSession(`prettylisavpn:billing-pending:${user}`, { id });
}
export function clearRequestId(user: string): void {
  memoryRequests.delete(`prettylisavpn:billing-request:${user}`);
  try {
    sessionStorage.removeItem(`prettylisavpn:billing-request:${user}`);
  } catch {
    /* Optional recovery. */
  }
}
function readSession(key: string): Record<string, unknown> | null {
  try {
    return JSON.parse(sessionStorage.getItem(key) ?? "null") as Record<
      string,
      unknown
    > | null;
  } catch {
    return null;
  }
}
function writeSession(key: string, value: unknown): void {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* In-memory request guard remains active. */
  }
}
