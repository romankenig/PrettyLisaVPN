import { describe, expect, it } from "vitest";
import {
  createTrafficSelection,
  emptyTraffic,
  normalizeMask,
  parseTrafficCatalog,
  routingPolicy,
  refreshServices,
} from "../vpn/traffic";

describe("device traffic rules", () => {
  it("refreshes selected preset masks only on explicit save and preserves offline choices", () => {
    const old = {
      id: "0bd811da-f080-4f25-887a-67bf534ac2c6",
      slug: "youtube",
      name: "YouTube",
      icon: "youtube",
      domains: ["youtube.com"],
    };
    const updated = { ...old, domains: ["youtube.com", "*.googlevideo.com"] };
    const value = {
      ...emptyTraffic(),
      include: { services: [old], masks: ["manual.example.com"] },
    };
    expect(refreshServices(value, []).include.services).toEqual([old]);
    expect(refreshServices(value, [updated]).include.services).toEqual([
      updated,
    ]);
    expect(value.include.services).toEqual([old]);
    expect(refreshServices(value, [updated]).exclude).toEqual(
      emptyTraffic().exclude,
    );
    expect(refreshServices(value, [updated]).include.masks).toEqual([
      "manual.example.com",
    ]);
  });
  it("normalizes exact and subdomain masks independently", () => {
    expect(normalizeMask(" YouTube.com ")).toBe("youtube.com");
    expect(normalizeMask("*.YouTube.com")).toBe("*.youtube.com");
    expect(normalizeMask("пример.рф")).toBe("xn--e1afmkfd.xn--p1ai");
    for (const mask of [
      "https://a.com",
      "a.com/path",
      "a.com:443",
      "a.*.com",
      "*.com",
      "127.0.0.1",
      "a..com",
      "-a.com",
    ])
      expect(() => normalizeMask(mask)).toThrow();
  });
  it("persists two independent lists and compiles only the active one", () => {
    const memory = new Map<string, string>();
    const storage = {
      getItem: (key: string) => memory.get(key) ?? null,
      setItem: (key: string, value: string) => {
        memory.set(key, value);
      },
    };
    const store = createTrafficSelection(storage);
    const selected = {
      ...emptyTraffic(),
      mode: "include" as const,
      include: { services: [], masks: ["youtube.com", "*.youtube.com"] },
      exclude: { services: [], masks: ["instagram.com"] },
    };
    store.save(selected);
    expect(createTrafficSelection(storage).current()).toEqual(selected);
    expect(routingPolicy(selected).domains).toEqual([
      "youtube.com",
      "*.youtube.com",
    ]);
    expect(routingPolicy({ ...selected, mode: "exclude" }).domains).toEqual([
      "instagram.com",
    ]);
    expect(routingPolicy({ ...selected, mode: "all" }).domains).toEqual([]);
  });
  it("rejects invalid catalog masks and bounds the compiled union", () => {
    expect(() => parseTrafficCatalog({ services: [{ id: "bad" }] })).toThrow();
    expect(() =>
      routingPolicy({
        ...emptyTraffic(),
        mode: "include",
        include: {
          services: [],
          masks: Array.from({ length: 257 }, (_, i) => `s${i}.example.com`),
        },
      }),
    ).toThrow();
  });
});
