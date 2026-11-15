import type { AnalyticsPoint, Series } from "./analytics.ts";

export type DeviceMeasure = "users" | "connections";
const names: Record<string, string> = { ANDROID: "Android", WINDOWS: "Windows", IOS: "iOS", MACOS: "macOS", LINUX: "Linux", ANDROID_TV: "Android TV", CHROME_EXTENSION: "Chrome", UNKNOWN: "Неизвестно" };
const colors = ["#5f22d9", "#17655c", "#ac73ff", "#2c016d", "#51d6ca", "#5b5b5b", "#6877aa", "#9c9c9c"];
export function deviceTotal(point: AnalyticsPoint, measure: DeviceMeasure): number | null {
  const counts = point.device_platforms?.[measure];
  return counts == null ? null : Object.values(counts).reduce((sum, count) => sum + count, 0);
}
export function deviceSeries(points: AnalyticsPoint[], measure: DeviceMeasure, shares: boolean): Series[] {
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
