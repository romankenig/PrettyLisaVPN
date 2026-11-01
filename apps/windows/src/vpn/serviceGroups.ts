import type { TrafficService, TrafficMode } from "./traffic";

export function serviceGroups(
  services: TrafficService[],
  mode: TrafficMode,
  language: string,
) {
  const collator = new Intl.Collator(language, {
    sensitivity: "base",
    numeric: true,
  });
  const all = [...services].sort(
    (a, b) => collator.compare(a.name, b.name) || a.id.localeCompare(b.id),
  );
  const category =
    mode === "exclude" && language === "ru" ? "whitelist" : "popular";
  const top = all
    .filter((service) => (service.category ?? "popular") === category)
    .sort(
      (a, b) =>
        (a.popularity_rank ?? 1001) - (b.popularity_rank ?? 1001) ||
        collator.compare(a.name, b.name),
    )
    .slice(0, 10);
  return [
    { key: "top", title: "Топ-10 популярных", services: top },
    { key: "all", title: "Все сервисы", services: all },
  ];
}
