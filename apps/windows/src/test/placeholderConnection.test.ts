import { afterEach, describe, expect, it, vi } from "vitest";
import { createVpnConnectionManager } from "../vpn/connection";
import { placeholderAdapters } from "../vpn/placeholders";
import type { ConnectionAdapter } from "../vpn/protocol";
import { attemptMessage } from "../vpn/attempt";

afterEach(() => vi.useRealTimers());
const selection = { mode: "COUNTRY", country_code: "DE" } as const;

describe("shipped placeholder connection executor", () => {
  it("calls every adapter once, in order, for three seconds each and never connects", async () => {
    vi.useFakeTimers();
    const adapters = placeholderAdapters();
    expect(adapters.map((a) => a.id)).toEqual([
      "wireguard",
      "amneziawg",
      "openvpn",
      "ipsec",
      "sstp",
      "softether",
      "openconnect",
      "shadowsocks",
      "shadowsocks2022",
      "vmess",
      "vless",
      "trojan",
      "ssh",
      "hysteria",
    ]);
    adapters.forEach((a) => vi.spyOn(a, "connect"));
    const manager = createVpnConnectionManager(adapters);
    const phases: string[] = [];
    manager.subscribe(() => phases.push(manager.current().phase));
    const done = manager.connect("not-sent-anywhere", selection);
    for (const [index, adapter] of adapters.entries()) {
      expect(manager.current()).toMatchObject({
        phase: "CONNECTING",
        attempt: {
          method: adapter.name,
          previousMethod: adapters[index - 1]?.name ?? null,
        },
      });
      expect(adapter.connect).toHaveBeenCalledExactlyOnceWith(
        selection,
        expect.any(AbortSignal),
      );
      await vi.advanceTimersByTimeAsync(2_999);
      expect(manager.current()).toMatchObject({
        phase: "CONNECTING",
        attempt: { method: adapter.name },
      });
      await vi.advanceTimersByTimeAsync(1);
    }
    await done;
    expect(manager.current()).toMatchObject({
      phase: "FAILED",
      failure_code: "METHODS_EXHAUSTED",
      attempt: { method: "Hysteria / Hysteria 2" },
    });
    expect(phases).not.toContain("CONNECTED");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("cancels a pending timer, does not advance, and restarts from WireGuard", async () => {
    vi.useFakeTimers();
    const adapters = placeholderAdapters();
    adapters.forEach((a) => vi.spyOn(a, "connect"));
    const manager = createVpnConnectionManager(adapters);
    const done = manager.connect("", selection);
    await vi.advanceTimersByTimeAsync(500);
    await manager.disconnect("");
    await done;
    await vi.advanceTimersByTimeAsync(60_000);
    expect(adapters[1].connect).not.toHaveBeenCalled();
    expect(manager.current().phase).toBe("DISCONNECTED");
    const again = manager.connect("", selection);
    expect(adapters[0].connect).toHaveBeenCalledTimes(2);
    await manager.disconnect("");
    await again;
    expect(vi.getTimerCount()).toBe(0);
  });

  it("ignores double clicks and cancels on account change or disposal", async () => {
    vi.useFakeTimers();
    const manager = createVpnConnectionManager();
    const first = manager.connect("", selection);
    await manager.connect("", selection);
    expect(vi.getTimerCount()).toBe(1);
    manager.setOwner?.("another-account");
    await first;
    await manager.disconnect("");
    expect(manager.current().phase).toBe("DISCONNECTED");
    const second = manager.connect("", selection);
    manager.dispose();
    await second;
    await manager.disconnect("");
    await manager.connect("", selection);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("continues after failure, stops on verified success and uses the adapter's details", async () => {
    const details = {
      protocol: "future",
      transport: "test",
      server: "test",
      encryption: "test",
      obfuscation: "none",
    };
    const calls: string[] = [];
    const adapter = (id: string, success: boolean): ConnectionAdapter => ({
      id,
      name: id,
      async connect() {
        calls.push(id);
        return success
          ? { connected: true, internetVerified: true, details }
          : { connected: false };
      },
      async disconnect() {
        calls.push(`stop-${id}`);
      },
    });
    const manager = createVpnConnectionManager([
      adapter("first", false),
      adapter("second", true),
      adapter("third", true),
    ]);
    await manager.connect("", selection);
    expect(calls).toEqual(["first", "stop-first", "second"]);
    expect(manager.current().phase).toBe("CONNECTED");
    expect(await manager.connectionDetails?.()).toBe(details);
    await manager.disconnect("");
    expect(calls.at(-1)).toBe("stop-second");
  });

  it("aborts fallback if cleanup fails instead of overlapping adapters", async () => {
    const next = vi.fn();
    const broken: ConnectionAdapter = {
      id: "broken",
      name: "broken",
      async connect() {
        throw Error("private detail");
      },
      async disconnect() {
        throw Error("private detail");
      },
    };
    const manager = createVpnConnectionManager([
      broken,
      { ...broken, id: "next", connect: next },
    ]);
    await manager.connect("", selection);
    expect(next).not.toHaveBeenCalled();
    expect(manager.current()).toMatchObject({
      phase: "FAILED",
      failure_code: "CLEANUP_FAILED",
    });
    expect(JSON.stringify(manager.current())).not.toContain("private detail");
  });

  it("reports the exact current and previous public method names", () => {
    expect(
      attemptMessage({
        method: "WireGuard",
        previousMethod: null,
        retry: false,
      }),
    ).toBe("Пробую WireGuard…");
    expect(
      attemptMessage({
        method: "AmneziaWG",
        previousMethod: "WireGuard",
        retry: true,
      }),
    ).toBe("WireGuard не подключился, пробую AmneziaWG…");
  });
});
