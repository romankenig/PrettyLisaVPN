import type { HttpTransport } from "../native/http";

export interface PublicLocation {
  readonly ip: string;
  readonly countryCode: string | null;
  readonly city: string | null;
}
export interface PublicLocationProvider {
  current(signal: AbortSignal): Promise<PublicLocation>;
}

// This provider observes the request's actual egress, not a selected VPN node.
// No auth headers, browsing data, coordinates or persistent location history.
export function createPublicLocationProvider(
  transport: HttpTransport,
  endpoint = "https://ipwho.is/",
  allowLoopback = false,
): PublicLocationProvider {
  const url = new URL(endpoint);
  if ((url.protocol !== "https:" && !(allowLoopback && url.protocol === "http:" && url.hostname === "127.0.0.1")) || url.username || url.password || url.hash) {
    throw new Error("INVALID_PUBLIC_LOCATION_URL");
  }
  return {
    async current(signal) {
      const controller = new AbortController();
      const abort = () => controller.abort();
      signal.addEventListener("abort", abort, { once: true });
      if (signal.aborted) controller.abort();
      let rejectAbort: () => void = () => undefined;
      const aborted = new Promise<never>((_, reject) => {
        rejectAbort = () => reject(new Error("PUBLIC_LOCATION_UNAVAILABLE"));
        controller.signal.addEventListener("abort", rejectAbort, { once: true });
        if (controller.signal.aborted) rejectAbort();
      });
      const timer = globalThis.setTimeout(() => controller.abort(), 8000);
      try {
        return await Promise.race([
          (async () => {
            const response = await transport(url, { method: "GET", credentials: "omit", cache: "no-store", signal: controller.signal });
            if (!response.ok) throw new Error("PUBLIC_LOCATION_UNAVAILABLE");
            return parsePublicLocation(await response.json());
          })(),
          aborted,
        ]);
      } finally {
        globalThis.clearTimeout(timer);
        signal.removeEventListener("abort", abort);
        controller.signal.removeEventListener("abort", rejectAbort);
      }
    },
  };
}

export function parsePublicLocation(value: unknown): PublicLocation {
  if (typeof value !== "object" || value === null || !("success" in value) || value.success !== true || !("ip" in value) || typeof value.ip !== "string" || !isIp(value.ip)) {
    throw new Error("INVALID_PUBLIC_LOCATION");
  }
  const countryCode = "country_code" in value && typeof value.country_code === "string" && /^[A-Z]{2}$/.test(value.country_code) ? value.country_code : null;
  const city = "city" in value && typeof value.city === "string" && value.city.trim().length <= 120 ? value.city.trim() || null : null;
  return { ip: value.ip, countryCode, city };
}

function isIp(value: string): boolean {
  if (/^(\d{1,3}\.){3}\d{1,3}$/.test(value)) return value.split(".").every((part) => Number(part) <= 255);
  if (!value.includes(":")) return false;
  try { return new URL(`https://[${value}]/`).hostname.startsWith("["); } catch { return false; }
}
