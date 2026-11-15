import type { CurrentDevicePoint, DevicePoint, Series } from "./analytics.ts";

export type DeviceMeasure = "users" | "connections";
const names: Record<string, string> = { ANDROID: "Android", WINDOWS: "Windows", IOS: "iOS", MACOS: "macOS", LINUX: "Linux", ANDROID_TV: "Android TV", CHROME_EXTENSION: "Chrome", UNKNOWN: "Неизвестно" };
const colors = ["#5f22d9", "#17655c", "#ac73ff", "#2c016d", "#51d6ca", "#5b5b5b", "#6877aa", "#9c9c9c"];
export function deviceChartPoints(points: DevicePoint[], today?: CurrentDevicePoint): DevicePoint[] {
  if (!today) return points;
  const end = Date.parse(today.date), day = 86400_000;
  const start = Math.max(Date.parse(points[0]?.date ?? today.date), end - 62 * day);
  const history = new Map(points.map(point => [point.date, point]));
  const result: DevicePoint[] = [];
  for (let at = start; at <= end; at += day) {
    const date = new Date(at).toISOString().slice(0, 10);
    result.push(date === today.date ? today : history.get(date) ?? { date, device_platforms: { connections: null, users: null } });
  }
  return result;
}
export function deviceTotal(point: DevicePoint, measure: DeviceMeasure): number | null {
  const counts = point.device_platforms?.[measure];
  return counts == null ? null : Object.values(counts).reduce((sum, count) => sum + count, 0);
}
export function deviceSeries(points: DevicePoint[], measure: DeviceMeasure, shares: boolean): Series[] {
  const platforms = [...new Set(points.flatMap(point => Object.keys(point.device_platforms?.connections ?? {})))].sort((a, b) => {
    const order = Object.keys(names);
    return (order.indexOf(a) < 0 ? order.length : order.indexOf(a)) - (order.indexOf(b) < 0 ? order.length : order.indexOf(b)) || a.localeCompare(b);
  });
  return platforms.map(platform => ({
    name: names[platform] ?? platform,
    color: colors[Object.keys(names).indexOf(platform)] ?? "#9c9c9c",
    values: points.map(point => {
      const counts = point.device_platforms?.[measure], total = deviceTotal(point, measure);
      if (counts == null || (shares && !total)) return null;
      const count = counts[platform] ?? 0;
      return shares ? 100 * count / total! : count;
    }),
  }));
}
