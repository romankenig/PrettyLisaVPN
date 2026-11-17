import type { Distribution, Series } from "./analytics";
import { reportPlans, type ReportPlan } from "./reportPlan.ts";

export const durationLabels = ["≤10 с", "10–60 с", "1–3 мин", "3–5 мин", "5–15 мин", ">15 мин"];
export type DurationKind = "session_duration" | "time_to_silence";
export type DurationDay = { date: string; partial: boolean; sessions: number | null; session_duration: Distribution | null; time_to_silence: Distribution | null; duration_unobserved_sessions: number | null; silence_unobserved_sessions: number | null };
export type DurationHistory = { timezone: "GMT+3"; plan: ReportPlan; generated_at: string; observed_from: string; from_date: string; through_date: string; points: DurationDay[] };
export function readDurationHistory(value: unknown): DurationHistory {
  const data = value as DurationHistory;
  if (!data || data.timezone !== "GMT+3" || !reportPlans.includes(data.plan) || !Number.isFinite(Date.parse(data.generated_at)) || !Number.isFinite(Date.parse(data.observed_from)) || !Array.isArray(data.points) || data.points.length < 1 || data.points.length > 63) throw new Error("Invalid duration history");
  let previous: number | undefined;
  for (const [i, p] of data.points.entries()) {
    if (!p || !/^\d{4}-\d{2}-\d{2}$/.test(p.date) || !Number.isFinite(Date.parse(p.date)) || (previous !== undefined && Date.parse(p.date) - previous !== 86400_000) || p.partial !== (i === data.points.length - 1)) throw new Error("Invalid duration date");
    previous = Date.parse(p.date);
    if (p.sessions !== null && (!Number.isSafeInteger(p.sessions) || p.sessions < 0)) throw new Error("Invalid sessions");
    for (const kind of ["session_duration", "time_to_silence"] as const) {
      const dist = p[kind], missing = unobserved(p, kind);
      if (p.sessions === null) { if (dist !== null || missing !== null) throw new Error("Invalid missing duration"); continue; }
      if (!dist || JSON.stringify(dist.bounds_seconds) !== "[10,60,180,300,900]" || !Array.isArray(dist.counts) || dist.counts.length !== 6 || !dist.counts.every(n => Number.isSafeInteger(n) && n >= 0) || dist.counts.reduce((a,b)=>a+b,0) !== dist.samples || !Number.isSafeInteger(missing) || missing! < 0 || dist.samples + missing! !== p.sessions || !Array.isArray(dist.shares) || dist.shares.length !== 6 || dist.shares.some((n,j) => dist.samples ? typeof n !== "number" || !Number.isFinite(n) || Math.abs(n-100*dist.counts[j]/dist.samples)>.001 : n !== null)) throw new Error("Invalid daily duration");
    }
  }
  if (data.from_date !== data.points[0].date || data.through_date !== data.points.at(-1)!.date || new Date(Date.parse(data.generated_at)+3*3600_000).toISOString().slice(0,10) !== data.through_date) throw new Error("Invalid duration period");
  return data;
}
export function unobserved(point: DurationDay, kind: DurationKind): number | null { return point[kind === "session_duration" ? "duration_unobserved_sessions" : "silence_unobserved_sessions"]; }
const colors = ["#17655c", "#51d6ca", "#377aa0", "#5f22d9", "#ac73ff", "#2c016d"];
export function durationSeries(data: DurationHistory, kind: DurationKind, shares: boolean): Series[] {
  return durationLabels.map((name,i)=>({name,color:colors[i],values:data.points.map(p=>p[kind] === null ? null : shares ? p[kind]!.shares[i] : p[kind]!.counts[i])}));
}
