import { chromium } from "@playwright/test";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import assert from "node:assert/strict";

// Production artifact in an isolated browser profile; only the API is a fixture.
// These screenshots and navigation tests do not claim live proxy acceptance.
const extension = path.resolve("dist");
const profile = await mkdtemp(path.join(tmpdir(), "pl-chrome-review-"));
const output = path.resolve("review");
await mkdir(output, { recursive: true });
const launch = (offline = false) =>
  chromium.launchPersistentContext(profile, {
    channel: "chromium",
    headless: true,
    viewport: { width: 480, height: 600 },
    offline,
    args: [
      `--disable-extensions-except=${extension}`,
      `--load-extension=${extension}`,
    ],
  });
let context = await launch();
const id = "11111111-1111-4111-8111-111111111111";
const device = "22222222-2222-4222-8222-222222222222";
const errors = [];
let billingAvailable = true;
let guest = false;
const demoKeys = [];
async function mockAPI() {
  await context.route("https://prettylisavpn.com/account/**", (route) =>
    route.fulfill({
      contentType: "text/html",
      body: "<title>Fixture billing portal</title>",
    }),
  );
  await context.route("https://api.prettylisavpn.com/**", async (route) => {
    const p = new URL(route.request().url()).pathname;
    if (p === "/billing/overview" && !billingAvailable)
      return route.fulfill({
        status: 503,
        json: { error: { code: "BILLING_UNAVAILABLE" } },
      });
    let value;
    let status = 200;
    if (p === "/version")
      value = { application_version: "0.41.0-test-fixture" };
    else if (p === "/auth/request-otp") value = { status: "accepted" };
    else if (p === "/auth/demo" || p === "/auth/verify-otp") {
      guest = p === "/auth/demo";
      if (guest) {
        const body = route.request().postDataJSON();
        assert.equal(body.platform, "CHROME_EXTENSION");
        assert.match(body.device_key, /^[a-f0-9]{64}$/);
        demoKeys.push(body.device_key);
      }
      value = {
        session_id: id,
        access_token: "fixture-access",
        refresh_token: "fixture-refresh",
        user: { id },
        device: { id: device },
      };
    } else if (p === "/auth/logout") value = {};
    else if (p === "/me")
      value = {
        id,
        email: guest ? null : "preview@example.com",
        plan: guest ? "DEMO" : "FREE",
        active_device_count: guest ? 1 : 2,
        entitlements: { free_seconds_usable: guest ? 900 : 3600 },
      };
    else if (p === "/vpn/countries")
      value = {
        autopilot: { available: true },
        countries: [
          { country_code: "NL", available: true, quality: 98 },
          { country_code: "DE", available: false, quality: 0 },
        ],
      };
    else if (p === "/devices")
      value = {
        devices: [
          {
            id: device,
            device_name: "Chrome Preview",
            is_current: true,
            status: "ACTIVE",
            created_at: "2026-11-04T10:00:00Z",
            last_login_at: "2026-11-04T12:00:00Z",
          },
        ],
      };
    else if (p === "/billing/overview")
      value = {
        plan: "FREE",
        status: "FREE",
        paid_until: null,
        auto_renew: false,
        current_price: null,
        payment_method: null,
        new_contract_required: true,
        offers: [
          {
            id,
            plan: "PREMIUM",
            period: "MONTH",
            prices: {
              RUB: { amount_minor: 19900 },
              USD: { amount_minor: 399 },
            },
          },
        ],
      };
    else if (p === "/billing/portal")
      value = {
        url: "https://prettylisavpn.com/account/#handoff=" + "a".repeat(43),
      };
    else if (p === "/support/requests") value = { status: "ACCEPTED" };
    else if (p === "/vpn/sessions/current") value = null;
    else if (p === "/vpn/sessions") {
      status = 503;
      value = { error: { code: "VPN_NO_AVAILABLE_NODE" } };
    } else {
      status = 404;
      value = { error: { code: "NOT_FOUND" } };
    }
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(value),
    });
  });
}
try {
  await mockAPI();
  const worker =
    context.serviceWorkers()[0] ??
    (await context.waitForEvent("serviceworker"));
  const extensionId = new URL(worker.url()).host;
  let page = await context.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(`chrome-extension://${extensionId}/popup.html`);
  // All six complete locales and document destinations on the installed artifact.
  for (const [lang, name, picker] of [
    ["en", "english", "язык"],
    ["de", "deutsch", "language"],
    ["fr", "français", "sprache"],
    ["es", "español", "langue"],
    ["zh", "中文", "idioma"],
    ["ru", "русский", "语言"],
  ]) {
    await page.getByRole("button", { name: picker, exact: true }).click();
    assert.equal(await page.locator(".language-options button").count(), 6);
    await page.getByRole("button", { name, exact: true }).click();
    await page.reload();
    await page.locator(".language-trigger").filter({ hasText: lang }).waitFor();
    const base =
      "https://prettylisavpn.com" + (lang === "ru" ? "" : "/" + lang);
    for (const key of ["terms", "privacy", "refunds", "payments"])
      assert.equal(
        await page.locator(`a[href="${base}/legal/${key}/"]`).count(),
        1,
      );
    assert.equal(await page.locator(`a[href="${base}/"]`).count(), 1);
    assert.equal(
      await page.evaluate(() => globalThis.document.body.scrollWidth > 480),
      false,
    );
    await page.screenshot({ path: path.join(output, `login-${lang}.png`) });
  }
  assert.equal(await page.getByText("открыть вход во вкладке").count(), 0);
  assert.equal(
    await page.getByText("Вход сохраняется", { exact: false }).count(),
    0,
  );
  await page
    .getByRole("button", { name: "попробовать без регистрации" })
    .click();
  await page.getByText("гость", { exact: true }).waitFor();
  assert.equal(await page.getByLabel("куда подключаемся").isDisabled(), true);
  await page.screenshot({ path: path.join(output, "demo-home.png") });
  await page.close();
  page = await context.newPage();
  await page.goto(`chrome-extension://${extensionId}/popup.html`);
  await page.getByText("гость", { exact: true }).waitFor();
  assert.equal(await page.getByText("15:00", { exact: true }).count(), 1);
  // Real MV3 worker termination verifies recovery, not the reported enable-toggle issue.
  const cdp = await context.newCDPSession(page);
  await cdp.send("ServiceWorker.enable");
  await cdp.send("ServiceWorker.stopAllWorkers");
  await page.reload();
  await page.getByText("гость", { exact: true }).waitFor();
  assert.equal(
    (
      await page.evaluate(() =>
        chrome.runtime.sendMessage({ type: "snapshot" }),
      )
    ).ok,
    true,
  );
  await cdp.detach();
  await page
    .getByRole("button", { name: "войти или зарегистрироваться" })
    .click();
  await page
    .getByRole("button", { name: "попробовать без регистрации" })
    .click();
  await page.getByText("гость", { exact: true }).waitFor();
  assert.equal(demoKeys.length, 2);
  assert.equal(demoKeys[0], demoKeys[1]);
  await page
    .getByRole("button", { name: "войти или зарегистрироваться" })
    .click();
  await page.getByLabel("ваша почта").fill("preview@example.com");
  await page.screenshot({ path: path.join(output, "login-fixture.png") });
  await page.getByRole("button", { name: "получить код" }).click();
  await page.getByLabel("код из письма").waitFor();
  await page.close(); // Switching to webmail closes a real action popup.
  page = await context.newPage();
  await page.goto(`chrome-extension://${extensionId}/popup.html`);
  await page.getByLabel("код из письма").waitFor();
  assert.equal(
    await page.getByLabel("ваша почта").inputValue(),
    "preview@example.com",
  );
  await page.screenshot({
    path: path.join(output, "otp-reopened-fixture.png"),
  });
  await page.getByLabel("код из письма").fill("123456");
  await page.getByRole("button", { name: "войти", exact: true }).click();
  await page.getByText("preview@example.com", { exact: true }).waitFor();
  await context.close();
  // Start offline so a restored fixture token never reaches the real API before
  // routes are installed. This is a genuine browser/profile restart.
  context = await launch(true);
  await mockAPI();
  await context.setOffline(false);
  page = await context.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(`chrome-extension://${extensionId}/popup.html`);
  await page.getByText("preview@example.com", { exact: true }).waitFor();
  assert.equal(await page.getByLabel("код из письма").count(), 0);
  assert.equal(
    (await page.evaluate(() => chrome.storage.local.get("auth"))).auth
      .refresh_token,
    "fixture-refresh",
  );
  for (const [screen, label] of [
    ["home", "главная"],
    ["settings", "настройки"],
    ["about", "о приложении"],
  ]) {
    await page.getByRole("button", { name: label, exact: true }).click();
    await page.screenshot({ path: path.join(output, `${screen}-fixture.png`) });
  }
  await page.getByRole("button", { name: "настройки", exact: true }).click();
  await page
    .getByRole("button", { name: "устройства управление доступом к аккаунту" })
    .click();
  await page.getByText("Chrome Preview", { exact: true }).waitFor();
  await page.screenshot({ path: path.join(output, "devices-fixture.png") });
  await page.getByRole("button", { name: "главная", exact: true }).click();
  await page.getByRole("button", { name: "улучшить", exact: true }).click();
  await page.getByRole("heading", { name: "Premium", exact: true }).waitFor();
  await page
    .getByRole("button", { name: "управлять подпиской и оплатой", exact: true })
    .waitFor();
  await page.screenshot({
    path: path.join(output, "subscription-fixture.png"),
  });
  // A tab opened by an extension worker can navigate before Playwright attaches
  // request interception. Capture the real destination and create a blank tab,
  // then navigate it only after attachment so fixture handoffs never hit the site.
  const billingWorker =
    context.serviceWorkers()[0] ??
    (await context.waitForEvent("serviceworker"));
  await billingWorker.evaluate(() => {
    const createTab = chrome.tabs.create.bind(chrome.tabs);
    globalThis.billingReviewDestination = null;
    chrome.tabs.create = (details, ...args) => {
      if (details.url?.startsWith("https://prettylisavpn.com/account/")) {
        globalThis.billingReviewDestination = details.url;
        chrome.tabs.create = createTab;
        return createTab({ ...details, url: "about:blank" }, ...args);
      }
      return createTab(details, ...args);
    };
  });
  const billingOpened = context.waitForEvent("page");
  await page
    .getByRole("button", { name: "управлять подпиской и оплатой", exact: true })
    .click();
  const portal = await billingOpened;
  const destination = await billingWorker.evaluate(
    () => globalThis.billingReviewDestination,
  );
  assert.equal(
    destination,
    "https://prettylisavpn.com/account/#handoff=" + "a".repeat(43),
  );
  await portal.goto(destination);
  assert.equal(portal.url(), destination);
  assert.equal(await portal.title(), "Fixture billing portal");
  await portal.close();
  billingAvailable = false;
  await page.reload();
  await page.getByRole("button", { name: "улучшить", exact: true }).click();
  await page.getByTestId("billing-reference-prices").waitFor();
  assert.match(
    await page.getByTestId("billing-reference-prices").textContent(),
    /399/,
  );
  assert.match(
    await page.getByTestId("billing-reference-prices").textContent(),
    /\$5/,
  );
  await page.screenshot({
    path: path.join(output, "subscription-offline.png"),
  });
  billingAvailable = true;

  await page.getByRole("button", { name: "о приложении", exact: true }).click();
  await page.getByRole("button", { name: "написать в поддержку" }).click();
  await page.getByLabel("тема", { exact: true }).fill("Тестовая форма");
  await page
    .getByLabel("что случилось?")
    .fill("Локальная проверка интерфейса; сообщение не отправляется.");
  await page.getByRole("button", { name: "отправить", exact: true }).click();
  await page.getByText("обращение принято.", { exact: false }).waitFor();
  await page.getByRole("button", { name: "главная", exact: true }).click();
  await page.getByRole("button", { name: "подключить", exact: true }).click();
  await page
    .getByText("сейчас нет доступных прокси-серверов.", { exact: false })
    .waitFor();
  assert.equal(await page.getByText("подключено", { exact: true }).count(), 0);
  const state = await page.evaluate(() =>
    chrome.storage.session.get("private"),
  );
  assert.equal(state.private.phase, "FAILED");
  const settings = await page.evaluate(() =>
    chrome.proxy.settings.get({ incognito: false }),
  );
  assert.notEqual(settings.levelOfControl, "controlled_by_this_extension");
  await page.getByRole("button", { name: "язык", exact: true }).click();
  await page.getByRole("button", { name: "english", exact: true }).click();
  await page.getByRole("button", { name: "settings", exact: true }).click();
  await page.getByText("manage account access").waitFor();
  assert.deepEqual(errors, []);
  console.log(
    "Installed MV3 artifact: reopened OTP, browser restart, Home/Settings/About, devices, support, languages and honest failure passed. API fixtures; no live proxy claim.",
  );
} finally {
  await context.close();
  // The unique directory was created by this script under the OS temp folder.
  assert.ok(profile.startsWith(path.join(tmpdir(), "pl-chrome-review-")));
  await rm(profile, { recursive: true, force: true });
}
