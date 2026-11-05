export const API = "https://api.prettylisavpn.com";
export const PROBE = "https://prettylisavpn.com";
export const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export interface Account {
  id: string;
  email: string;
  plan: "FREE" | "PREMIUM" | "PLATINUM";
  active_device_count: number;
  entitlements?: {
    free_seconds_remaining?: number | null;
    free_seconds_usable?: number | null;
  };
}
export interface Country {
  country_code: string;
  available: boolean;
  quality: number;
}
export interface Device {
  id: string;
  device_name: string;
  status: string;
  is_current: boolean;
  created_at: string;
  last_login_at: string | null;
}
export interface ProxyConfig {
  scheme: "https";
  host: string;
  port: number;
  username: string;
  password: string;
}
export interface Lease {
  id: string;
  status: "PROVISIONING" | "READY" | "REVOKING" | "CLOSED";
  code: string | null;
  country: string;
  method: "https_proxy";
  expires_at: string;
  configuration?: {
    proxy: ProxyConfig;
    expected_egress_ips: string[];
    scope: "browser";
    dns: "remote";
    ipv6: "blocked";
  };
}
export interface Session {
  access_token: string;
  refresh_token: string;
  session_id: string;
  device?: { id: string };
  user?: { id: string };
}
export type Phase =
  | "DISCONNECTED"
  | "CONNECTING"
  | "VERIFYING"
  | "CONNECTED"
  | "DISCONNECTING"
  | "FAILED";
export interface Snapshot {
  phase: Phase;
  error: string | null;
  signedIn: boolean;
  otpEmail: string | null;
  account: Account | null;
  countries: Country[];
  backend: string | null;
  ip: string | null;
  country: string | null;
  expires: string | null;
  cleanupPending: boolean;
}
export function validateLease(value: unknown): Lease {
  const row = value as Lease;
  if (
    !row ||
    !UUID.test(row.id) ||
    row.method !== "https_proxy" ||
    !["PROVISIONING", "READY", "REVOKING", "CLOSED"].includes(row.status) ||
    !Number.isFinite(Date.parse(row.expires_at))
  )
    throw new Error("INVALID_RESPONSE");
  if (row.status === "READY") {
    const config = row.configuration,
      proxy = config?.proxy;
    if (
      !proxy ||
      proxy.scheme !== "https" ||
      !/^proxy-[a-z0-9-]+\.prettylisavpn\.com$/.test(proxy.host) ||
      !Number.isInteger(proxy.port) ||
      proxy.port < 40000 ||
      proxy.port > 49899 ||
      proxy.username !== row.id ||
      !UUID.test(proxy.password) ||
      config?.scope !== "browser" ||
      config.dns !== "remote" ||
      config.ipv6 !== "blocked" ||
      !Array.isArray(config.expected_egress_ips) ||
      config.expected_egress_ips.length === 0 ||
      config.expected_egress_ips.some(
        (ip) => !/^\d{1,3}(\.\d{1,3}){3}$/.test(ip),
      )
    )
      throw new Error("UNSUPPORTED_CONFIGURATION");
  }
  return row;
}
export function proxySettings(proxy: ProxyConfig): chrome.proxy.ProxyConfig {
  return {
    mode: "fixed_servers",
    rules: {
      singleProxy: { scheme: "https", host: proxy.host, port: proxy.port },
      bypassList: ["<-loopback>", "api.prettylisavpn.com"],
    },
  };
}
export function controlsProxy(
  details: chrome.types.ChromeSettingGetResult<chrome.proxy.ProxyConfig>,
  proxy: ProxyConfig,
): boolean {
  const value = details.value as chrome.proxy.ProxyConfig;
  const actual = value?.rules?.singleProxy;
  return (
    details.levelOfControl === "controlled_by_this_extension" &&
    value.mode === "fixed_servers" &&
    actual?.scheme === "https" &&
    actual.host === proxy.host &&
    actual.port === proxy.port &&
    value.rules?.bypassList?.join() === "<-loopback>,api.prettylisavpn.com"
  );
}
export function proxyAuth(
  details: Pick<
    chrome.webRequest.OnAuthRequiredDetails,
    "isProxy" | "challenger" | "realm"
  >,
  proxy?: ProxyConfig,
): boolean {
  return Boolean(
    proxy &&
    details.isProxy &&
    details.challenger.host.toLowerCase() === proxy.host &&
    details.challenger.port === proxy.port &&
    details.realm === "PrettyLisaVPN",
  );
}
export function errorCode(error: unknown): string {
  const value = error instanceof Error ? error.message : "REQUEST_FAILED";
  return /^[A-Z][A-Z0-9_]{0,63}$/.test(value) ? value : "REQUEST_FAILED";
}
