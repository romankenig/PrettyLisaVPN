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
async function mockAPI() {
  await context.route("https://api.prettylisavpn.com/**", async (route) => {
    const p = new URL(route.request().url()).pathname;
    let value;
    let status = 200;
    if (p === "/version")
      value = { application_version: "0.34.0-test-fixture" };
    else if (p === "/auth/request-otp") value = { status: "accepted" };
    else if (p === "/auth/verify-otp")
      value = {
        session_id: id,
        access_token: "fixture-access",
        refresh_token: "fixture-refresh",
        user: { id },
        device: { id: device },
      };
    else if (p === "/me")
      value = {
        id,
        email: "preview@example.com",
        plan: "FREE",
        active_device_count: 2,
        entitlements: { free_seconds_usable: 3600 },
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
      value = { plan: "FREE", status: "FREE", paid_until: null };
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
  const opened = context.waitForEvent("page");
  await page.getByRole("button", { name: "открыть вход во вкладке" }).click();
  const loginTab = await opened;
  await loginTab.getByLabel("код из письма").waitFor();
  await loginTab.close();
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
  await page.getByRole("button", { name: "о приложении", exact: true }).click();
  await page.getByRole("button", { name: "написать в поддержку" }).click();
  await page.getByLabel("тема", { exact: true }).fill("Тестовая форма");
  await page
    .getByLabel("что случилось?")
    .fill("Локальная проверка интерфейса; сообщение не отправляется.");
  await page.getByRole("button", { name: "отправить", exact: true }).click();
  await page.getByText("Обращение принято.", { exact: false }).waitFor();
  await page.getByRole("button", { name: "главная", exact: true }).click();
  await page.getByRole("button", { name: "подключить", exact: true }).click();
  await page
    .getByText("Сейчас нет доступных прокси-серверов.", { exact: false })
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
  await page.getByLabel("Language").selectOption("1");
  await page.getByRole("button", { name: "settings", exact: true }).click();
  await page.getByText("manage account access").waitFor();
  assert.deepEqual(errors, []);
  console.log(
    "Installed MV3 artifact: reopened OTP, sign-in tab, browser restart, Home/Settings/About, devices, support, languages and honest failure passed. API fixtures; no live proxy claim.",
  );
} finally {
  await context.close();
  // The unique directory was created by this script under the OS temp folder.
  assert.ok(profile.startsWith(path.join(tmpdir(), "pl-chrome-review-")));
  await rm(profile, { recursive: true, force: true });
}
