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
  expect(relay.native.start).toHaveBeenCalledWith(relay.row.configuration);
  expect(
    JSON.parse(
      relay.requests.find((request) => request.method === "POST")!.body!,
    ).method,
  ).toBe("wireguard_relay");
  expect(progress.some((state) => state.includes("WireGuard через RU"))).toBe(
    true,
  );
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
  expect(requests).toEqual([]);
  expect(manager.current()).toMatchObject({
    phase: "FAILED",
    failure_code: "VPN_CONFLICT",
  });
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
