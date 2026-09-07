export interface AppConfig {
  readonly applicationName: string;
  readonly environment: "development" | "test" | "production";
  readonly backendBaseUrl: string;
}
export function loadConfig(env: Record<string, unknown>): AppConfig {
  const environment = env.VITE_APP_ENVIRONMENT ?? "development";
  if (!["development", "test", "production"].includes(String(environment))) {
    throw new Error("INVALID_APP_ENVIRONMENT");
  }
  const rawUrl = env.VITE_BACKEND_BASE_URL ?? "http://127.0.0.1:8000";
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
  return Object.freeze({
    applicationName: "PrettyLisaVPN",
    environment: environment as AppConfig["environment"],
    backendBaseUrl: url.toString().replace(/\/+$/, ""),
  });
}
