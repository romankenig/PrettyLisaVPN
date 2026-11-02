import type { TrafficService, TrafficMode } from "./traffic";

export function serviceGroups(
  services: TrafficService[],
  mode: TrafficMode,
  language: string,
  savedSelection: readonly string[] = [],
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
  const selected = new Set(savedSelection);
  const order = (a: TrafficService, b: TrafficService) =>
    Number(selected.has(b.id)) - Number(selected.has(a.id)) ||
    collator.compare(a.name, b.name) ||
    a.id.localeCompare(b.id);
  return [
    { key: "top", title: "Топ-10 популярных", services: top.sort(order) },
    { key: "all", title: "Все сервисы", services: all.sort(order) },
  ];
}
