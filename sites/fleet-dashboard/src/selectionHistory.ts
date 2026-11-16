import type { Series } from "./analytics.ts";

export type SelectionDay = { date: string; partial: boolean; complete: boolean; counts: Record<string, number> | null; total: number | null; active_sessions: number; observed_sessions: number; unknown_mode_sessions: number; uncertain_sessions: number };
export type SelectionHistory = { timezone: "GMT+3"; generated_at: string; from_date: string; through_date: string; observed_from: string | null; categories: { id: string; name: string }[]; points: SelectionDay[] };
export function readSelectionHistory(value: unknown): SelectionHistory {
  const data = value as SelectionHistory;
  if (!data || data.timezone !== "GMT+3" || !Number.isFinite(Date.parse(data.generated_at)) || !Array.isArray(data.categories) || !Array.isArray(data.points) || data.points.length !== 8) throw new Error("Invalid selection history");
  const ids = new Set<string>();
  for (const row of data.categories) {
    if (!row || typeof row.id !== "string" || !row.id || typeof row.name !== "string" || ids.has(row.id)) throw new Error("Invalid categories");
    ids.add(row.id);
  }
  let previous: number | undefined;
  for (const [i, point] of data.points.entries()) {
    if (!point || !/^\d{4}-\d{2}-\d{2}$/.test(point.date) || !Number.isFinite(Date.parse(point.date)) || (previous !== undefined && Date.parse(point.date) - previous !== 86400_000) || point.partial !== (i === 7) || typeof point.complete !== "boolean") throw new Error("Invalid day");
    previous = Date.parse(point.date);
    for (const field of ["active_sessions", "observed_sessions", "unknown_mode_sessions", "uncertain_sessions"] as const) if (!Number.isSafeInteger(point[field]) || point[field] < 0) throw new Error("Invalid coverage");
    if (point.observed_sessions > point.active_sessions) throw new Error("Invalid coverage");
    if (point.counts === null) {
      if (point.total !== null) throw new Error("Invalid missing total");
    } else {
      if (!point.counts || typeof point.counts !== "object" || Array.isArray(point.counts) || !Object.entries(point.counts).every(([id, n]) => ids.has(id) && Number.isSafeInteger(n) && n >= 0) || Object.values(point.counts).reduce((sum, n) => sum + n, 0) !== point.total) throw new Error("Invalid daily counts");
    }
  }
  if (data.from_date !== data.points[0].date || data.through_date !== data.points[7].date || new Date(Date.parse(data.generated_at) + 3 * 3600_000).toISOString().slice(0, 10) !== data.through_date) throw new Error("Invalid period");
  return data;
}
const palette = ["#5f22d9", "#17655c", "#ac73ff", "#2c016d", "#51d6ca", "#b28a09", "#6877aa", "#9c9c9c"];
export function selectionSeries(history: SelectionHistory, shares: boolean, name: (id: string, label: string) => string): Series[] {
  return history.categories.map(row => ({
    name: name(row.id, row.name),
    color: row.id === "UNKNOWN" ? "#9c9c9c" : palette[[...row.id].reduce((sum, char) => (sum * 31 + char.charCodeAt(0)) >>> 0, 0) % palette.length],
    values: history.points.map(point => point.counts === null || (shares && !point.total) ? null : shares ? 100 * (point.counts[row.id] ?? 0) / point.total! : point.counts[row.id] ?? 0),
  }));
}
