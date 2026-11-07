import { date, TIME_ZONE_LABEL } from "./time.ts";

export type SpeedDirection = {
  mean_mbps: number | null; median_mbps: number | null; active_users: number;
  bytes: number; active_seconds: number; reference_mbps: number | null;
  reference_percent: number | null; reference_servers: number;
};
export type SpeedPoint = {
  at: string; download: SpeedDirection; upload: SpeedDirection;
  coverage: { expected_servers: number; complete_servers: number; reporting_servers: number; fraction: number | null; server_seconds: Record<string, number> };
};
export type SpeedHistory = {
  generated_at: string; activity_threshold_bps: number; bucket_seconds: number;
  period: string; nodes: { id: string; name: string }[]; points: SpeedPoint[];
};
export const speedNumber = (value: number | null | undefined) => value == null || !Number.isFinite(value) ? "—" : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 3 }).format(value);

export function speedSegments(points: SpeedPoint[], direction: "download" | "upload", metric: "mean_mbps" | "reference_mbps") {
  const segments: { index: number; value: number }[][] = [];
  let segment: { index: number; value: number }[] = [];
  points.forEach((point, index) => {
    const value = point[direction][metric];
    if (value == null || !Number.isFinite(value)) { segment = []; return; }
    if (!segment.length) { segment = []; segments.push(segment); }
    segment.push({ index, value });
  });
  return segments;
}

export function speedTooltip(point: SpeedPoint, seconds: number): string[] {
  const coverage = point.coverage;
  return [
    `${date(point.at)} ${TIME_ZONE_LABEL} · интервал ${seconds / 60} мин`,
    ...(["download", "upload"] as const).map(direction => {
      const value = point[direction];
      return `${direction === "download" ? "↓ Скачивание" : "↑ Загрузка"}: средняя ${speedNumber(value.mean_mbps)}, медиана ${speedNumber(value.median_mbps)} Мбит/с · активных пользователей ${value.active_users}`;
    }),
    ...(["download", "upload"] as const).map(direction => {
      const value = point[direction];
      return `${direction === "download" ? "↓" : "↑"} Ориентир проверки: ${speedNumber(value.reference_mbps)} Мбит/с (${value.reference_servers}/${coverage.expected_servers} серверов) · отношение средней: ${speedNumber(value.reference_percent)}${value.reference_percent == null ? "" : "%"}`;
    }),
    `Полнота: ${speedNumber(coverage.fraction == null ? null : coverage.fraction * 100)}% времени серверов · полностью ${coverage.complete_servers}/${coverage.expected_servers}, частично или полностью ${coverage.reporting_servers}/${coverage.expected_servers}`,
  ];
}
