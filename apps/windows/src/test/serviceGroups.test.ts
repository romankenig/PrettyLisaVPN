import { expect, it } from "vitest";
import { serviceGroups } from "../vpn/serviceGroups";
import type { TrafficService } from "../vpn/traffic";

const catalog: TrafficService[] = Array.from({ length: 24 }, (_, index) => ({
  id: String(index),
  slug: `service-${index}`,
  name: `Service ${24 - index}`,
  icon: "website",
  domains: ["example.com"],
  category: index < 12 ? "popular" : "whitelist",
  popularity_rank: index + 1,
}));

it("partitions selected, popular and remaining services without duplicates", () => {
  for (const [mode, language] of [
    ["include", "ru"],
    ["include", "en"],
    ["exclude", "ru"],
    ["exclude", "de"],
  ] as const) {
    const selectedIds = ["0", "12", "1"];
    const [selected, top, remaining] = serviceGroups(
      catalog,
      mode,
      language,
      selectedIds,
    );
    expect(selected.services.map((s) => s.id)).toEqual(["12", "1", "0"]);
    const candidates =
      mode === "exclude" && language === "ru"
        ? catalog.slice(12, 22)
        : catalog.slice(0, 10);
    expect(top.services.map((s) => s.id)).toEqual(
      candidates.filter((s) => !selectedIds.includes(s.id)).map((s) => s.id),
    );
    expect(remaining.services.map((s) => s.name)).toEqual(
      remaining.services
        .map((s) => s.name)
        .sort(new Intl.Collator(language, { numeric: true }).compare),
    );
    const result = [selected, top, remaining].flatMap((g) =>
      g.services.map((s) => s.id),
    );
    expect(result).toHaveLength(catalog.length);
    expect(new Set(result).size).toBe(catalog.length);
  }
});
it("moves newly selected services into the first group without refilling the top ten", () => {
  const before = serviceGroups(catalog, "include", "en");
  const after = serviceGroups(catalog, "include", "en", ["0", "23"]);
  expect(before[0].services).toEqual([]);
  expect(after[0].services.map((s) => s.id)).toEqual(["23", "0"]);
  expect(after[1].services).toHaveLength(9);
  expect(after[2].services.some((s) => s.id === "23")).toBe(false);
  expect(
    serviceGroups([...catalog, catalog[0]], "include", "en").flatMap(
      (g) => g.services,
    ),
  ).toHaveLength(24);
});
