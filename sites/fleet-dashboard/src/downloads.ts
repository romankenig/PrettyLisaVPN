export const PLATFORMS = ["android", "windows"] as const;
export type Platform = typeof PLATFORMS[number];
export const downloadUrls: Record<Platform, string> = {
  android: "/dashboard/downloads/android.apk",
  windows: "/dashboard/downloads/windows.exe",
};
export type Client = { version: string; published_at: string; bytes: number };
export type Clients = Partial<Record<Platform, Client>>;

export function readClients(value: unknown): Clients {
  if (!value || typeof value !== "object" || !("schema" in value) || value.schema !== 1 || !("clients" in value) || !value.clients || typeof value.clients !== "object") throw new Error("Invalid download catalog");
  const result: Clients = {};
  for (const platform of PLATFORMS) {
    const item = (value.clients as Record<string, unknown>)[platform];
    if (!item || typeof item !== "object") continue;
    const client = item as Record<string, unknown>;
    if (typeof client.version !== "string" || !/^\d+\.\d+\.\d+$/.test(client.version) || typeof client.published_at !== "string" || !Number.isFinite(Date.parse(client.published_at)) || typeof client.bytes !== "number" || client.bytes <= 0) continue;
    result[platform] = { version: client.version, published_at: client.published_at, bytes: client.bytes };
  }
  return result;
}
