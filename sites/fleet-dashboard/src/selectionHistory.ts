import type { Series } from "./analytics.ts";

export type SelectionDay = { date: string; partial: boolean; complete: boolean; counts: Record<string, number> | null; total: number | null; active_sessions: number; observed_sessions: number; unknown_mode_sessions: number; uncertain_sessions: number };
export const connectionOutcomes = ["all", "successful", "unsuccessful"] as const;
export type ConnectionOutcome = typeof connectionOutcomes[number];
export const outcomeLabels: Record<ConnectionOutcome, string> = { all: "Все", successful: "Успешные", unsuccessful: "Неуспешные" };
type SelectionData = { timezone: "GMT+3"; generated_at: string; from_date: string; through_date: string; observed_from: string | null; categories: { id: string; name: string }[]; points: SelectionDay[] };
export type SelectionHistory = SelectionData & { outcomes?: Record<ConnectionOutcome, SelectionData> };
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
  if (data.outcomes !== undefined) {
    if (!data.outcomes || typeof data.outcomes !== "object") throw new Error("Invalid outcomes");
    for (const outcome of connectionOutcomes) {
      const history = data.outcomes[outcome];
      if (!history || "outcomes" in history) throw new Error("Invalid outcome history");
      readSelectionHistory(history);
      if (history.generated_at !== data.generated_at || history.from_date !== data.from_date || history.through_date !== data.through_date || JSON.stringify(history.categories) !== JSON.stringify(data.categories)) throw new Error("Inconsistent outcome history");
    }
    if (JSON.stringify(data.outcomes.successful.points) !== JSON.stringify(data.points)) throw new Error("Inconsistent successful history");
  }
  return data;
}
export function historyForOutcome(history: SelectionHistory | undefined, outcome: ConnectionOutcome): SelectionData | undefined {
  return history?.outcomes?.[outcome] ?? (outcome === "successful" ? history : undefined);
}
const palette = ["#5f22d9", "#17655c", "#ac73ff", "#2c016d", "#51d6ca", "#377aa0", "#6877aa", "#5b5b5b"];
export function categoryColors(ids: string[]): Map<string, string> {
  const colors = new Map<string, string>(), used = new Set<string>();
  for (const id of [...ids].sort()) {
    if (id === "UNKNOWN") { colors.set(id, "#9c9c9c"); continue; }
    const preferred = [...id].reduce((sum, char) => (sum * 31 + char.charCodeAt(0)) >>> 0, 0) % palette.length;
    const color = palette.map((_, offset) => palette[(preferred + offset) % palette.length]).find(candidate => !used.has(candidate))
      ?? `hsl(${(170 + used.size * 137.508) % 360} 45% 45%)`;
    colors.set(id, color); used.add(color);
  }
  return colors;
}
export function selectionSeries(history: SelectionHistory, shares: boolean, name: (id: string, label: string) => string): Series[] {
  const colors = categoryColors(history.categories.map(row => row.id));
  return history.categories.map(row => ({
    name: name(row.id, row.name),
    color: colors.get(row.id)!,
    values: history.points.map(point => point.counts === null || (shares && !point.total) ? null : shares ? 100 * (point.counts[row.id] ?? 0) / point.total! : point.counts[row.id] ?? 0),
  }));
}
