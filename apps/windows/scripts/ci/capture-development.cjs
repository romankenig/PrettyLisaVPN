/* eslint @typescript-eslint/no-require-imports: "off" */
/* global process, console, fetch, AbortSignal, setTimeout, window, require, Buffer */
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { spawn, spawnSync } = require("node:child_process");
const { chromium } = require("playwright-core");
const { privateDecrypt, constants } = require("node:crypto");
const output = path.resolve("artifacts/development-acceptance");
fs.mkdirSync(output, { recursive: true });
const base = process.env.VITE_BACKEND_BASE_URL;
if (base !== "https://api.prettylisavpn.com") throw new Error("Unexpected API");
const account = JSON.parse(
  fs.readFileSync(process.env.ACCEPTANCE_CREDENTIAL_PATH, "utf8"),
);
const report = {
  checked_at: new Date().toISOString(),
  source_sha: process.env.GITHUB_SHA,
  run: process.env.GITHUB_RUN_ID,
  attempt: process.env.GITHUB_RUN_ATTEMPT,
  backend: base,
  frontend: JSON.parse(fs.readFileSync("package.json", "utf8")).version,
  api: [],
  checks: [],
  status: "running",
  authentication:
    "server-seeded disposable account; native refresh tested; email OTP not tested",
  real_payment_provider: false,
  real_payments: false,
  support_email_delivery: "not sent",
  vpn_tunnel:
    "not tested: no signed WireGuard distribution/runtime on hosted runner",
  smtp_authentication: account.smtp_authentication,
};
let app, browser, page;
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function get(endpoint, authenticated = true) {
  const response = await fetch(base + endpoint, {
    headers: authenticated
      ? { Authorization: `Bearer ${account.access_token}` }
      : {},
    redirect: "error",
    signal: AbortSignal.timeout(15000),
  });
  report.api.push({
    endpoint: endpoint.split("?")[0],
    status: response.status,
  });
  if (response.status !== 200)
    throw new Error("API contract failed: " + endpoint.split("?")[0]);
  return response.json();
}
async function capture(name) {
  const bounded = await page
    .locator(".sidebar-versions")
    .evaluate((versions) => {
      const sidebar = versions.closest("aside").getBoundingClientRect();
      return [...versions.querySelectorAll("dd")].every(
        (value) => value.getBoundingClientRect().right <= sidebar.right,
      );
    });
  if (!bounded) throw new Error("Runtime version overflows the sidebar");
  const result = spawnSync(
    "pwsh",
    [
      "-NoProfile",
      "-File",
      path.resolve("scripts/ci/capture-native-window.ps1"),
      "-AppProcessId",
      String(app.pid),
      "-OutputPath",
      path.join(output, name + ".png"),
      "-Action",
      "Capture",
    ],
    { encoding: "utf8", timeout: 60000 },
  );
  if (result.error || result.status)
    throw new Error("Native screenshot failed");
}
async function connect() {
  for (let i = 0; i < 60; i++) {
    try {
      browser = await chromium.connectOverCDP("http://127.0.0.1:9222");
      break;
    } catch {
      await delay(500);
    }
  }
  if (!browser) throw new Error("WebView2 unavailable");
  for (let i = 0; i < 60; i++) {
    page = browser
      .contexts()
      .flatMap((c) => c.pages())
      .find((p) => /(?:tauri\.localhost|localhost)/.test(p.url()));
    if (page) break;
    await delay(500);
  }
  if (!page) throw new Error("Native page unavailable");
  page.setDefaultTimeout(20000);
}
async function waitForManualInput(kind) {
  const key = fs.readFileSync(process.env.ACCEPTANCE_OTP_PRIVATE_KEY, "utf8");
  const scope = JSON.parse(
    fs.readFileSync(process.env.ACCEPTANCE_OTP_PUBLIC_KEY, "utf8"),
  );
  const url = `https://api.github.com/repos/${process.env.GITHUB_REPOSITORY}/contents/acceptance-otp.json?ref=acceptance-otp-${process.env.GITHUB_RUN_ID}`;
  const deadline = Date.now() + (kind === "ready" ? 600000 : 300000);
  while (Date.now() < deadline) {
    const response = await fetch(url, {
      headers: {
        Authorization: `Bearer ${process.env.GH_ACCEPTANCE_READ_TOKEN}`,
        Accept: "application/vnd.github+json",
      },
      signal: AbortSignal.timeout(10000),
    });
    if (response.status === 200) {
      const envelope = JSON.parse(
        Buffer.from((await response.json()).content, "base64").toString("utf8"),
      );
      const value = JSON.parse(
        privateDecrypt(
          {
            key,
            padding: constants.RSA_PKCS1_OAEP_PADDING,
            oaepHash: "sha256",
          },
          Buffer.from(envelope.ciphertext, "base64"),
        ).toString("utf8"),
      );
      if (value.run === scope.run && value.nonce === scope.nonce) {
        if (kind === "ready" && value.ready === true) return;
        if (kind === "code" && /^\d{6}$/.test(value.code)) return value.code;
      }
    }
    if (response.status !== 404 && response.status !== 200)
      throw new Error("OTP envelope transport unavailable");
    await delay(2000);
  }
  throw new Error("Manual input not received within acceptance window");
}
async function main() {
  await get("/health", false);
  await get("/ready", false);
  const version = await get("/version", false);
  if (
    version.environment !== "development" ||
    !version.application_version.startsWith("0.10.0-dev.")
  )
    throw new Error("Unexpected runtime identity");
  report.runtime_version = version.application_version;
  try {
    const response = await fetch("https://ipwho.is/", {
      signal: AbortSignal.timeout(10000),
    });
    const location = await response.json();
    report.public_location_probe = {
      http_status: response.status,
      provider_success: location.success === true,
    };
  } catch {
    report.public_location_probe = { status: "unavailable" };
  }
  const me = await get("/me");
  if (
    me.email !== account.email ||
    me.active_device_count !== 2 ||
    me.plan !== "FREE"
  )
    throw new Error("Disposable account mismatch");
  const devices = await get("/devices");
  report.device_response_keys = Object.keys(devices);
  const countries = await get("/vpn/countries");
  report.country_count = countries.countries.length;
  await get("/vpn/sessions/current");
  await get(
    "/messages?platform=WINDOWS&app_version=" +
      report.frontend +
      "&locale=ru&schema_version=1",
  );
  const billing = await get("/billing/overview");
  if (
    billing.provider_mode !== "DISABLED" ||
    billing.actions.length ||
    billing.payment_routes.length !== 4 ||
    billing.payment_routes.some(
      (r) => r.currencies.length || r.recurring_currencies.length,
    )
  )
    throw new Error("Disabled provider contract mismatch");
  app = spawn(
    path.resolve("src-tauri/target/debug/prettylisavpn-windows.exe"),
    [],
    {
      env: {
        ...process.env,
        WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:
          "--remote-debugging-port=9222 --disable-gpu",
        WEBVIEW2_USER_DATA_FOLDER: fs.mkdtempSync(
          path.join(os.tmpdir(), "prettylisa-live-"),
        ),
      },
      stdio: "ignore",
    },
  );
  await connect();
  const installation = await page.evaluate(() =>
    window.__TAURI_INTERNALS__.invoke("get_installation_id"),
  );
  fs.writeFileSync(
    process.env.ACCEPTANCE_CREDENTIAL_PATH + ".installation",
    installation,
  );
  await page.locator("#login-email").waitFor();
  await page.evaluate(async (credential) => {
    await window.__TAURI_INTERNALS__.invoke("save_refresh_credential", {
      credential,
    });
  }, account.credential);
  await page.reload();
  await page.getByText(account.email, { exact: true }).waitFor();
  await page.getByRole("combobox").waitFor();
  await page.waitForFunction(() => {
    const location = window.document.querySelector(".current-location");
    return location && !location.textContent.includes("определяем…");
  });
  report.native_location = (await page
    .locator(".current-location__details")
    .isVisible())
    ? "available"
    : "unavailable";
  // Observe the same native HTTP plugin without recording an IP or response body.
  report.native_location_probe = await page.evaluate(async () => {
    const invoke = window.__TAURI_INTERNALS__.invoke;
    let responseRid;
    try {
      const rid = await invoke("plugin:http|fetch", {
        clientConfig: {
          method: "GET",
          url: "https://ipwho.is/",
          headers: [],
          data: null,
          connectTimeout: 8000,
        },
      });
      const response = await invoke("plugin:http|fetch_send", { rid });
      responseRid = response.rid;
      let body = "";
      const decoder = new window.TextDecoder();
      for (let i = 0; i < 100; i++) {
        const buffer = await invoke("plugin:http|fetch_read_body", {
          rid: responseRid,
        });
        const chunk = new Uint8Array(buffer);
        if (chunk[chunk.length - 1] === 1) break;
        body += decoder.decode(chunk.slice(0, -1), { stream: true });
        if (body.length > 65536) throw new Error("body size exceeded");
      }
      const data = JSON.parse(body);
      return {
        http_status: response.status,
        provider_success: data.success === true,
        valid_ip_present: typeof data.ip === "string",
        rejection_category:
          data.success === true
            ? null
            : /cors/i.test(String(data.message))
              ? "cors"
              : /limit|quota/i.test(String(data.message))
                ? "rate_limit"
                : "other",
      };
    } catch (error) {
      const message = String(error);
      return {
        error_category: /cert|tls|ssl/i.test(message)
          ? "tls"
          : /scope|allow|denied/i.test(message)
            ? "permission"
            : /dns|resolve/i.test(message)
              ? "dns"
              : /timeout|timed out/i.test(message)
                ? "timeout"
                : "other",
      };
    } finally {
      if (responseRid !== undefined)
        await invoke("plugin:http|fetch_cancel_body", {
          rid: responseRid,
        }).catch(() => {});
    }
  });
  if (report.native_location !== "available")
    throw new Error("Native public location unavailable");
  report.checks.push(
    "real public location displayed through fixed native request",
  );
  report.checks.push(
    "native credential store → real HTTPS refresh → me → Home",
  );
  await capture("01-development-home");
  await page.reload();
  await page.getByText(account.email, { exact: true }).waitFor();
  report.checks.push(
    "second native session restoration with rotated refresh credential",
  );
  await page.getByRole("link", { name: "настройки", exact: true }).click();
  await page.getByRole("link", { name: /устройства/ }).click();
  await page
    .getByRole("heading", { name: "Acceptance Windows", exact: true })
    .waitFor();
  await page
    .getByRole("heading", { name: "Acceptance spare", exact: true })
    .waitFor();
  await page
    .getByText("последний вход: нет данных", { exact: false })
    .first()
    .waitFor();
  await capture("02-development-devices");
  await page
    .getByRole("button", { name: "отозвать доступ", exact: true })
    .click();
  await page.getByRole("button", { name: "да, отозвать", exact: true }).click();
  await page.getByText("отозвано", { exact: true }).waitFor();
  report.checks.push("real device list and spare-device revocation");
  await capture("03-development-revoked");
  await page.getByRole("link", { name: "главная", exact: true }).click();
  await page
    .locator(".account-summary")
    .getByText("1", { exact: true })
    .waitFor();
  report.checks.push(
    "returning Home refreshes the device count after revocation",
  );
  await capture("03a-development-home-refreshed");
  await page.getByRole("link", { name: "настройки", exact: true }).click();
  await page.getByRole("link", { name: /подписк/ }).click();
  await page
    .getByText(
      "оплата пока недоступна. данные подписки доступны для просмотра.",
      { exact: true },
    )
    .waitFor();
  if (
    !(await page
      .getByRole("button", { name: "оформить подписку", exact: true })
      .isDisabled())
  )
    throw new Error("Live backend enabled payments without provider");
  if (await page.getByRole("dialog").count())
    throw new Error("Unexpected payment dialog");
  await page.getByRole("button", { name: "$", exact: true }).click();
  if (
    !(await page
      .getByRole("button", { name: "оформить подписку", exact: true })
      .isDisabled())
  )
    throw new Error("USD bypassed disabled provider");
  report.checks.push(
    "real billing overview, RUB/USD browsing, disabled payment actions",
  );
  await capture("04-development-subscription");
  await page.getByRole("link", { name: "о приложении", exact: true }).click();
  await page
    .getByRole("heading", { name: "о приложении", exact: true })
    .waitFor();
  await page
    .getByText(version.application_version, { exact: true })
    .last()
    .waitFor();
  await page
    .getByRole("button", { name: "написать в поддержку", exact: true })
    .click();
  await page
    .getByRole("dialog", { name: "помощь и поддержка", exact: true })
    .waitFor();
  await capture("05-development-support");
  await page.keyboard.press("Escape");
  report.checks.push(
    "runtime version rendered; support form opens without sending mail",
  );
  await page.getByRole("link", { name: "настройки", exact: true }).click();
  await page.getByRole("button", { name: /выйти/ }).click();
  await page.locator("#login-email").waitFor();
  const stored = await page.evaluate(() =>
    window.__TAURI_INTERNALS__.invoke("load_refresh_credential"),
  );
  if (stored !== null) throw new Error("Logout retained refresh credential");
  await page.reload();
  await page.locator("#login-email").waitFor();
  report.checks.push(
    "real logout; native credential removed; restart stays logged out",
  );
  await capture("06-development-logout");
  if (process.env.ACCEPTANCE_MANUAL_OTP !== "1") {
    report.manual_otp = "deferred by owner; not requested or verified";
    report.status = "passed";
    return;
  }
  report.phase = "real email OTP";
  await waitForManualInput("ready");
  await page.locator("#login-email").fill(process.env.ACCEPTANCE_OTP_EMAIL);
  await page.getByRole("button", { name: /продолжить/i }).click();
  await page.locator("#otp-code").waitFor();
  const code = await waitForManualInput("code");
  await page.locator("#otp-code").fill(code);
  await page.getByRole("button", { name: /подтвердить/i }).click();
  await page
    .getByText(process.env.ACCEPTANCE_OTP_EMAIL, { exact: true })
    .waitFor();
  report.authentication =
    "real email OTP manually supplied by mailbox owner; native refresh separately verified on disposable account";
  report.checks.push(
    "real Windows → OTP email request → owner-supplied OTP → authenticated Home",
  );
  await page.getByRole("link", { name: "настройки", exact: true }).click();
  await page.getByRole("button", { name: /выйти/ }).click();
  await page.locator("#login-email").waitFor();
  report.checks.push(
    "real OTP account logged out; existing devices and subscriptions were not modified",
  );
  report.status = "passed";
}
main()
  .catch(async () => {
    report.status = "failed";
    report.failure =
      "Native/API assertion failed; secrets and response bodies intentionally omitted";
    if (page && report.phase !== "real email OTP") {
      try {
        await capture("failure");
      } catch {
        /* best effort */
      }
    }
    process.exitCode = 1;
  })
  .finally(async () => {
    if (page) {
      try {
        await page.evaluate(() =>
          window.__TAURI_INTERNALS__.invoke("delete_refresh_credential"),
        );
      } catch {
        /* cleanup also deletes server account */
      }
    }
    if (browser) await browser.close();
    if (app) app.kill();
    fs.rmSync(process.env.ACCEPTANCE_CREDENTIAL_PATH, { force: true });
    if (process.env.ACCEPTANCE_OTP_PRIVATE_KEY)
      fs.rmSync(process.env.ACCEPTANCE_OTP_PRIVATE_KEY, { force: true });
    fs.writeFileSync(
      path.join(output, "result.json"),
      JSON.stringify(report, null, 2) + "\n",
    );
    console.log(JSON.stringify(report));
  });
