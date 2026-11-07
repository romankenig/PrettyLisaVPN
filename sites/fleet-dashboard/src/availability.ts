export const availabilityStates = ["HEALTHY", "DEGRADED", "FAILED", "UNKNOWN", "PENDING", "NOT_REGISTERED"] as const;
export type AvailabilityStatus = typeof availabilityStates[number];
export type AvailabilityHour = { at: string; status: AvailabilityStatus; modes: string[]; checks: number };
export type CombinedHour = AvailabilityHour & { counts: Record<AvailabilityStatus, number> };

export const availabilityNames: Record<AvailabilityStatus, string> = {
  HEALTHY: "Доступен", DEGRADED: "С ограничениями", FAILED: "Сбой",
  UNKNOWN: "Нет подтверждения", PENDING: "Ожидается проверка", NOT_REGISTERED: "Узел ещё не добавлен",
};
const colors: Record<AvailabilityStatus, string> = {
  HEALTHY: "#51d6ca", DEGRADED: "#d7ad0d", FAILED: "#c82b28",
  UNKNOWN: "#b7aec9", PENDING: "#e5def0", NOT_REGISTERED: "#eeeef2",
};

export function combineAvailability(nodes: { history: AvailabilityHour[] }[]): CombinedHour[] {
  // Match actual UTC hours, not array positions; a gap is unknown, never another hour's result.
  const histories = nodes.map(node => new Map(node.history.map(hour => [Date.parse(hour.at), hour])));
  const times = [...new Set(histories.flatMap(history => [...history.keys()]))].filter(Number.isFinite).sort((a, b) => a - b);
  return times.map(time => {
    const values = histories.map(history => history.get(time));
    const counts = Object.fromEntries(availabilityStates.map(status => [status, 0])) as Record<AvailabilityStatus, number>;
    for (const hour of values) counts[hour?.status ?? "UNKNOWN"]++;
    const status = (["FAILED", "DEGRADED", "UNKNOWN", "PENDING", "HEALTHY"] as const).find(value => counts[value] > 0) ?? "NOT_REGISTERED";
    return {
      at: new Date(time).toISOString(), status, counts,
      checks: values.reduce((sum, hour) => sum + (hour?.checks ?? 0), 0),
      modes: [...new Set(values.flatMap(hour => hour?.modes ?? []))],
    };
  });
}

export function availabilityFill(hour: AvailabilityHour | CombinedHour): string | undefined {
  if (!("counts" in hour)) return undefined;
  // Servers which did not yet exist cannot dilute a real outage or inflate availability.
  const states = availabilityStates.filter(status => status !== "NOT_REGISTERED" && hour.counts[status] > 0);
  const total = states.reduce((sum, status) => sum + hour.counts[status], 0);
  if (!total) return colors.NOT_REGISTERED;
  if (states.length === 1) return colors[states[0]];
  let position = 0;
  const stops = states.map(status => {
    const start = position;
    position += 100 * hour.counts[status] / total;
    return `${colors[status]} ${start.toFixed(3)}% ${position.toFixed(3)}%`;
  });
  return `linear-gradient(to top, ${stops.join(", ")})`;
}

export function availabilityDescription(hour: AvailabilityHour | CombinedHour): string {
  if (!("counts" in hour)) return availabilityNames[hour.status];
  const registered = availabilityStates.filter(status => status !== "NOT_REGISTERED").reduce((sum, status) => sum + hour.counts[status], 0);
  return availabilityStates.filter(status => hour.counts[status] > 0).map(status => {
    const count = hour.counts[status];
    return status === "NOT_REGISTERED" ? `${availabilityNames[status]}: ${count}` : `${availabilityNames[status]}: ${count} из ${registered}`;
  }).join(" · ");
}
