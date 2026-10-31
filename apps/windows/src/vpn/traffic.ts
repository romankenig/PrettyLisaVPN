export type TrafficMode = "all" | "include" | "exclude";
export interface TrafficService {
  id: string;
  slug: string;
  name: string;
  icon: string;
  domains: string[];
  category?: "popular" | "whitelist";
  ipv4_cidrs?: string[];
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
  ipv4_cidrs?: string[];
}
// Service-owned public networks only; manual input remains domain masks.
export function normalizeServiceNetwork(value: string): string {
  const match = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\/(\d{1,2})$/.exec(
    value,
  );
  if (!match) throw new Error("INVALID_SERVICE_NETWORK");
  const octets = match.slice(1, 5).map(Number);
  const bits = Number(match[5]);
  if (
    octets.some((n) => n > 255) ||
    bits < 8 ||
    bits > 32 ||
    `${octets.join(".")}/${bits}` !== value
  )
    throw new Error("INVALID_SERVICE_NETWORK");
  const address = octets.reduce((n, byte) => n * 256 + byte, 0);
  const size = 2 ** (32 - bits);
  if (address % size) throw new Error("INVALID_SERVICE_NETWORK");
  const end = address + size - 1;
  for (const cidr of [
    "0.0.0.0/8",
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.0.0.0/24",
    "192.0.2.0/24",
    "192.88.99.0/24",
    "192.168.0.0/16",
    "198.18.0.0/15",
    "198.51.100.0/24",
    "203.0.113.0/24",
    "224.0.0.0/3",
  ]) {
    const [ip, prefix] = cidr.split("/");
    const first = ip.split(".").reduce((n, part) => n * 256 + Number(part), 0);
    const last = first + 2 ** (32 - Number(prefix)) - 1;
    if (address <= last && end >= first)
      throw new Error("INVALID_SERVICE_NETWORK");
  }
  return value;
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
    if (
      s.ipv4_cidrs != null &&
      (!Array.isArray(s.ipv4_cidrs) || s.ipv4_cidrs.length > 64)
    )
      throw new Error("INVALID_CATALOG");
    return {
      ...s,
      domains: [...new Set(s.domains.map(normalizeMask))],
      ...(s.ipv4_cidrs == null
        ? {}
        : {
            ipv4_cidrs: [...new Set(s.ipv4_cidrs.map(normalizeServiceNetwork))],
          }),
    };
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
  const ipv4_cidrs = [
    ...new Set(
      parseTrafficCatalog({ services: list.services }).flatMap(
        (s) => s.ipv4_cidrs ?? [],
      ),
    ),
  ];
  if (ipv4_cidrs.length > 256) throw new Error("TOO_MANY_NETWORKS");
  return {
    mode: value.mode,
    domains,
    ...(ipv4_cidrs.length ? { ipv4_cidrs } : {}),
  };
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
