import { isTauri } from "@tauri-apps/api/core";
import { fetch as tauriFetch } from "@tauri-apps/plugin-http";

export type HttpTransport = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

export function createHttpTransport(): HttpTransport {
  return isTauri() ? tauriFetch : globalThis.fetch.bind(globalThis);
}
