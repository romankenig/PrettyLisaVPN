/* eslint @typescript-eslint/no-require-imports: "off" */
/* global console, process, setTimeout, URL, fetch, AbortSignal, require, document, window */
const fs = require("node:fs");
const path = require("node:path");
const { spawn, spawnSync } = require("node:child_process");
const { chromium } = require("playwright-core");

const output = path.resolve("artifacts/ui-review");
fs.mkdirSync(output, { recursive: true });
const executable = path.resolve("src-tauri/target/debug/prettylisavpn-windows.exe");
fs.copyFileSync(executable, path.join(output, "PrettyLisaVPN-UI-review.exe"));
fs.writeFileSync(
  path.join(output, "README.txt"),
  [
    "PrettyLisaVPN native Windows UI review",
    "Commit: " + (process.env.GITHUB_SHA || "local"),
    "Debug Tauri executable; captured through its real WebView2 on Windows.",
    "Account, devices and countries are loopback-only synthetic fixtures.",
    "Primary PNGs capture the real native window, including the custom application title bar.",
    "Extra *-content.png files capture the fixed WebView canvas (only collections scroll).",
    "No VPN connection was started or verified.",
    "This exe is a UI review build, not a production VPN distribution.",
    "It targets http://127.0.0.1:8000; run mock-ui-api.py to use the fixtures.",
    "WebView2 Runtime is required. WireGuard DLL is intentionally not packaged.",
    "No installer or code signing is included.",
  ].join("\n") + "\n",
);
fs.copyFileSync("scripts/ci/mock-ui-api.py", path.join(output, "mock-ui-api.py"));
const log = fs.openSync(path.join(output, "capture-process.log"), "w");
const api = spawn("python", ["scripts/ci/mock-ui-api.py"], {
  stdio: ["ignore", log, log],
});
let app;
let browser;
let page;
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitForUrl(url) {
  for (let attempt = 0; attempt < 60; attempt++) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1000) });
      if (response.ok) return;
    } catch {
      // The fixture service or WebView2 is still starting.
    }
    await delay(500);
  }
  throw new Error("Timed out waiting for " + url);
}

function nativeWindow(action, name) {
  const result = spawnSync("pwsh", [
    "-NoProfile", "-File", path.resolve("scripts/ci/capture-native-window.ps1"),
    "-AppProcessId", String(app.pid),
    "-OutputPath", path.join(output, name + ".png"),
    "-Action", action,
  ], { encoding: "utf8", timeout: 20000 });
  if (result.error || result.status !== 0) {
    throw new Error("Native window " + action + " failed: " + (result.stderr || result.error));
  }
}

async function screenshot(name) {
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => window.scrollTo(0, 0));
  await delay(300);
  const layout = await page.evaluate(() => {
    const main = document.querySelector("main");
    const bad = [];
    for (const node of [document.documentElement, document.body, main,
      ...document.querySelectorAll(".connection-card, .home-workspace")]) {
      if (node && (node.scrollHeight > node.clientHeight + 1 ||
        node.scrollWidth > node.clientWidth + 1)) bad.push(node.className || node.tagName);
    }
    return bad;
  });
  if (layout.length) throw new Error("Content exceeds fixed canvas: " + layout.join(", "));
  await page.getByRole("button", { name: "Свернуть", exact: true }).waitFor();
  await page.getByRole("button", { name: "Закрыть", exact: true }).waitFor();
  nativeWindow("Capture", name);
  await page.screenshot({ path: path.join(output, name + "-content.png"), fullPage: true });
}

async function main() {
  await waitForUrl("http://127.0.0.1:8000/me");
  app = spawn(executable, [], {
    env: {
      ...process.env,
      WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: "--remote-debugging-port=9222 --disable-gpu",
      WEBVIEW2_USER_DATA_FOLDER: path.join(output, "temporary-webview-profile"),
    },
    stdio: ["ignore", log, log],
  });
  await waitForUrl("http://127.0.0.1:9222/json/version");
  browser = await chromium.connectOverCDP("http://127.0.0.1:9222");
  for (let attempt = 0; attempt < 60; attempt++) {
    page = browser.contexts().flatMap((context) => context.pages()).find((candidate) => {
      try {
        const host = new URL(candidate.url()).hostname;
        return host === "tauri.localhost" || host === "localhost";
      } catch {
        return false;
      }
    });
    if (page) break;
    await delay(500);
  }
  if (!page) throw new Error("Native Tauri WebView page not found");
  page.setDefaultTimeout(15000);
  await page.getByRole("heading", { name: "войти по email" }).waitFor();
  await screenshot("01-login");

  await page.getByRole("button", { name: "продолжить", exact: true }).click();
  await page.getByText("Введите корректный email.", { exact: true }).waitFor();
  await screenshot("02-login-validation");

  await page.getByLabel("Email", { exact: true }).fill("ui-review@example.com");
  await page.getByRole("button", { name: "продолжить", exact: true }).click();
  await page.getByRole("heading", { name: "введите код", exact: true }).waitFor();
  await screenshot("03-otp");

  await page.getByLabel("Шестизначный код", { exact: true }).fill("123456");
  await page.getByRole("button", { name: "подтвердить", exact: true }).click();
  await page.getByRole("heading", { name: "PrettyLisaVPN", exact: true }).waitFor();
  await page.getByRole("heading", { name: "Куда подключиться", exact: true }).waitFor();
  await page.getByRole("heading", { name: "Not connected", exact: true }).waitFor();
  await screenshot("04-home");

  await page.getByRole("navigation").getByRole("link", { name: "устройства", exact: true }).click();
  await page.getByRole("heading", { name: "Windows device", exact: true }).waitFor();
  await page.getByRole("heading", { name: "Android phone", exact: true }).waitFor();
  await screenshot("05-devices");
  await page.getByRole("button", { name: "отозвать доступ", exact: true }).click();
  await page.getByRole("alertdialog").waitFor();
  await screenshot("06-device-confirmation");
  await page.getByRole("button", { name: "отмена", exact: true }).click();

  await page.getByRole("navigation").getByRole("link", { name: "о приложении", exact: true }).click();
  await page.getByRole("heading", { name: "о приложении", exact: true }).waitFor();
  await page.getByText("0.1.0", { exact: true }).waitFor();
  await screenshot("07-about");
  nativeWindow("VerifyFixed", "08-about-fixed");
  await page.getByRole("button", { name: "Свернуть", exact: true }).click();
  await delay(300);
  nativeWindow("VerifyMinimized", "unused");
  nativeWindow("Restore", "10-about-after-minimize");
  await page.getByRole("button", { name: "Закрыть", exact: true }).click();
  for (let attempt = 0; attempt < 50 && app.exitCode === null; attempt++) {
    await delay(100);
  }
  if (app.exitCode === null) throw new Error("Native Close did not exit the app");
  fs.writeFileSync(path.join(output, "capture-result.json"), JSON.stringify({
    status: "passed",
    nativeWindows: true,
    nativeWindowChrome: true,
    windowControlsVerified: ["custom minimize", "restore", "custom close", "fixed size", "native rounded region"],
    syntheticApi: true,
    vpnTested: false,
    screenshots: fs.readdirSync(output).filter((name) => name.endsWith(".png")),
  }, null, 2));
  // Transport only synthetic fixture screenshots through the GitHub connector.
  for (const name of fs.readdirSync(output).filter((file) =>
    file.endsWith(".png") && !file.endsWith("-content.png"))) {
    console.log("UI_SCREENSHOT " + JSON.stringify({
      name,
      base64: fs.readFileSync(path.join(output, name)).toString("base64"),
    }));
  }
}

main().catch(async (error) => {
  console.error(error);
  if (page) {
    await screenshot("failure").catch(() => {});
    fs.writeFileSync(path.join(output, "failure-page.txt"), await page.locator("body").innerText().catch(() => ""));
  }
  process.exitCode = 1;
}).finally(async () => {
  if (browser) await browser.close().catch(() => {});
  for (const child of [app, api]) {
    if (child?.pid) spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { timeout: 5000, stdio: "ignore" });
  }
  fs.closeSync(log);
  fs.rmSync(path.join(output, "temporary-webview-profile"), { recursive: true, force: true, maxRetries: 3 });
});
