import { afterEach, expect, it, vi } from "vitest";
import { createWireGuardAdapter, type WireGuardNative } from "../vpn/wireguard";
import { createVpnConnectionManager } from "../vpn/connection";
import { createAuthenticationSession } from "../auth/session";
import { createTestCredentialStorage } from "./fakes";

afterEach(() => vi.useRealTimers());
const selection = { mode: "COUNTRY", country_code: "DE" } as const;
function setup(viaRelay = false) {
  vi.useFakeTimers();
  const row = {
    id: crypto.randomUUID(),
    status: "PROVISIONING",
    country: "DE",
    expires_at: new Date(Date.now() + 3600000).toISOString(),
    heartbeat_seconds: 30,
    configuration: {
      address: "10.88.1.2/32",
      server_public_key: "public",
      endpoint: "5.181.49.183:51820",
      mtu: 1380,
      dns: ["1.1.1.1"],
      allowed_ips: ["0.0.0.0/0", "::/0"],
    },
  };
  let allocated = false;
  const requests: { method: string; url: string; body?: string }[] = [];
  const transport = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const method = init?.method ?? "GET",
        url = String(input);
      requests.push({ method, url, body: init?.body as string | undefined });
      expect(init?.headers).toMatchObject({ Authorization: "Bearer current" });
      if (method === "POST" && url.endsWith("/sessions")) allocated = true;
      if (method === "DELETE") row.status = "CLOSED";
      if (
        method === "GET" &&
        !url.endsWith("/current") &&
        row.status === "PROVISIONING"
      )
        row.status = "READY";
      return Response.json(allocated ? row : null);
    },
  );
  const native: WireGuardNative = {
    prepare: vi.fn(async () => "public-key"),
    start: vi.fn(async () => {}),
    stop: vi.fn(async () => {}),
    verify: vi.fn(async () => true),
    isUp: vi.fn(async () => true),
  };
  const lost = vi.fn();
  const adapter = createWireGuardAdapter({
    baseUrl: "https://api.prettylisavpn.com",
    transport,
    native,
    bearer: async () => "current",
    lost,
    viaRelay,
  });
  return { adapter, native, requests, row, lost, transport };
}
it("falls back through the actual relay adapter only after direct cleanup", async () => {
  const direct = setup(),
    relay = setup(true);
  vi.mocked(direct.native.verify).mockResolvedValue(false);
  relay.row.configuration.endpoint = "45.153.68.12:20000";
  const manager = createVpnConnectionManager([direct.adapter, relay.adapter]);
  const progress: string[] = [];
  manager.subscribe(() => {
    progress.push(JSON.stringify(manager.current()));
  });
  const connecting = manager.connect("", selection);
  await vi.advanceTimersByTimeAsync(8000);
  await connecting;
  expect(direct.row.status).toBe("CLOSED");
  expect(manager.current().phase).toBe("CONNECTED");
  expect(relay.native.start).toHaveBeenCalledWith(relay.row.configuration, {
    id: relay.row.id,
    country: relay.row.country,
  });
  expect(
    JSON.parse(
      relay.requests.find((request) => request.method === "POST")!.body!,
    ).method,
  ).toBe("wireguard_relay");
  expect(progress.some((state) => state.includes("WireGuard+"))).toBe(true);
  await manager.disconnect("");
});
it("publishes real session only after native tunnel-bound proof and releases it", async () => {
  const { adapter, native, requests, row } = setup();
  const manager = createVpnConnectionManager([adapter]);
  const connecting = manager.connect("not-used-stale-token", selection);
  expect(manager.current().phase).toBe("CONNECTING");
  await vi.advanceTimersByTimeAsync(2500);
  await connecting;
  expect(manager.current()).toMatchObject({
    phase: "CONNECTED",
    session: {
      sessionId: row.id,
      countryCode: "DE",
      expiresAt: row.expires_at,
    },
  });
  expect(native.verify).toHaveBeenCalledWith("10.88.1.2/32", row.id, "current");
  expect(requests.find((item) => item.method === "POST")?.body).not.toContain(
    "private",
  );
  await manager.disconnect("");
  expect(requests.some((item) => item.method === "DELETE")).toBe(true);
  expect(manager.current().phase).toBe("DISCONNECTED");
});
it("never claims connection on failed egress verification", async () => {
  const { adapter, native, requests } = setup();
  vi.mocked(native.verify).mockResolvedValue(false);
  const manager = createVpnConnectionManager([adapter]);
  const connecting = manager.connect("", selection);
  await vi.advanceTimersByTimeAsync(5000);
  await connecting;
  expect(manager.current()).toMatchObject({
    phase: "FAILED",
    failure_code: "VPN_EGRESS_MISMATCH",
  });
  expect(requests.some((item) => item.method === "DELETE")).toBe(true);
});
it("stops on server revocation or a lost native service", async () => {
  const { adapter, native, lost } = setup();
  const connecting = adapter.connect(selection, new AbortController().signal);
  await vi.advanceTimersByTimeAsync(2500);
  await connecting;
  vi.mocked(native.isUp).mockResolvedValue(false);
  await vi.advanceTimersByTimeAsync(30000);
  expect(lost).toHaveBeenCalledOnce();
  await adapter.disconnect();
});
it("does not reserve remote access when an existing VPN conflicts", async () => {
  const { adapter, native, requests } = setup();
  vi.mocked(native.prepare).mockRejectedValue("VPN_CONFLICT");
  const manager = createVpnConnectionManager([adapter]);
  await manager.connect("", selection);
  expect(requests.every((request) => request.method === "GET")).toBe(true);
  expect(manager.current()).toMatchObject({
    phase: "FAILED",
    failure_code: "VPN_CONFLICT",
  });
});
it("revokes the remote grant even when stopping the native service fails", async () => {
  const { adapter, native, row, requests } = setup();
  const connecting = adapter.connect(selection, new AbortController().signal);
  await vi.advanceTimersByTimeAsync(2500);
  await connecting;
  vi.mocked(native.stop).mockRejectedValueOnce(new Error("VPN_CLEANUP_FAILED"));
  await expect(adapter.disconnect()).rejects.toThrow("VPN_CLEANUP_FAILED");
  expect(row.status).toBe("CLOSED");
  expect(
    requests.filter((request) => request.method === "DELETE"),
  ).toHaveLength(1);
  await adapter.disconnect();
  expect(
    requests.filter((request) => request.method === "DELETE"),
  ).toHaveLength(1);
});
it("cleans an abandoned device grant on startup once and leaves a new connection alone", async () => {
  const { adapter, row, requests } = setup();
  const previous = adapter.connect(selection, new AbortController().signal);
  await vi.advanceTimersByTimeAsync(2500);
  await previous;
  const manager = createVpnConnectionManager([adapter]);
  manager.setOwner?.("owner");
  await Promise.resolve();
  await Promise.resolve();
  await manager.reconcile("");
  expect(row.status).toBe("CLOSED");
  const count = requests.length;
  await manager.reconcile("");
  expect(requests).toHaveLength(count);
});
it("serializes refresh and never replays an ambiguously consumed refresh credential", async () => {
  const storage = createTestCredentialStorage();
  const session = createAuthenticationSession(storage);
  await session.establish({
    accessToken: "old",
    accessTokenExpiresIn: 0,
    refreshToken: "one-use",
    refreshTokenExpiresAt: "2030-01-01T00:00:00Z",
    sessionId: "session",
    userId: "user",
    deviceId: "device",
    plan: "FREE",
  });
  const api = {
    refresh: vi.fn(async () => {
      expect(await storage.retrieve()).toBeNull();
      throw new Error("timeout");
    }),
    me: vi.fn(),
  };
  const results = await Promise.allSettled([
    session.bearer(api),
    session.bearer(api),
  ]);
  expect(results.every((value) => value.status === "rejected")).toBe(true);
  expect(api.refresh).toHaveBeenCalledOnce();
  expect(await storage.retrieve()).toBeNull();
  expect(session.current()).toBeNull();
});

it("does not cancel method fallback when a slow initial verification overlaps a heartbeat failure", async () => {
  const direct = setup(),
    relay = setup(true);
  vi.mocked(direct.native.verify).mockImplementation(async () => {
    await new Promise((resolve) => setTimeout(resolve, 35000));
    return false;
  });
  const normal = direct.transport.getMockImplementation()!;
  direct.transport.mockImplementation(async (input, init) =>
    String(input).endsWith("/heartbeat")
      ? Response.json({ error: { code: "VPN_UNAVAILABLE" } }, { status: 503 })
      : normal(input, init),
  );
  const manager = createVpnConnectionManager([direct.adapter, relay.adapter]);
  direct.lost.mockImplementation((code) => {
    void manager.connectionLost?.(code);
  });
  const connecting = manager.connect("", selection);
  await vi.advanceTimersByTimeAsync(120000);
  await connecting;
  expect(direct.lost).not.toHaveBeenCalled();
  expect(direct.row.status).toBe("CLOSED");
  expect(relay.native.start).toHaveBeenCalledOnce();
  expect(manager.current().phase).toBe("CONNECTED");
  await manager.disconnect("");
});

it("retains private configuration across heartbeat responses and tolerates one probe failure", async () => {
  const { adapter, native, transport, lost } = setup();
  const normal = transport.getMockImplementation()!;
  transport.mockImplementation(async (input, init) => {
    const response = await normal(input, init);
    if (!String(input).endsWith("/heartbeat")) return response;
    const value = await response.json();
    delete value.configuration;
    return Response.json(value);
  });
  const connecting = adapter.connect(selection, new AbortController().signal);
  await vi.advanceTimersByTimeAsync(2500);
  await connecting;
  vi.mocked(native.verify)
    .mockResolvedValueOnce(false)
    .mockResolvedValueOnce(true)
    .mockResolvedValue(false);
  await vi.advanceTimersByTimeAsync(60000);
  expect(lost).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(60000);
  expect(lost).toHaveBeenCalledExactlyOnceWith("VPN_CONNECTION_LOST");
  await adapter.disconnect();
});

it("ignores a late health check after disconnection", async () => {
  const { adapter, native, lost } = setup();
  const connecting = adapter.connect(selection, new AbortController().signal);
  await vi.advanceTimersByTimeAsync(2500);
  await connecting;
  let finish!: (result: boolean) => void;
  vi.mocked(native.isUp).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  await vi.advanceTimersByTimeAsync(30000);
  await adapter.disconnect();
  finish(false);
  await vi.advanceTimersByTimeAsync(60000);
  expect(lost).not.toHaveBeenCalled();
});

it("does not try other methods when the device's daily budget is exhausted", async () => {
  const direct = setup(),
    relay = setup(true);
  const normal = direct.transport.getMockImplementation()!;
  direct.transport.mockImplementation(async (input, init) =>
    init?.method === "POST" && String(input).endsWith("/sessions")
      ? Response.json(
          { error: { code: "DEMO_QUOTA_EXHAUSTED" } },
          { status: 403 },
        )
      : normal(input, init),
  );
  const manager = createVpnConnectionManager([direct.adapter, relay.adapter]);
  await manager.connect("", selection);
  expect(manager.current()).toMatchObject({
    phase: "FAILED",
    failure_code: "DEMO_QUOTA_EXHAUSTED",
  });
  expect(relay.native.prepare).not.toHaveBeenCalled();
});
