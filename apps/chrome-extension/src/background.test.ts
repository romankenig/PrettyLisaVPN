import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const controller = vi.hoisted(() => ({
  state: { wanted: true },
  init: vi.fn(async () => {}),
  tick: vi.fn(async () => {}),
  refreshAccount: vi.fn(async () => {}),
  checkProxy: vi.fn(async () => {}),
  fail: vi.fn<(error: unknown) => Promise<void>>(async () => {}),
}));
vi.mock("./controller", () => ({
  Controller: class {
    constructor() {
      return controller;
    }
  },
}));
const event = () => ({ addListener: vi.fn<(callback: () => void) => void>() });
let proxyError: ReturnType<typeof event>;
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

beforeEach(async () => {
  vi.resetModules();
  vi.clearAllMocks();
  controller.state.wanted = true;
  proxyError = event();
  vi.stubGlobal("chrome", {
    storage: {
      local: { setAccessLevel: async () => {} },
      session: { setAccessLevel: async () => {} },
    },
    webRequest: { onAuthRequired: event() },
    alarms: { create: async () => {}, onAlarm: event() },
    runtime: { onStartup: event(), onInstalled: event(), onMessage: event() },
    proxy: { settings: { onChange: event() }, onProxyError: proxyError },
  });
  await import("./background");
  await vi.waitFor(() =>
    expect(controller.refreshAccount).toHaveBeenCalledOnce(),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("Chrome proxy-error events", () => {
  it("coalesces events during verification, including errors from the probe itself", async () => {
    let finish!: () => void;
    controller.checkProxy.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve;
        }),
    );
    const emit = proxyError.addListener.mock.calls[0][0];
    emit();
    emit();
    await vi.waitFor(() =>
      expect(controller.checkProxy).toHaveBeenCalledOnce(),
    );
    emit();
    await flush();
    expect(controller.checkProxy).toHaveBeenCalledOnce();
    expect(controller.fail).not.toHaveBeenCalled();
    finish();
    await flush();
    emit();
    await vi.waitFor(() =>
      expect(controller.checkProxy).toHaveBeenCalledTimes(2),
    );
  });
  it("ignores events while disconnected", async () => {
    controller.state.wanted = false;
    proxyError.addListener.mock.calls[0][0]();
    await flush();
    expect(controller.checkProxy).not.toHaveBeenCalled();
    expect(controller.fail).not.toHaveBeenCalled();
  });
  it("allows another check after an unexpected verification failure", async () => {
    const error = new Error("STORAGE_ERROR");
    controller.checkProxy.mockRejectedValueOnce(error);
    const emit = proxyError.addListener.mock.calls[0][0];
    emit();
    await vi.waitFor(() => expect(controller.fail).toHaveBeenCalledWith(error));
    emit();
    await vi.waitFor(() =>
      expect(controller.checkProxy).toHaveBeenCalledTimes(2),
    );
  });
});
