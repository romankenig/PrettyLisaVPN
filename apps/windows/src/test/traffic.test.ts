import { describe, expect, it } from "vitest";
import {
  createTrafficSelection,
  emptyTraffic,
  normalizeMask,
  parseTrafficCatalog,
  routingPolicy,
  refreshServices,
  normalizeServiceNetwork,
} from "../vpn/traffic";

describe("device traffic rules", () => {
  it("keeps service IP networks separate from manual domains and inverse lists", () => {
    const service = {
      id: "6cbb9213-108e-5bf7-b4f9-5f10a42d2b0c",
      slug: "telegram",
      name: "Telegram",
      icon: "telegram",
      domains: ["telegram.org"],
      ipv4_cidrs: ["91.108.4.0/22"],
    };
    const value = {
      ...emptyTraffic(),
      mode: "include" as const,
      include: { services: [service], masks: ["example.com"] },
    };
    expect(routingPolicy(value)).toEqual({
      mode: "include",
      domains: ["example.com", "telegram.org"],
      ipv4_cidrs: ["91.108.4.0/22"],
    });
    expect(
      routingPolicy({ ...value, mode: "exclude" }).ipv4_cidrs,
    ).toBeUndefined();
    expect(routingPolicy({ ...value, mode: "all" }).ipv4_cidrs).toBeUndefined();
    expect(() => normalizeMask("91.108.4.0/22")).toThrow();
    const memory = new Map<string, string>();
    const storage = {
      getItem: (key: string) => memory.get(key) ?? null,
      setItem: (key: string, v: string) => {
        memory.set(key, v);
      },
    };
    createTrafficSelection(storage).save(value);
    expect(
      routingPolicy(createTrafficSelection(storage).current()).ipv4_cidrs,
    ).toEqual(service.ipv4_cidrs);
    for (const cidr of [
      "91.108.4.1/22",
      "91.108.4.0",
      "091.108.4.0/22",
      "0.0.0.0/0",
      "127.0.0.1/32",
      "10.0.0.0/8",
      "100.64.0.0/10",
      "198.18.0.0/15",
      "198.0.0.0/8",
      "224.0.0.0/4",
      "2001:b28:f23d::/48",
    ])
      expect(() => normalizeServiceNetwork(cidr)).toThrow();
    expect(() =>
      parseTrafficCatalog({
        services: [{ ...service, ipv4_cidrs: Array(65).fill("91.108.4.0/22") }],
      }),
    ).toThrow();
  });
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
