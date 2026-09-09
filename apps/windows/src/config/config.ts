export interface AppConfig {
  readonly applicationName: string;
  readonly environment: "development" | "test" | "production";
  readonly backendBaseUrl: string;
  readonly backendTimeoutMs: number;
  readonly backendHealthIntervalMs: number;
}
export function loadConfig(env: Record<string, unknown>): AppConfig {
  const environment = env.VITE_APP_ENVIRONMENT ?? "development";
  if (!["development", "test", "production"].includes(String(environment))) {
    throw new Error("INVALID_APP_ENVIRONMENT");
  }
  const rawUrl = env.VITE_BACKEND_BASE_URL ?? "https://api.prettylisavpn.com";
  let url: URL;
  try {
    url = new URL(String(rawUrl));
  } catch {
    throw new Error("INVALID_BACKEND_BASE_URL");
  }
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    throw new Error("INVALID_BACKEND_BASE_URL");
  }
  if (environment === "production" && url.protocol !== "https:") {
    throw new Error("BACKEND_HTTPS_REQUIRED");
  }
  // OTP delivery waits for the Backend's bounded SMTP send (up to 10 seconds).
  // Keep the client deadline above that bound so a slow but valid delivery is
  // not reported as a network failure.
  const backendTimeoutMs = Number(env.VITE_BACKEND_TIMEOUT_MS ?? 15000);
  if (
    !Number.isInteger(backendTimeoutMs) ||
    backendTimeoutMs < 1000 ||
    backendTimeoutMs > 30000
  ) {
    throw new Error("INVALID_BACKEND_TIMEOUT");
  }
  const backendHealthIntervalMs = Number(
    env.VITE_BACKEND_HEALTH_INTERVAL_MS ?? 15000,
  );
  if (
    !Number.isInteger(backendHealthIntervalMs) ||
    backendHealthIntervalMs < backendTimeoutMs ||
    backendHealthIntervalMs > 60000
  ) {
    throw new Error("INVALID_BACKEND_HEALTH_INTERVAL");
  }
  return Object.freeze({
    applicationName: "PrettyLisaVPN",
    environment: environment as AppConfig["environment"],
    backendBaseUrl: url.toString().replace(/\/+$/, ""),
    backendTimeoutMs,
    backendHealthIntervalMs,
  });
}
