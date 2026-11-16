import { readSelectionHistory, type SelectionHistory } from "./selectionHistory.ts";
const names: Record<string, string> = {
  wireguard: "WireGuard", amneziawg: "AmneziaWG", sstp: "SSTP", softether: "SoftEther",
  vless_reality: "VLESS Reality", vless: "VLESS TLS", vmess: "VMess TLS",
  shadowsocks2022: "Shadowsocks 2022", hysteria: "Hysteria", hysteria2: "Hysteria 2",
  hysteria2_salamander: "Hysteria 2 Salamander", https_proxy: "HTTPS proxy", UNKNOWN: "UNKNOWN",
};
export function methodName(id: string): string {
  const relay = id.endsWith("_relay");
  const base = relay ? id.slice(0, -6) : id;
  return (names[base] ?? base) + (relay ? "+" : "");
}
export type MethodAssessment = { id: string; points: { date: string; score: number | null }[]; week_score: number | null; observed_days: number; today_score: number | null; today_code: string | null; next_check_at: string };
export type MethodReport = { generated_at: string; methods: MethodAssessment[]; selection_history?: SelectionHistory; selection: { active_sessions: number; items: { method: string; count: number; share: number }[] } };
export function readMethodReport(value: unknown): MethodReport {
  const data = value as MethodReport;
  const score = (v: unknown) => v === null || (typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= 100);
  if (!data || !Number.isFinite(Date.parse(data.generated_at)) || !Array.isArray(data.methods) || !data.selection || !Array.isArray(data.selection.items)) throw new Error("Invalid method report");
  const ids = new Set<string>();
  for (const row of data.methods) {
    if (typeof row.id !== "string" || ids.has(row.id) || !Array.isArray(row.points) || row.points.length !== 7 || !score(row.week_score) || !score(row.today_score) || !Number.isFinite(Date.parse(row.next_check_at))) throw new Error("Invalid method assessment");
    ids.add(row.id);
    let previous = "";
    for (const point of row.points) {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(point.date) || point.date <= previous || !score(point.score)) throw new Error("Invalid daily point");
      previous = point.date;
    }
    if (row.observed_days !== row.points.filter(point => point.score !== null).length) throw new Error("Invalid coverage");
  }
  const total = data.selection.items.reduce((sum, row) => {
    if (typeof row.method !== "string" || !Number.isSafeInteger(row.count) || row.count <= 0 || !score(row.share)) throw new Error("Invalid distribution");
    return sum + row.count;
  }, 0);
  if (total !== data.selection.active_sessions || data.selection.items.some(row => Math.abs(row.share - 100 * row.count / total) > .001)) throw new Error("Invalid shares");
  if (data.selection_history !== undefined) readSelectionHistory(data.selection_history);
  return data;
}
