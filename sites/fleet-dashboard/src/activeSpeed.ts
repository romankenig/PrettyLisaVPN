import { date, TIME_ZONE_LABEL } from "./time.ts";

export type SpeedDirection = {
  mean_mbps: number | null; median_mbps: number | null; active_users: number;
  bytes: number; active_seconds: number; reference_mbps: number | null;
  reference_percent: number | null; reference_servers: number;
};
export type SpeedPoint = {
  at: string; duration_seconds?: number; download: SpeedDirection; upload: SpeedDirection;
  coverage: { expected_servers: number; complete_servers: number; reporting_servers: number; fraction: number | null; server_seconds: Record<string, number> };
};
export type SpeedHistory = {
  generated_at: string; activity_threshold_bps: number; bucket_seconds: number;
  period: string; nodes: { id: string; name: string }[]; points: SpeedPoint[];
};
export const speedNumber = (value: number | null | undefined, maximumFractionDigits = 3) => value == null || !Number.isFinite(value) ? "—" : new Intl.NumberFormat("ru-RU", { maximumFractionDigits }).format(value);

export function speedSamples(points: SpeedPoint[], direction: "download" | "upload", metric: "mean_mbps" | "reference_mbps") {
  return points.flatMap((point, index) => {
    const value = point[direction][metric];
    return value == null || !Number.isFinite(value) ? [] : [{ index, value }];
  });
}

export function speedScaleMaximum(points: SpeedPoint[], direction: "download" | "upload", actualOnly = false) {
  const metrics = actualOnly ? ["mean_mbps"] as const : ["mean_mbps", "reference_mbps"] as const;
  return metrics.reduce((maximum, metric) => speedSamples(points, direction, metric)
    .reduce((current, sample) => Math.max(current, sample.value), maximum), 0.1) * 1.1;
}

export function parseSpeedMaximum(input: string): number | null {
  const value = Number(input.trim().replace(",", "."));
  return Number.isFinite(value) && value >= 0.001 ? value : null;
}

export function speedTooltip(point: SpeedPoint, seconds: number): string[] {
  const coverage = point.coverage;
  return [
    `${date(point.at)} ${TIME_ZONE_LABEL} · интервал ${(point.duration_seconds ?? seconds) / 60} мин`,
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
