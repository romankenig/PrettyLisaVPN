import { afterEach, expect, it, vi } from "vitest";
import {
  createManagedAdapter,
  managedMethods,
  type ManagedConfiguration,
} from "../vpn/managed";
import type { SessionEngine } from "../vpn/sessionAdapter";
import { createVpnConnectionManager } from "../vpn/connection";

afterEach(() => vi.useRealTimers());
function setup(id: string) {
  vi.useFakeTimers();
  const session = crypto.randomUUID();
  const configuration: ManagedConfiguration = {
    engine_profile: {
      version: 1,
      session,
      country: "DE",
      method:
        managedMethods[
          id.replace(/_relay$/, "") as keyof typeof managedMethods
        ],
      server: "203.0.113.1",
      port: 40000,
      secret: "private-test-only-credential",
    },
    expected_egress_ips: ["203.0.113.2"],
  };
  const row = {
    id: session,
    country: "DE",
    status: "READY",
    expires_at: new Date(Date.now() + 3600000).toISOString(),
    heartbeat_seconds: 30,
    configuration,
  };
  let created = false;
  const requests: RequestInit[] = [];
  const transport = vi.fn(async (_: RequestInfo | URL, init?: RequestInit) => {
    requests.push(init!);
    if (init?.method === "POST") created = true;
    if (init?.method === "DELETE") row.status = "CLOSED";
    return Response.json(created ? row : null);
  });
  const native: SessionEngine<ManagedConfiguration> = {
    prepare: vi.fn(async () => "test-binding"),
    start: vi.fn(async () => {}),
    stop: vi.fn(async () => {}),
    verify: vi.fn(async () => true),
    isUp: vi.fn(async () => true),
  };
  const adapter = createManagedAdapter({
    id,
    name: id,
    baseUrl: "https://api.prettylisavpn.com",
    transport,
    native,
    bearer: async () => "access",
    lost: vi.fn(),
  });
  return { adapter, native, row, requests, configuration };
}

it.each(Object.keys(managedMethods).flatMap((id) => [id, id + "_relay"]))(
  "%s uses real adapter lifecycle and never exposes credentials in connection details",
  async (id) => {
    const { adapter, native, row, requests, configuration } = setup(id);
    const manager = createVpnConnectionManager([adapter]);
    const connecting = manager.connect("", {
      mode: "COUNTRY",
      country_code: "DE",
    });
    await vi.advanceTimersByTimeAsync(2000);
    await connecting;
    expect(manager.current().phase).toBe("CONNECTED");
    expect(native.start).toHaveBeenCalledWith(configuration, {
      id: row.id,
      country: row.country,
    });
    expect(native.verify).toHaveBeenCalledWith(configuration, row.id, "access");
    expect(
      JSON.parse(
        requests.find((request) => request.method === "POST")!.body as string,
      ).method,
    ).toBe(id);
    expect(JSON.stringify(await manager.connectionDetails!())).not.toContain(
      configuration.engine_profile.secret,
    );
    await manager.disconnect("");
    expect(row.status).toBe("CLOSED");
    expect(native.stop).toHaveBeenCalledTimes(2);
  },
);
it("rejects another lease's private profile before native start and revokes it", async () => {
  const { adapter, native, row, configuration } = setup("vless");
  configuration.engine_profile.session = crypto.randomUUID();
  const manager = createVpnConnectionManager([adapter]);
  await manager.connect("", { mode: "AUTO" });
  expect(manager.current().phase).toBe("FAILED");
  expect(native.start).not.toHaveBeenCalled();
  expect(row.status).toBe("CLOSED");
});
it("cannot treat RUNNING without verified Internet as success", async () => {
  const { adapter, native, row } = setup("hysteria2");
  vi.mocked(native.verify).mockResolvedValue(false);
  const manager = createVpnConnectionManager([adapter]);
  const connecting = manager.connect("", { mode: "AUTO" });
  await vi.advanceTimersByTimeAsync(5000);
  await connecting;
  expect(manager.current().phase).toBe("FAILED");
  expect(row.status).toBe("CLOSED");
});
