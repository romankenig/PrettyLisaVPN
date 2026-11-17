import { categoryColors } from "./selectionHistory.ts";

export const appPlatforms: Record<string, string> = { WINDOWS: "Windows", ANDROID: "Android", CHROME_EXTENSION: "Chrome Extension", MACOS: "macOS", IOS: "iOS", LINUX: "Linux", ANDROID_TV: "Android TV" };
export type VersionCounts = { users: Record<string, number>; devices: Record<string, number>; active_users: number };
export type VersionDay = { date: string; partial: boolean; platforms: Record<string, VersionCounts> | null };
export type VersionReport = { plan?: string; schema: 1; timezone: "GMT+3"; generated_at: string; collection_started_at: string | null; from_date: string; through_date: string; points: VersionDay[] };
export function readVersionReport(value: unknown): VersionReport {
  const data = value as VersionReport;
  if (!data || data.schema !== 1 || data.timezone !== "GMT+3" || !Number.isFinite(Date.parse(data.generated_at)) || (data.collection_started_at !== null && !Number.isFinite(Date.parse(data.collection_started_at))) || !Array.isArray(data.points) || data.points.length !== 31) throw new Error("Invalid version report");
  let previous: number | undefined;
  for (const [i, point] of data.points.entries()) {
    if (!point || !/^\d{4}-\d{2}-\d{2}$/.test(point.date) || !Number.isFinite(Date.parse(point.date)) || (previous !== undefined && Date.parse(point.date) - previous !== 86400_000) || point.partial !== (i === 30)) throw new Error("Invalid version date");
    previous = Date.parse(point.date);
    if (point.platforms === null) continue;
    if (!point.platforms || typeof point.platforms !== "object" || Array.isArray(point.platforms)) throw new Error("Invalid platforms");
    for (const [platform, counts] of Object.entries(point.platforms)) {
      if (!Object.hasOwn(appPlatforms, platform) || !counts || !Number.isSafeInteger(counts.active_users) || counts.active_users < 0) throw new Error("Invalid platform counts");
      for (const values of [counts.users, counts.devices]) {
        if (!values || typeof values !== "object" || Array.isArray(values) || !Object.entries(values).every(([version, n]) => (version === "UNKNOWN" || /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$/.test(version)) && version.length <= 100 && Number.isSafeInteger(n) && n > 0)) throw new Error("Invalid version counts");
      }
      const users = Object.values(counts.users).reduce((a, b) => a + b, 0);
      if (counts.active_users > users || Object.entries(counts.users).some(([v, n]) => n > (counts.devices[v] ?? 0) || n > counts.active_users) || Object.keys(counts.devices).some(v => !(v in counts.users))) throw new Error("Invalid users");
    }
  }
  if (data.from_date !== data.points[0].date || data.through_date !== data.points[30].date || new Date(Date.parse(data.generated_at) + 3 * 3600_000).toISOString().slice(0, 10) !== data.through_date) throw new Error("Invalid version period");
  return data;
}
export function versionSeries(data: VersionReport, platform: string, shares: boolean) {
  const versions = [...new Set(data.points.flatMap(p => Object.keys(p.platforms?.[platform]?.users ?? {})))].sort((a, b) => a === "UNKNOWN" ? 1 : b === "UNKNOWN" ? -1 : a.localeCompare(b, undefined, { numeric: true }));
  const colors = categoryColors(versions);
  return versions.map(name => ({ name, color: colors.get(name)!, values: data.points.map(point => {
    if (point.platforms === null) return null;
    const counts = point.platforms[platform]?.users ?? {}, total = Object.values(counts).reduce((a, b) => a + b, 0);
    return shares ? total ? 100 * (counts[name] ?? 0) / total : null : counts[name] ?? 0;
  }) }));
}
