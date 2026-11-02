export const plans = ["FREE", "PREMIUM", "PLATINUM", "UNKNOWN"] as const;
export type Plan = typeof plans[number];
export type ActiveMetric = "dau" | "wau" | "mau";
export type Count = { total: number | null; plans: Record<Plan, number | null>; complete: boolean };
export type AnalyticsPoint = {
  date: string; complete: boolean; dau: Count; wau: Count; mau: Count;
  new_accounts: number; verified_sessions: number | null; connection_success_percent: number | null;
  settled_attempts: number | null; pending_attempts: number | null;
  median_connection_seconds: number | null; engagement_percent: number | null;
};
export type Analytics = {
  schema: 1; generated_at: string; next_update_at: string; from_date: string; through_date: string;
  timezone: string; observed_from: string | null; full_collection_from: string; history_partial: boolean;
  attempts_from: string | null; points: AnalyticsPoint[]; methods: Record<string, number>;
};
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
      if (!count || !number(count.total) || !count.plans || !plans.every(plan => number(count.plans[plan]))) throw new Error("Invalid count");
      if (count.total !== null && plans.reduce((sum, plan) => sum + (count.plans[plan] ?? 0), 0) !== count.total) throw new Error("Invalid cohorts");
    }
    for (const metric of ["new_accounts", "verified_sessions", "connection_success_percent", "settled_attempts", "pending_attempts", "median_connection_seconds", "engagement_percent"] as const) if (!number(point[metric])) throw new Error("Invalid metric");
  }
  if (data.points[0].date !== data.from_date || previous !== data.through_date) throw new Error("Invalid period");
  return data;
}
export const formatNumber = (value: number | null | undefined) => value == null ? "—" : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(value);
export const formatDay = (value: string) => new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(value + "T00:00:00Z"));
export type Series = { name: string; color: string; values: (number | null)[]; dashed?: boolean };
export function segments(values: (number | null)[]): { index: number; value: number }[][] {
  const result: { index: number; value: number }[][] = [];
  let current: { index: number; value: number }[] = [];
  values.forEach((value, index) => { if (value == null) { if (current.length) result.push(current); current = []; } else current.push({ index, value }); });
  if (current.length) result.push(current);
  return result;
}
