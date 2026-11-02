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

it("promotes ten popular services in include and non-Russian exclude, then keeps the entire alphabetic catalog", () => {
  for (const [mode, language] of [
    ["include", "ru"],
    ["include", "en"],
    ["exclude", "en"],
  ] as const) {
    const [top, all] = serviceGroups(catalog, mode, language);
    expect(top.services.map((service) => service.id)).toEqual(
      catalog
        .slice(0, 10)
        .reverse()
        .map((service) => service.id),
    );
    expect(all.services).toHaveLength(24);
    expect(all.services[0].name).toBe("Service 1");
    expect(all.services.at(-1)?.name).toBe("Service 24");
  }
});

it("Russian exclude promotes the allowlist with the requested popular heading", () => {
  const [top, all] = serviceGroups(catalog, "exclude", "ru");
  expect(top.title).toBe("Топ-10 популярных");
  expect(top.services).toHaveLength(10);
  expect(
    top.services.every((service) => service.category === "whitelist"),
  ).toBe(true);
  expect(all.services).toHaveLength(24);
  expect(
    serviceGroups(
      catalog.map((service) => ({ ...service, popularity_rank: null })),
      "include",
      "de",
    )[0].services,
  ).toHaveLength(10);
});

it("sorts each block by saved selection then alphabetically without changing top membership", () => {
  const [top, all] = serviceGroups(catalog, "include", "en", ["0", "12", "1"]);
  expect(top.services.slice(0, 2).map((s) => s.id)).toEqual(["1", "0"]);
  expect(all.services.slice(0, 3).map((s) => s.id)).toEqual(["12", "1", "0"]);
  expect(new Set(top.services.map((s) => s.id))).toEqual(
    new Set(catalog.slice(0, 10).map((s) => s.id)),
  );
});
