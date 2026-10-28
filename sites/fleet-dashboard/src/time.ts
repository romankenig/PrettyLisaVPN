export const TIME_ZONE_LABEL = "GMT+3";
export const TIME_ZONE = "Etc/GMT-3";

export function date(value: string | null, time = true): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit", month: "short",
    ...(time ? { hour: "2-digit", minute: "2-digit" } : {}),
    timeZone: TIME_ZONE,
  }).format(new Date(value));
}

export function clock(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit", minute: "2-digit", timeZone: TIME_ZONE,
  }).format(new Date(value));
}
