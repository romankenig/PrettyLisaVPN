/* eslint @typescript-eslint/no-require-imports: "off" */
/* global process, console, fetch, AbortSignal, setTimeout, window */
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { spawn, spawnSync } = require("node:child_process");
const { chromium } = require("playwright-core");
const output = path.resolve("artifacts/development-acceptance");
fs.mkdirSync(output, { recursive: true });
const base = process.env.VITE_BACKEND_BASE_URL;
if (base !== "https://api.prettylisavpn.com") throw new Error("Unexpected API");
const account = JSON.parse(fs.readFileSync(process.env.ACCEPTANCE_CREDENTIAL_PATH, "utf8"));
const report = {
  checked_at: new Date().toISOString(), source_sha: process.env.GITHUB_SHA,
  run: process.env.GITHUB_RUN_ID, attempt: process.env.GITHUB_RUN_ATTEMPT,
  backend: base, frontend: JSON.parse(fs.readFileSync("package.json", "utf8")).version,
  api: [], checks: [], status: "running", authentication: "server-seeded disposable account; native refresh tested; email OTP not tested",
  real_payment_provider: false, real_payments: false, support_email_delivery: "not sent",
  vpn_tunnel: "not tested: no signed WireGuard distribution/runtime on hosted runner",
};
let app, browser, page;
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function get(endpoint, authenticated = true) {
  const response = await fetch(base + endpoint, { headers: authenticated ? { Authorization: `Bearer ${account.access_token}` } : {}, redirect: "error", signal: AbortSignal.timeout(15000) });
  report.api.push({ endpoint: endpoint.split("?")[0], status: response.status });
  if (response.status !== 200) throw new Error("API contract failed: " + endpoint.split("?")[0]);
  return response.json();
}
async function capture(name) {
  const result = spawnSync("pwsh", ["-NoProfile", "-File", path.resolve("scripts/ci/capture-native-window.ps1"), "-AppProcessId", String(app.pid), "-OutputPath", path.join(output, name + ".png"), "-Action", "Capture"], { encoding: "utf8", timeout: 60000 });
  if (result.error || result.status) throw new Error("Native screenshot failed");
}
async function connect() {
  for (let i = 0; i < 60; i++) {
    try { browser = await chromium.connectOverCDP("http://127.0.0.1:9222"); break; } catch { await delay(500); }
  }
  if (!browser) throw new Error("WebView2 unavailable");
  for (let i = 0; i < 60; i++) {
    page = browser.contexts().flatMap((c) => c.pages()).find((p) => /(?:tauri\.localhost|localhost)/.test(p.url()));
    if (page) break;
    await delay(500);
  }
  if (!page) throw new Error("Native page unavailable");
  page.setDefaultTimeout(20000);
}
async function main() {
  await get("/health", false);
  await get("/ready", false);
  const version = await get("/version", false);
  if (version.environment !== "development" || !version.application_version.startsWith("0.10.0-dev.")) throw new Error("Unexpected runtime identity");
  report.runtime_version = version.application_version;
  const me = await get("/me");
  if (me.email !== account.email || me.active_device_count !== 2 || me.plan !== "FREE") throw new Error("Disposable account mismatch");
  const devices = await get("/devices");
  report.device_response_keys = Object.keys(devices);
  const countries = await get("/vpn/countries");
  report.country_count = countries.countries.length;
  await get("/vpn/sessions/current");
  await get("/messages?platform=WINDOWS&app_version=" + report.frontend + "&locale=ru&schema_version=1");
  const billing = await get("/billing/overview");
  if (billing.provider_mode !== "DISABLED" || billing.actions.length || billing.payment_routes.length !== 4 || billing.payment_routes.some((r) => r.currencies.length || r.recurring_currencies.length)) throw new Error("Disabled provider contract mismatch");
  app = spawn(path.resolve("src-tauri/target/debug/prettylisavpn-windows.exe"), [], { env: { ...process.env, WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: "--remote-debugging-port=9222 --disable-gpu", WEBVIEW2_USER_DATA_FOLDER: fs.mkdtempSync(path.join(os.tmpdir(), "prettylisa-live-")) }, stdio: "ignore" });
  await connect();
  await page.locator("#login-email").waitFor();
  await page.evaluate(async (credential) => { await window.__TAURI_INTERNALS__.invoke("save_refresh_credential", { credential }); }, account.credential);
  await page.reload();
  await page.getByText(account.email, { exact: true }).waitFor();
  await page.getByRole("combobox").waitFor();
  report.checks.push("native credential store → real HTTPS refresh → me → Home");
  await capture("01-development-home");
  await page.reload();
  await page.getByText(account.email, { exact: true }).waitFor();
  report.checks.push("second native session restoration with rotated refresh credential");
  await page.getByRole("link", { name: "настройки", exact: true }).click();
  await page.getByRole("link", { name: /устройства/ }).click();
  await page.getByRole("heading", { name: "Acceptance Windows", exact: true }).waitFor();
  await page.getByRole("heading", { name: "Acceptance spare", exact: true }).waitFor();
  await page.getByText("последний вход: нет данных", { exact: false }).first().waitFor();
  await capture("02-development-devices");
  await page.getByRole("button", { name: "отозвать доступ", exact: true }).click();
  await page.getByRole("button", { name: "да, отозвать", exact: true }).click();
  await page.getByText("отозвано", { exact: true }).waitFor();
  report.checks.push("real device list and spare-device revocation");
  await capture("03-development-revoked");
  await page.getByRole("link", { name: "настройки", exact: true }).click();
  await page.getByRole("link", { name: /подписк/ }).click();
  await page.getByText("оплата пока недоступна. данные подписки доступны для просмотра.", { exact: true }).waitFor();
  if (!(await page.getByRole("button", { name: "оформить подписку", exact: true }).isDisabled())) throw new Error("Live backend enabled payments without provider");
  if (await page.getByRole("dialog").count()) throw new Error("Unexpected payment dialog");
  await page.getByRole("button", { name: "$", exact: true }).click();
  if (!(await page.getByRole("button", { name: "оформить подписку", exact: true }).isDisabled())) throw new Error("USD bypassed disabled provider");
  report.checks.push("real billing overview, RUB/USD browsing, disabled payment actions");
  await capture("04-development-subscription");
  await page.getByRole("link", { name: "о приложении", exact: true }).click();
  await page.getByRole("heading", { name: "о приложении", exact: true }).waitFor();
  await page.getByText(version.application_version, { exact: true }).last().waitFor();
  await page.getByRole("button", { name: "написать в поддержку", exact: true }).click();
  await page.getByRole("dialog", { name: "помощь и поддержка", exact: true }).waitFor();
  await capture("05-development-support");
  await page.keyboard.press("Escape");
  report.checks.push("runtime version rendered; support form opens without sending mail");
  await page.getByRole("link", { name: "настройки", exact: true }).click();
  await page.getByRole("button", { name: /выйти/ }).click();
  await page.locator("#login-email").waitFor();
  const stored = await page.evaluate(() => window.__TAURI_INTERNALS__.invoke("load_refresh_credential"));
  if (stored !== null) throw new Error("Logout retained refresh credential");
  await page.reload();
  await page.locator("#login-email").waitFor();
  report.checks.push("real logout; native credential removed; restart stays logged out");
  await capture("06-development-logout");
  report.status = "passed";
}
main().catch(async () => { report.status = "failed"; report.failure = "Native/API assertion failed; secrets and response bodies intentionally omitted"; if (page) { try { await capture("failure"); } catch { /* best effort */ } } process.exitCode = 1; }).finally(async () => {
  if (page) { try { await page.evaluate(() => window.__TAURI_INTERNALS__.invoke("delete_refresh_credential")); } catch { /* cleanup also deletes server account */ } }
  if (browser) await browser.close();
  if (app) app.kill();
  fs.rmSync(process.env.ACCEPTANCE_CREDENTIAL_PATH, { force: true });
  fs.writeFileSync(path.join(output, "result.json"), JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report));
});
