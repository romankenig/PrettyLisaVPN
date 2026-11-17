import { readDurationHistory, type DurationHistory } from "./durationHistory.ts";

export const plans = ["DEMO", "FREE", "PREMIUM", "PLATINUM", "UNKNOWN"] as const;
export type Plan = typeof plans[number];
export type ActiveMetric = "dau" | "wau" | "mau";
export type Count = { total: number | null; plans: Record<Plan, number | null>; complete: boolean };
export type DevicePlatforms = { connections: Record<string, number> | null; users: Record<string, number> | null };
export type DevicePoint = { date: string; device_platforms?: DevicePlatforms; partial?: boolean };
export type CurrentDevicePoint = DevicePoint & { partial: true; updated_at: string; device_platforms: { connections: Record<string, number>; users: Record<string, number> } };
export type AnalyticsPoint = {
  date: string; complete: boolean; dau: Count; wau: Count; mau: Count;
  new_accounts: number | null; verified_sessions: number | null; connection_success_percent: number | null;
  settled_attempts: number | null; pending_attempts: number | null;
  median_connection_seconds: number | null; engagement_percent: number | null;
  mean_session_seconds?: number | null; completed_sessions?: number;
  device_platforms?: DevicePlatforms;
};
export type Distribution = { bounds_seconds: number[]; counts: number[]; shares: (number | null)[]; samples: number };
export type AnalyticsSummary = {
  session_duration?: Distribution; time_to_silence?: Distribution;
  mean_session_seconds?: number | null; duration_unobserved_sessions?: number; silence_unobserved_sessions?: number;
};
export type LiveAnalytics = { partial: true; updated_at: string; from_date: string; point: AnalyticsPoint; summary: AnalyticsSummary };
export type Analytics = AnalyticsSummary & {
  plan?: string; duration_history?: DurationHistory;
  schema: 1; generated_at: string; next_update_at: string; from_date: string; through_date: string;
  timezone: string; observed_from: string | null; full_collection_from: string; history_partial: boolean;
  attempts_from: string | null; points: AnalyticsPoint[]; methods: Record<string, number>;
  devices?: Record<string, number>;
  device_today?: CurrentDevicePoint;
  live?: LiveAnalytics;
};
function validateDevices(devices: DevicePlatforms) {
  if (!devices || typeof devices !== "object") throw new Error("Invalid device distribution");
  for (const metric of ["connections", "users"] as const) {
    const counts = devices[metric];
    if (counts !== null && (!counts || typeof counts !== "object" || Array.isArray(counts) || !Object.values(counts).every(v => Number.isSafeInteger(v) && v >= 0))) throw new Error("Invalid device counts");
  }
  if (devices.connections === null ? devices.users !== null : Object.entries(devices.users ?? {}).some(([platform, count]) => count > (devices.connections?.[platform] ?? 0))) throw new Error("Invalid device users");
}
function validateCurrentDay(day: string, updated: string, partial: boolean, through: string) {
  if (partial !== true || !/^\d{4}-\d{2}-\d{2}$/.test(day) || day <= through || !Number.isFinite(Date.parse(updated)) || new Date(Date.parse(updated) + 3 * 3600_000).toISOString().slice(0, 10) !== day) throw new Error("Invalid current day");
}
export function readAnalytics(value: unknown): Analytics {
  if (!value || typeof value !== "object") throw new Error("Invalid analytics");
  const data = value as Analytics;
  if (data.schema !== 1 || data.timezone !== "GMT+3" || !Number.isFinite(Date.parse(data.generated_at)) || !Number.isFinite(Date.parse(data.next_update_at)) || !Array.isArray(data.points) || data.points.length > 62 || !data.points.length) throw new Error("Invalid analytics");
  const number = (v: unknown) => v === null || (typeof v === "number" && Number.isFinite(v) && v >= 0);
  let previous = "";
  for (const point of [...data.points, ...(data.live ? [data.live.point] : [])]) {
    if (!point || !/^\d{4}-\d{2}-\d{2}$/.test(point.date)) throw new Error("Invalid date");
    if (point !== data.live?.point) {
      if (point.date <= previous || point.date > data.through_date) throw new Error("Invalid date");
      previous = point.date;
    }
    for (const metric of ["mau", "wau", "dau"] as const) {
      const count = point[metric];
      if (count?.plans && count.plans.DEMO === undefined) count.plans.DEMO = count.total === null ? null : 0;
      if (!count || !number(count.total) || !count.plans || !plans.every(plan => number(count.plans[plan]))) throw new Error("Invalid count");
      if (count.total !== null && plans.reduce((sum, plan) => sum + (count.plans[plan] ?? 0), 0) !== count.total) throw new Error("Invalid cohorts");
    }
    for (const metric of ["new_accounts", "verified_sessions", "connection_success_percent", "settled_attempts", "pending_attempts", "median_connection_seconds", "engagement_percent"] as const) if (!number(point[metric])) throw new Error("Invalid metric");
    if (point.mean_session_seconds !== undefined && !number(point.mean_session_seconds)) throw new Error("Invalid duration");
    if (point.device_platforms !== undefined) {
      const devices = point.device_platforms;
      validateDevices(devices);
      if (devices.connections !== null && Object.values(devices.connections).reduce((sum, count) => sum + count, 0) !== point.verified_sessions) throw new Error("Invalid device connections");
    }
  }
  if (data.points[0].date !== data.from_date || previous !== data.through_date) throw new Error("Invalid period");
  if (data.device_today !== undefined) {
    const today = data.device_today;
    if (!today) throw new Error("Invalid current device day");
    validateCurrentDay(today.date, today.updated_at, today.partial, data.through_date);
    validateDevices(today.device_platforms);
    if (today.device_platforms.connections === null || today.device_platforms.users === null) throw new Error("Invalid current device counts");
  }
  if (data.live !== undefined) {
    const live = data.live;
    if (!live || !live.point || !live.summary || !/^\d{4}-\d{2}-\d{2}$/.test(live.from_date) || live.from_date > live.point.date) throw new Error("Invalid live analytics");
    validateCurrentDay(live.point.date, live.updated_at, live.partial, data.through_date);
    for (const key of ["session_duration", "time_to_silence"] as const) {
      const dist = live.summary[key];
      if (!dist || JSON.stringify(dist.bounds_seconds) !== "[10,60,180,300,900]" || !Array.isArray(dist.counts) || dist.counts.length !== 6 || !dist.counts.every(n => Number.isSafeInteger(n) && n >= 0) || dist.counts.reduce((sum, n) => sum + n, 0) !== dist.samples) throw new Error("Invalid live distribution");
    }
    for (const key of ["mean_session_seconds", "duration_unobserved_sessions", "silence_unobserved_sessions"] as const) if (!number(live.summary[key])) throw new Error("Invalid live summary");
  }
  if (data.duration_history !== undefined) {
    readDurationHistory(data.duration_history);
    if (data.duration_history.plan !== (data.plan ?? "ALL")) throw new Error("Wrong duration tariff");
  }
  return data;
}
export function analyticsChartPoints(data: Analytics): AnalyticsPoint[] {
  if (!data.live) return data.points;
  const today = data.live.point, end = Date.parse(today.date), day = 86400_000;
  const start = Math.max(Date.parse(data.from_date), end - 62 * day);
  const history = new Map(data.points.map(point => [point.date, point]));
  const missing = { total: null, complete: false, plans: Object.fromEntries(plans.map(plan => [plan, null])) as Count["plans"] };
  return Array.from({ length: Math.round((end - start) / day) + 1 }, (_, i) => {
    const date = new Date(start + i * day).toISOString().slice(0, 10);
    return date === today.date ? today : history.get(date) ?? { date, complete: false, dau: missing, wau: missing, mau: missing, new_accounts: null, verified_sessions: null, connection_success_percent: null, settled_attempts: null, pending_attempts: null, median_connection_seconds: null, engagement_percent: null };
  });
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
