export const PLATFORMS = ["android", "windows", "chrome", "ios", "macos"] as const;
export type Platform = typeof PLATFORMS[number];
export const platformNames: Record<Platform, string> = { android: "Android", windows: "Windows", chrome: "Chrome Extension", ios: "iOS", macos: "macOS" };
export const packageLabels: Record<Platform, string> = { android: "APK", windows: "EXE", chrome: "ZIP", ios: "ZIP", macos: "ZIP" };
export const installNotes: Record<Platform, string> = {
  android: "Установите APK поверх приложения.",
  windows: "Сохраните и запустите установщик EXE.",
  chrome: "Распакуйте ZIP. В chrome://extensions включите режим разработчика и выберите «Загрузить распакованное расширение». Защита действует только в Chrome.",
  ios: "Неподписанная сборка для устройства. Для установки на iPhone нужны подпись и профиль Apple; это не App Store или TestFlight. Работа VPN на устройстве пока не подтверждена.",
  macos: "Неподписанная сборка приложения. Для работы VPN нужны подпись Apple и разрешения Network Extension. Работа VPN на Mac пока не подтверждена.",
};
export const downloadUrls: Record<Platform, string> = {
  android: "/dashboard/downloads/android.apk",
  windows: "/dashboard/downloads/windows.exe",
  chrome: "/dashboard/downloads/chrome-extension.zip",
  ios: "/dashboard/downloads/ios-unsigned.zip",
  macos: "/dashboard/downloads/macos-unsigned.zip",
};
export const sourceUrls: Partial<Record<Platform, string>> = {
  android: "/dashboard/downloads/android-sources.tar.gz",
  windows: "/dashboard/downloads/windows-sources.tar.gz",
  ios: "/dashboard/downloads/ios-sources.tar.gz",
  macos: "/dashboard/downloads/macos-sources.tar.gz",
};
export type Client = { version: string; published_at: string; bytes: number; has_sources?: true; abi?: "arm64-v8a" };
export type Clients = Partial<Record<Platform, Client>>;

export function readClients(value: unknown): Clients {
  if (!value || typeof value !== "object" || !("schema" in value) || value.schema !== 1 || !("clients" in value) || !value.clients || typeof value.clients !== "object") throw new Error("Invalid download catalog");
  const result: Clients = {};
  for (const platform of PLATFORMS) {
    const item = (value.clients as Record<string, unknown>)[platform];
    if (!item || typeof item !== "object") continue;
    const client = item as Record<string, unknown>;
    if (typeof client.version !== "string" || !/^\d+\.\d+\.\d+$/.test(client.version) || typeof client.published_at !== "string" || !Number.isFinite(Date.parse(client.published_at)) || typeof client.bytes !== "number" || client.bytes <= 0) continue;
    if ((platform === "ios" || platform === "macos") && client.package_kind !== "unsigned-app") continue;
    if (platform === "chrome" && client.package_kind !== "unpacked-extension") continue;
    result[platform] = { version: client.version, published_at: client.published_at, bytes: client.bytes };
    if (platform === "android" && client.abi === "arm64-v8a") result[platform]!.abi = "arm64-v8a";
    if (sourceUrls[platform] && client.sources_url === sourceUrls[platform] && typeof client.sources_sha256 === "string" && /^[a-f0-9]{64}$/.test(client.sources_sha256)) result[platform]!.has_sources = true;
  }
  return result;
}
