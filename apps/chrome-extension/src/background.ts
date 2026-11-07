import { Controller } from "./controller";
import { applyProxy, clearProxy, verifyProxy } from "./browser";
import { UUID, errorCode, proxyAuth } from "./model";
import { stateStorage } from "./storage";

const storage = stateStorage(chrome.storage.local, chrome.storage.session);

const controller = new Controller({
  load: storage.load,
  save: async (value) => {
    await storage.save(value);
    await chrome.action.setBadgeText({
      text:
        value.phase === "CONNECTED"
          ? "ON"
          : value.phase === "FAILED"
            ? "!"
            : "",
    });
    await chrome.action.setBadgeBackgroundColor({
      color: value.phase === "CONNECTED" ? "#51d6ca" : "#c82b28",
    });
  },
  installation: async () => {
    const stored = (await chrome.storage.local.get("installation"))
      .installation;
    if (typeof stored === "string" && UUID.test(stored)) return stored;
    const id = crypto.randomUUID();
    await chrome.storage.local.set({ installation: id });
    return id;
  },
  apply: applyProxy,
  clear: clearProxy,
  verify: verifyProxy,
  fetch: (...args) => fetch(...args),
  sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
});
const ready = (async () => {
  await chrome.storage.local.setAccessLevel({
    accessLevel: "TRUSTED_CONTEXTS",
  });
  await chrome.storage.session.setAccessLevel({
    accessLevel: "TRUSTED_CONTEXTS",
  });
  await controller.init();
  await chrome.alarms.create("connection", { periodInMinutes: 0.5 });
})();
let queue: Promise<unknown> = ready;
function enqueue<T>(operation: () => Promise<T>): Promise<T> {
  const task = queue.then(operation);
  queue = task.catch(() => undefined);
  return task;
}
function background(operation: () => Promise<unknown>) {
  void enqueue(operation).catch((error) => controller.fail(error));
}

// Register synchronously so Chrome can wake the worker for proxy authentication.
// Never inspect/store URLs, DNS queries, page contents or navigation history.
const attempts = new Map<string, number>();
chrome.webRequest.onAuthRequired.addListener(
  (details, respond) => {
    if (!respond) return undefined;
    void ready
      .then(() => {
        const proxy = controller.state.lease?.configuration?.proxy;
        if (!proxyAuth(details, proxy)) {
          respond({});
          return;
        }
        const now = Date.now();
        for (const [id, when] of attempts)
          if (now - when > 60000) attempts.delete(id);
        if (
          !controller.state.wanted ||
          !proxy ||
          attempts.has(details.requestId) ||
          attempts.size >= 1024
        ) {
          respond({ cancel: true });
          return;
        }
        attempts.set(details.requestId, now);
        respond({
          authCredentials: {
            username: proxy.username,
            password: proxy.password,
          },
        });
      })
      .catch(() => respond({ cancel: true }));
    return undefined;
  },
  { urls: ["<all_urls>"] },
  ["asyncBlocking"],
);
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "connection") background(() => controller.tick());
});
chrome.runtime.onStartup.addListener(() => {
  background(() => controller.tick());
});
chrome.runtime.onInstalled.addListener(() => {
  background(() => controller.tick());
});
chrome.proxy.settings.onChange.addListener(() => {
  if (
    controller.state.phase === "CONNECTED" &&
    controller.state.lease?.configuration
  )
    background(() => verifyProxy(controller.state.lease!.configuration!.proxy));
});
chrome.proxy.onProxyError.addListener(() => {
  if (controller.state.wanted)
    void controller.fail(new Error("PROXY_NETWORK_ERROR"));
});

chrome.runtime.onMessage.addListener((message: unknown, sender, respond) => {
  if (
    sender.id !== chrome.runtime.id ||
    sender.url !== chrome.runtime.getURL("popup.html")
  )
    return;
  const data = message as {
    type?: string;
    email?: string;
    code?: string;
    country?: string;
    id?: string;
    subject?: string;
    description?: string;
  };
  if (!data || typeof data.type !== "string") return;
  const text = (value: unknown, max: number) =>
    typeof value === "string" && value.length <= max ? value : "";
  if (data.type === "disconnect") controller.cancel();
  const task =
    data.type === "snapshot"
      ? ready.then(() => controller.snapshot())
      : enqueue(async () => {
          switch (data.type) {
            case "requestOtp":
              await controller.requestOtp(text(data.email, 254));
              break;
            case "resetOtp":
              await controller.resetOtp();
              break;
            case "login":
              await controller.login(text(data.email, 254), text(data.code, 6));
              break;
            case "refresh":
              await controller.refreshAccount();
              break;
            case "connect":
              background(() => controller.connect(text(data.country, 4)));
              break;
            case "disconnect":
              background(() => controller.disconnect());
              break;
            case "logout":
              await controller.logout();
              break;
            case "devices":
              return controller.devices();
            case "revokeDevice":
              return controller.revokeDevice(text(data.id, 36));
            case "billingPortal":
              await chrome.tabs.create({
                url: await controller.billingPortal(),
              });
              return { opened: true };
            case "billing":
              return controller.billing();
            case "support":
              return controller.support({
                request_id: text(data.id, 36),
                subject: text(data.subject, 120),
                description: text(data.description, 4000),
              });
            default:
              throw new Error("INVALID_REQUEST");
          }
          return controller.snapshot();
        });
  void task
    .then((value) => respond({ ok: true, value }))
    .catch((error) => respond({ ok: false, code: errorCode(error) }));
  return true;
});
background(async () => {
  await controller.tick();
  await controller.refreshAccount();
});
