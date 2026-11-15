export const plans = ["DEMO", "FREE", "PREMIUM", "PLATINUM", "UNKNOWN"] as const;
export type Plan = typeof plans[number];
export type ActiveMetric = "dau" | "wau" | "mau";
export type Count = { total: number | null; plans: Record<Plan, number | null>; complete: boolean };
export type DevicePlatforms = { connections: Record<string, number> | null; users: Record<string, number> | null };
export type DevicePoint = { date: string; device_platforms?: DevicePlatforms; partial?: boolean };
export type CurrentDevicePoint = DevicePoint & { partial: true; updated_at: string; device_platforms: { connections: Record<string, number>; users: Record<string, number> } };
export type AnalyticsPoint = {
  date: string; complete: boolean; dau: Count; wau: Count; mau: Count;
  new_accounts: number; verified_sessions: number | null; connection_success_percent: number | null;
  settled_attempts: number | null; pending_attempts: number | null;
  median_connection_seconds: number | null; engagement_percent: number | null;
  mean_session_seconds?: number | null; completed_sessions?: number;
  device_platforms?: DevicePlatforms;
};
export type Distribution = { bounds_seconds: number[]; counts: number[]; shares: (number | null)[]; samples: number };
export type Analytics = {
  schema: 1; generated_at: string; next_update_at: string; from_date: string; through_date: string;
  timezone: string; observed_from: string | null; full_collection_from: string; history_partial: boolean;
  attempts_from: string | null; points: AnalyticsPoint[]; methods: Record<string, number>;
  devices?: Record<string, number>; session_duration?: Distribution; time_to_silence?: Distribution;
  mean_session_seconds?: number | null; duration_unobserved_sessions?: number; silence_unobserved_sessions?: number;
  device_today?: CurrentDevicePoint;
};
function validateDevices(devices: DevicePlatforms) {
  if (!devices || typeof devices !== "object") throw new Error("Invalid device distribution");
  for (const metric of ["connections", "users"] as const) {
    const counts = devices[metric];
    if (counts !== null && (!counts || typeof counts !== "object" || Array.isArray(counts) || !Object.values(counts).every(v => Number.isSafeInteger(v) && v >= 0))) throw new Error("Invalid device counts");
  }
  if (devices.connections === null ? devices.users !== null : Object.entries(devices.users ?? {}).some(([platform, count]) => count > (devices.connections?.[platform] ?? 0))) throw new Error("Invalid device users");
}
export function readAnalytics(value: unknown): Analytics {
  if (!value || typeof value !== "object") throw new Error("Invalid analytics");
  const data = value as Analytics;
  if (data.schema !== 1 || data.timezone !== "GMT+3" || !Number.isFinite(Date.parse(data.generated_at)) || !Number.isFinite(Date.parse(data.next_update_at)) || !Array.isArray(data.points) || data.points.length > 62 || !data.points.length) throw new Error("Invalid analytics");
  const number = (v: unknown) => v === null || (typeof v === "number" && Number.isFinite(v) && v >= 0);
  let previous = "";
  for (const point of data.points) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(point.date) || point.date <= previous || point.date > data.through_date) throw new Error("Invalid date");
    previous = point.date;
    for (const metric of ["mau", "wau", "dau"] as const) {
      const count = point[metric];
      if (count?.plans && count.plans.DEMO === undefined) count.plans.DEMO = count.total === null ? null : 0;
      if (!count || !number(count.total) || !count.plans || !plans.every(plan => number(count.plans[plan]))) throw new Error("Invalid count");
      if (count.total !== null && plans.reduce((sum, plan) => sum + (count.plans[plan] ?? 0), 0) !== count.total) throw new Error("Invalid cohorts");
    }
    for (const metric of ["new_accounts", "verified_sessions", "connection_success_percent", "settled_attempts", "pending_attempts", "median_connection_seconds", "engagement_percent"] as const) if (!number(point[metric])) throw new Error("Invalid metric");
    if (point.device_platforms !== undefined) {
      const devices = point.device_platforms;
      validateDevices(devices);
      if (devices.connections !== null && Object.values(devices.connections).reduce((sum, count) => sum + count, 0) !== point.verified_sessions) throw new Error("Invalid device connections");
    }
  }
  if (data.points[0].date !== data.from_date || previous !== data.through_date) throw new Error("Invalid period");
  if (data.device_today !== undefined) {
    const today = data.device_today;
    if (!today || today.partial !== true || !/^\d{4}-\d{2}-\d{2}$/.test(today.date) || today.date <= data.through_date || !Number.isFinite(Date.parse(today.updated_at)) || new Date(Date.parse(today.updated_at) + 3 * 3600_000).toISOString().slice(0, 10) !== today.date) throw new Error("Invalid current device day");
    validateDevices(today.device_platforms);
    if (today.device_platforms.connections === null || today.device_platforms.users === null) throw new Error("Invalid current device counts");
  }
  return data;
}
export const formatNumber = (value: number | null | undefined) => value == null ? "—" : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(value);
export const formatDay = (value: string) => new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(value + "T00:00:00Z"));
export function planShare(count: Count, plan: Plan): number | null {
  const value = count.plans[plan];
  return count.total && value !== null ? 100 * value / count.total : null;
}
export type Series = { name: string; color: string; values: (number | null)[]; dashed?: boolean };
export function segments(values: (number | null)[]): { index: number; value: number }[][] {
  const result: { index: number; value: number }[][] = [];
  let current: { index: number; value: number }[] = [];
  values.forEach((value, index) => { if (value == null) { if (current.length) result.push(current); current = []; } else current.push({ index, value }); });
  if (current.length) result.push(current);
  return result;
}
