import { describe, expect, it, vi } from "vitest";
import { Controller, type Ports, type PrivateState } from "./controller";
import {
  controlsProxy,
  proxyAuth,
  proxySettings,
  validateLease,
  type Lease,
} from "./model";

const id = "11111111-1111-4111-8111-111111111111";
const ready = (): Lease => ({
  id,
  method: "https_proxy",
  status: "READY",
  code: null,
  country: "NL",
  expires_at: new Date(Date.now() + 600000).toISOString(),
  configuration: {
    proxy: {
      scheme: "https",
      host: "proxy-nl.prettylisavpn.com",
      port: 40001,
      username: id,
      password: "22222222-2222-4222-8222-222222222222",
    },
    expected_egress_ips: ["81.31.245.143"],
    scope: "browser",
    dns: "remote",
    ipv6: "blocked",
  },
});
function fixture() {
  let saved: PrivateState | undefined;
  let closed = false;
  const calls: { path: string; origin: string; options: RequestInit }[] = [];
  const io: Ports = {
    load: async () => saved,
    save: async (value) => {
      saved = structuredClone(value);
    },
    installation: async () => id,
    apply: vi.fn(async () => {}),
    clear: vi.fn(async () => {}),
    verify: vi.fn(async () => {}),
    sleep: async () => {},
    fetch: vi.fn(async (input, options = {}) => {
      const path = new URL(String(input)).pathname;
      calls.push({ path, origin: new URL(String(input)).origin, options });
      if (path.endsWith("/probe"))
        return Response.json({ verified: true, ip: "81.31.245.143" });
      if (path.endsWith("/current")) return Response.json(null);
      if (options.method === "DELETE") closed = true;
      return Response.json({ ...ready(), status: closed ? "CLOSED" : "READY" });
    }),
  };
  const controller = new Controller(io);
  controller.state.session = {
    session_id: id,
    access_token: "test-access",
    refresh_token: "test-refresh",
  };
  return { controller, io, calls, saved: () => saved };
}
describe("browser lease lifecycle", () => {
  it("requires real egress proof and actual browser ownership before connected", async () => {
    const { controller, io, calls } = fixture();
    await controller.connect("NL");
    expect(controller.snapshot().phase).toBe("CONNECTED");
    expect(io.apply).toHaveBeenCalledWith(ready().configuration!.proxy);
    expect(io.verify).toHaveBeenCalledTimes(2);
    expect(calls.some((c) => c.path.endsWith("/probe"))).toBe(true);
    expect(
      calls.every(
        (c) =>
          new Headers(c.options.headers).get("X-PrettyLisaVPN-Proxy-IP") ===
          "1",
      ),
    ).toBe(true);
    expect(
      calls
        .filter((c) => c.path.endsWith("/probe"))
        .every((c) => c.origin === "https://prettylisavpn.com"),
    ).toBe(true);
    expect(
      calls
        .filter((c) => !c.path.endsWith("/probe"))
        .every((c) => c.origin === "https://api.prettylisavpn.com"),
    ).toBe(true);
    const visible = JSON.stringify(controller.snapshot());
    for (const secret of [
      "test-access",
      "test-refresh",
      ready().configuration!.proxy.password,
    ])
      expect(visible).not.toContain(secret);
  });
  it("keeps proxy enforcement on egress mismatch and never says connected", async () => {
    const { controller, io } = fixture();
    const fetch = io.fetch;
    io.fetch = async (url, options) =>
      String(url).includes("/probe")
        ? Response.json({ verified: false, ip: "1.1.1.1" })
        : fetch(url, options);
    await controller.connect("NL").catch((e) => controller.fail(e));
    expect(controller.snapshot().phase).toBe("FAILED");
    expect(controller.snapshot().ip).toBeNull();
    expect(io.clear).not.toHaveBeenCalled();
  });
  it("restores existing browser policy and waits for confirmed server removal", async () => {
    const { controller, io, saved } = fixture();
    await controller.connect("AUTO");
    await controller.disconnect();
    expect(io.clear).toHaveBeenCalledOnce();
    expect(controller.snapshot()).toMatchObject({
      phase: "DISCONNECTED",
      cleanupPending: false,
    });
    expect(saved()?.lease).toBeUndefined();
  });
  it("preserves an uncertain allocation UUID across a service worker restart", async () => {
    const { controller, io, calls, saved } = fixture();
    const fetch = io.fetch;
    io.fetch = async (url, options) => {
      if (new URL(String(url)).pathname === "/vpn/sessions")
        throw new Error("network unavailable");
      return fetch(url, options);
    };
    await expect(controller.connect("NL")).rejects.toThrow("NETWORK_ERROR");
    const request = saved()?.pending;
    expect(request).toBeDefined();
    io.fetch = fetch;
    const recovered = new Controller(io);
    await recovered.init();
    await recovered.disconnect();
    const retried = calls.find((c) => c.path === "/vpn/sessions");
    expect(new Headers(retried?.options.headers).get("Idempotency-Key")).toBe(
      request!.id,
    );
    expect(recovered.snapshot().cleanupPending).toBe(false);
  });
  it("keeps cleanup pending on an API outage without trapping browser traffic", async () => {
    const { controller, io } = fixture();
    await controller.connect("NL");
    io.fetch = async () => {
      throw new Error("offline");
    };
    await controller.disconnect();
    expect(io.clear).toHaveBeenCalledOnce();
    expect(controller.snapshot()).toMatchObject({
      phase: "DISCONNECTED",
      cleanupPending: true,
    });
  });
  it("forgets stale connected state until a new probe after suspension", async () => {
    const { controller, io } = fixture();
    await controller.connect("NL");
    const restored = new Controller(io);
    await restored.init();
    expect(restored.snapshot().phase).toBe("VERIFYING");
    await restored.tick();
    expect(restored.snapshot().phase).toBe("CONNECTED");
  });
  it("clears proxy policy when browser restart clears session-only credentials", async () => {
    const { io } = fixture();
    const controller = new Controller(io);
    await controller.init();
    expect(io.clear).toHaveBeenCalledOnce();
    expect(controller.snapshot().signedIn).toBe(false);
  });
  it("restores access to sign-in after definitive device revocation", async () => {
    const { controller, io, saved } = fixture();
    await controller.connect("NL");
    io.fetch = async () =>
      Response.json({ error: { code: "device_revoked" } }, { status: 403 });
    await expect(controller.tick()).rejects.toThrow("SIGN_IN_REQUIRED");
    expect(io.clear).toHaveBeenCalledOnce();
    expect(controller.snapshot().signedIn).toBe(false);
    expect(saved()?.session).toBeUndefined();
    expect(saved()?.lease).toBeUndefined();
  });
  it("recovers failed proxy verification when the network returns", async () => {
    const { controller, io } = fixture();
    await controller.connect("NL");
    await controller.fail(new Error("NETWORK_ERROR"));
    await controller.tick();
    expect(io.apply).toHaveBeenCalledTimes(2);
    expect(controller.snapshot().phase).toBe("CONNECTED");
  });
  it("does not turn an invalid OTP into an expired-session error", async () => {
    const { controller, io } = fixture();
    delete controller.state.session;
    io.fetch = async () =>
      Response.json({ error: { code: "invalid_otp" } }, { status: 401 });
    await expect(
      controller.login("test@example.com", "123456"),
    ).rejects.toThrow("INVALID_OTP");
    expect(io.clear).not.toHaveBeenCalled();
  });
});
describe("proxy credential boundaries", () => {
  const proxy = ready().configuration!.proxy;
  it("never sends proxy credentials to website or unrelated proxy challenges", () => {
    const challenge = {
      isProxy: true,
      challenger: { host: proxy.host, port: proxy.port },
      realm: "PrettyLisaVPN",
    };
    expect(proxyAuth(challenge, proxy)).toBe(true);
    expect(proxyAuth({ ...challenge, isProxy: false }, proxy)).toBe(false);
    expect(
      proxyAuth(
        {
          ...challenge,
          challenger: { host: "attacker.example", port: proxy.port },
        },
        proxy,
      ),
    ).toBe(false);
    expect(proxyAuth({ ...challenge, realm: "other" }, proxy)).toBe(false);
  });
  it("requires encrypted first-party proxy configuration and matching lease credentials", () => {
    for (const changed of [
      { scheme: "http" },
      { host: "attacker.example" },
      { port: 80 },
      { username: "wrong" },
    ]) {
      const value = ready();
      Object.assign(value.configuration!.proxy, changed);
      expect(() => validateLease(value)).toThrow("UNSUPPORTED_CONFIGURATION");
    }
  });
  it("has no direct fallback and detects a competing extension", () => {
    const value = proxySettings(proxy);
    expect(value.rules?.bypassList).toEqual([
      "<-loopback>",
      "api.prettylisavpn.com",
    ]);
    expect(JSON.stringify(value)).not.toContain("DIRECT");
    expect(
      controlsProxy(
        { levelOfControl: "controlled_by_other_extensions", value },
        proxy,
      ),
    ).toBe(false);
    expect(
      controlsProxy(
        { levelOfControl: "controlled_by_this_extension", value },
        proxy,
      ),
    ).toBe(true);
  });
  it("accepts an advertised public exit IP with HTTPS and rejects private or unrelated IPs", () => {
    const value = ready();
    value.configuration!.proxy.host = "81.31.245.143";
    expect(validateLease(value)).toEqual(value);
    for (const host of [
      "5.181.49.183",
      "127.0.0.1",
      "10.0.0.1",
      "100.64.0.1",
      "169.254.169.254",
      "172.16.0.1",
      "192.168.1.1",
      "198.18.0.1",
      "203.0.113.1",
      "224.0.0.1",
      "999.1.1.1",
      "081.31.245.143",
    ]) {
      value.configuration!.proxy.host = host;
      if (host !== "5.181.49.183")
        value.configuration!.expected_egress_ips = [host];
      expect(() => validateLease(value)).toThrow("UNSUPPORTED_CONFIGURATION");
    }
  });
});
