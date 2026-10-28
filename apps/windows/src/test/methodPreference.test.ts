import { expect, it, vi } from "vitest";
import { createVpnConnectionManager } from "../vpn/connection";
import { createMethodPreference } from "../vpn/methodPreference";
import type { ConnectionAdapter, ConnectionResult } from "../vpn/protocol";

const selection = { mode: "COUNTRY", country_code: "DE" } as const;
const verified: ConnectionResult = {
  connected: true,
  internetVerified: true,
  details: {
    protocol: "test",
    transport: "test",
    server: "test",
    encryption: "test",
    obfuscation: "none",
  },
};
function storage(initial: string | null = null) {
  let saved = initial;
  return {
    getItem: vi.fn(() => saved),
    setItem: vi.fn((_key: string, value: string) => {
      saved = value;
    }),
  };
}
function adapters(
  calls: string[],
  works: Record<string, boolean>,
): ConnectionAdapter[] {
  return ["wireguard", "wireguard_relay", "other"].map((id) => ({
    id,
    name: id,
    async connect() {
      calls.push(id);
      return works[id] ? verified : { connected: false };
    },
    async disconnect() {
      calls.push(`stop-${id}`);
    },
  }));
}

it("persists verified success across manager recreation, then falls back once in stable order", async () => {
  const saved = storage(),
    calls: string[] = [];
  const works = { wireguard: false, wireguard_relay: true, other: false };
  const first = createVpnConnectionManager(
    adapters(calls, works),
    createMethodPreference(saved),
  );
  await first.connect("", selection);
  expect(calls).toEqual(["wireguard", "stop-wireguard", "wireguard_relay"]);
  expect(saved.getItem()).toBe("wireguard_relay");
  await first.disconnect("");
  calls.length = 0;
  works.wireguard_relay = false;
  works.other = true;
  const restarted = createVpnConnectionManager(
    adapters(calls, works),
    createMethodPreference(saved),
  );
  await restarted.connect("", selection);
  expect(calls).toEqual([
    "wireguard_relay",
    "stop-wireguard_relay",
    "wireguard",
    "stop-wireguard",
    "other",
  ]);
  expect(saved.getItem()).toBe("other");
  await restarted.disconnect("");
});

it.each([null, "removed_method", "invalid stored value"])(
  "uses the default order for %s without saving failures",
  async (initial) => {
    const saved = storage(initial),
      calls: string[] = [];
    const manager = createVpnConnectionManager(
      adapters(calls, {}),
      createMethodPreference(saved),
    );
    await manager.connect("", selection);
    expect(calls.filter((id) => !id.startsWith("stop-"))).toEqual([
      "wireguard",
      "wireguard_relay",
      "other",
    ]);
    expect(saved.setItem).not.toHaveBeenCalled();
  },
);

it("never remembers a late success after cancellation", async () => {
  const saved = storage("wireguard_relay");
  let finish!: (result: ConnectionResult) => void;
  const adapter: ConnectionAdapter = {
    id: "wireguard",
    name: "WireGuard",
    connect: () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
    disconnect: vi.fn(async () => {}),
  };
  const manager = createVpnConnectionManager(
    [adapter],
    createMethodPreference(saved),
  );
  const connecting = manager.connect("", selection);
  const stopping = manager.disconnect("");
  finish(verified);
  await Promise.all([connecting, stopping]);
  expect(saved.setItem).not.toHaveBeenCalled();
  expect(manager.current().phase).toBe("DISCONNECTED");
});

it("does not count an unverified tunnel as a successful preference", async () => {
  const saved = storage();
  const adapter: ConnectionAdapter = {
    id: "wireguard",
    name: "WireGuard",
    connect: async () =>
      ({ ...verified, internetVerified: false }) as unknown as ConnectionResult,
    disconnect: async () => {},
  };
  const manager = createVpnConnectionManager(
    [adapter],
    createMethodPreference(saved),
  );
  await manager.connect("", selection);
  expect(saved.setItem).not.toHaveBeenCalled();
  expect(manager.current().phase).toBe("FAILED");
});

it("keeps a working connection and in-memory choice when local storage fails", async () => {
  const saved = {
    getItem() {
      throw Error("unavailable");
    },
    setItem() {
      throw Error("unavailable");
    },
  };
  const preference = createMethodPreference(saved);
  const manager = createVpnConnectionManager(
    adapters([], { wireguard: true }),
    preference,
  );
  await manager.connect("", selection);
  expect(manager.current().phase).toBe("CONNECTED");
  expect(preference.current()).toBe("wireguard");
  await manager.disconnect("");
});
