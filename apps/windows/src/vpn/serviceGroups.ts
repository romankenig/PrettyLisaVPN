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
  const all = [
    ...new Map(services.map((service) => [service.id, service])).values(),
  ].sort(
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
  const popular = new Set(top.map((service) => service.id));
  return [
    {
      key: "selected",
      title: "Выбранные сервисы",
      services: all.filter((service) => selected.has(service.id)),
    },
    {
      key: "top",
      title: "Популярные",
      services: top.filter((service) => !selected.has(service.id)),
    },
    {
      key: "all",
      title: "Остальные сервисы",
      services: all.filter(
        (service) => !selected.has(service.id) && !popular.has(service.id),
      ),
    },
  ];
}
