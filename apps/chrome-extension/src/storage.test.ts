import { describe, expect, it, vi } from "vitest";
import { Controller, type Ports, type PrivateState } from "./controller";
import { stateStorage } from "./storage";

const auth = {
  access_token: "test-access",
  refresh_token: "test-refresh",
  session_id: "11111111-1111-4111-8111-111111111111",
};
function area() {
  const data: Record<string, unknown> = {};
  return {
    data,
    get: async (key: string) =>
      key in data ? { [key]: structuredClone(data[key]) } : {},
    set: async (value: Record<string, unknown>) => {
      Object.assign(data, structuredClone(value));
    },
  };
}
function fixture() {
  const local = area(),
    session = area();
  const io: Ports = {
    ...stateStorage(local, session),
    installation: async () => auth.session_id,
    clear: vi.fn(async () => {}),
    apply: vi.fn(async () => {}),
    verify: vi.fn(async () => {}),
    sleep: async () => {},
    fetch: vi.fn(async () => Response.json({})),
  };
  return { local, session, io, controller: new Controller(io) };
}
describe("auth persistence and OTP popup recovery", () => {
  it("keeps auth across browser exit, clears old proxy overrides and drops lease secrets", async () => {
    const { local, session, io, controller } = fixture();
    controller.state.session = auth;
    controller.state.wanted = true;
    controller.state.pending = {
      id: auth.session_id,
      key: "test-lease-key",
      country: "NL",
    };
    await io.save(controller.state);
    expect(local.data).toEqual({ auth });
    delete session.data.private; // Chrome clears storage.session on browser exit.
    const restarted = new Controller(io);
    await restarted.init();
    expect(restarted.snapshot().signedIn).toBe(true);
    expect(restarted.snapshot().phase).toBe("DISCONNECTED");
    expect(restarted.state.pending).toBeUndefined();
    expect(io.clear).toHaveBeenCalledOnce();
  });
  it("migrates existing session-only auth and persists rotation and sign-out", async () => {
    const { local, session, io, controller } = fixture();
    controller.state.session = auth;
    session.data.private = structuredClone(controller.state);
    await controller.init();
    expect(local.data.auth).toEqual(auth);
    controller.state.session = { ...auth, refresh_token: "rotated" };
    await io.save(controller.state);
    expect(local.data.auth).toEqual(controller.state.session);
    await controller.logout();
    expect(local.data.auth).toBeNull();
    // A partial volatile write cannot restore the old login after durable logout.
    session.data.private = { ...controller.state, session: auth };
    expect((await io.load())?.session).toBeUndefined();
  });
  it("preserves the requested email after popup closes and worker restarts, never the OTP", async () => {
    const { controller, io, local } = fixture();
    await controller.requestOtp("preview@example.com");
    const reopened = new Controller(io);
    await reopened.init();
    expect(reopened.snapshot().otpEmail).toBe("preview@example.com");
    expect(local.data).toEqual({ auth: null });
    io.fetch = async () =>
      Response.json({ error: { code: "invalid_otp" } }, { status: 401 });
    await expect(
      reopened.login("preview@example.com", "123456"),
    ).rejects.toThrow("INVALID_OTP");
    expect(JSON.stringify(await io.load())).not.toContain("123456");
    expect(reopened.snapshot().otpEmail).toBe("preview@example.com");
    await reopened.resetOtp();
    expect((await io.load())?.otpEmail).toBeUndefined();
  });
  it("does not show a code screen when sending failed", async () => {
    const { controller, io } = fixture();
    io.fetch = async () => {
      throw new Error("offline");
    };
    await expect(controller.requestOtp("preview@example.com")).rejects.toThrow(
      "NETWORK_ERROR",
    );
    expect(controller.snapshot().otpEmail).toBeNull();
  });
  it("deletes durable auth after revocation but retains it during transient network failure", async () => {
    const { controller, io, local } = fixture();
    controller.state.session = auth;
    await io.save(controller.state);
    io.fetch = async () => {
      throw new Error("offline");
    };
    await expect(controller.refreshAccount()).rejects.toThrow("NETWORK_ERROR");
    expect(local.data.auth).toEqual(auth);
    io.fetch = async (url) =>
      String(url).endsWith("/version")
        ? Response.json({ application_version: "test" })
        : Response.json({ error: { code: "device_revoked" } }, { status: 403 });
    await expect(controller.refreshAccount()).rejects.toThrow(
      "SIGN_IN_REQUIRED",
    );
    expect(local.data.auth).toBeNull();
    expect(((await io.load()) as PrivateState).session).toBeUndefined();
  });
});
