export type TrafficMode = "all" | "include" | "exclude";
export interface TrafficService {
  id: string;
  slug: string;
  name: string;
  icon: string;
  domains: string[];
  category?: "popular" | "whitelist";
}
export interface TrafficList {
  services: TrafficService[];
  masks: string[];
}
export interface TrafficSelection {
  mode: TrafficMode;
  include: TrafficList;
  exclude: TrafficList;
}
export interface RoutingPolicy {
  mode: TrafficMode;
  domains: string[];
}
export function refreshServices(
  value: TrafficSelection,
  catalog: TrafficService[],
): TrafficSelection {
  const refresh = (list: TrafficList): TrafficList => ({
    ...list,
    services: list.services.map(
      (saved) => catalog.find((s) => s.id === saved.id) ?? saved,
    ),
  });
  return {
    ...value,
    include: refresh(value.include),
    exclude: refresh(value.exclude),
  };
}
const KEY = "prettylisavpn:traffic:v1";
export const emptyTraffic = (): TrafficSelection => ({
  mode: "all",
  include: { services: [], masks: [] },
  exclude: { services: [], masks: [] },
});

export function normalizeMask(input: string): string {
  const raw = input.trim().toLowerCase();
  const wildcard = raw.startsWith("*.");
  const value = wildcard ? raw.slice(2) : raw;
  if (!value || /[\s/:@?#\\*%]/u.test(value)) throw new Error("INVALID_MASK");
  const host = new URL("https://" + value).hostname;
  if (
    host.length > 253 ||
    !host.includes(".") ||
    !/[a-z]/.test(host.split(".").at(-1) ?? "") ||
    host
      .split(".")
      .some((label) => !/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label))
  )
    throw new Error("INVALID_MASK");
  return (wildcard ? "*." : "") + host;
}
export function parseTrafficCatalog(raw: unknown): TrafficService[] {
  const data = raw as { services?: TrafficService[] };
  if (!Array.isArray(data?.services) || data.services.length > 64)
    throw new Error("INVALID_CATALOG");
  const ids = new Set<string>();
  return data.services.map((s) => {
    if (
      !s ||
      (s.category != null && !["popular", "whitelist"].includes(s.category)) ||
      !/^[0-9a-f-]{36}$/.test(s.id) ||
      ids.has(s.id) ||
      !/^[a-z][a-z0-9-]{0,39}$/.test(s.slug) ||
      !/^[a-z][a-z0-9-]{0,39}$/.test(s.icon) ||
      typeof s.name !== "string" ||
      !s.name.length ||
      s.name.length > 80 ||
      !Array.isArray(s.domains) ||
      !s.domains.length ||
      s.domains.length > 64
    )
      throw new Error("INVALID_CATALOG");
    ids.add(s.id);
    return { ...s, domains: [...new Set(s.domains.map(normalizeMask))] };
  });
}
export function routingPolicy(value: TrafficSelection): RoutingPolicy {
  if (!["all", "include", "exclude"].includes(value.mode))
    throw new Error("INVALID_TRAFFIC_MODE");
  if (value.mode === "all") return { mode: "all", domains: [] };
  const list = value[value.mode];
  const domains = [
    ...new Set([
      ...list.masks.map(normalizeMask),
      ...parseTrafficCatalog({ services: list.services }).flatMap(
        (s) => s.domains,
      ),
    ]),
  ];
  if (domains.length > 256) throw new Error("TOO_MANY_MASKS");
  return { mode: value.mode, domains };
}
export function createTrafficSelection(
  storage?: Pick<Storage, "getItem" | "setItem">,
) {
  let current = emptyTraffic();
  try {
    const raw = storage?.getItem(KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as TrafficSelection;
      routingPolicy({ ...parsed, mode: "include" });
      routingPolicy({ ...parsed, mode: "exclude" });
      routingPolicy(parsed);
      current = parsed;
    }
  } catch {
    /* Invalid persisted rules never become runtime configuration. */
  }
  const listeners = new Set<() => void>();
  return {
    current: () => current,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    save(value: TrafficSelection) {
      routingPolicy({ ...value, mode: "include" });
      routingPolicy({ ...value, mode: "exclude" });
      routingPolicy(value);
      storage?.setItem(KEY, JSON.stringify(value));
      current = structuredClone(value);
      listeners.forEach((fn) => fn());
    },
  };
}
let instance: ReturnType<typeof createTrafficSelection> | undefined;
export function getDeviceTrafficSelection() {
  return (instance ??= createTrafficSelection(globalThis.localStorage));
}
