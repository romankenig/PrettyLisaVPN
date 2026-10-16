/* eslint @typescript-eslint/no-require-imports: "off" */
/* global console, process, setTimeout, URL, fetch, AbortSignal, require, document, window, getComputedStyle */
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { spawn, spawnSync } = require("node:child_process");
const { chromium } = require("playwright-core");

const frontendVersion = JSON.parse(
  fs.readFileSync("package.json", "utf8"),
).version;
const webviewProfile = fs.mkdtempSync(
  path.join(os.tmpdir(), "prettylisavpn-ui-"),
);
const output = path.resolve("artifacts/ui-review");
fs.mkdirSync(output, { recursive: true });
const executable = path.resolve(
  "src-tauri/target/debug/prettylisavpn-windows.exe",
);
fs.copyFileSync(executable, path.join(output, "PrettyLisaVPN-UI-review.exe"));
fs.writeFileSync(
  path.join(output, "README.txt"),
  [
    "PrettyLisaVPN native Windows UI review",
    "Commit: " + (process.env.GITHUB_SHA || "local"),
    "Source head: " + (process.env.PR_HEAD_SHA || "local"),
    "Frontend version: " + frontendVersion,
    "Channel: preview",
    "Run: " + (process.env.GITHUB_RUN_ID || "local"),
    "Attempt: " + (process.env.GITHUB_RUN_ATTEMPT || "local"),
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
fs.copyFileSync(
  "scripts/ci/mock-ui-api.py",
  path.join(output, "mock-ui-api.py"),
);
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
      action,
    ],
    { encoding: "utf8", timeout: 20000 },
  );
  if (result.error || result.status !== 0) {
    throw new Error(
      "Native window " + action + " failed: " + (result.stderr || result.error),
    );
  }
}

async function screenshot(name) {
  await page.evaluate(async () => {
    const sample = "Съешь ещё этих мягких французских булок 0123456789";
    for (const weight of [400, 600, 700]) {
      const faces = await document.fonts.load(weight + ' 16px "Rubik"', sample);
      if (!faces.length || faces.some((face) => face.status !== "loaded"))
        throw new Error("Bundled Rubik failed to load at weight " + weight);
    }
    await document.fonts.ready;
    for (const node of document.querySelectorAll(
      "body, h1, h2, button, input:not([type=radio]):not([type=checkbox]), nav a",
    )) {
      if (!getComputedStyle(node).fontFamily.startsWith("Rubik"))
        throw new Error("Expected Rubik on " + node.tagName);
    }
  });
  await page.evaluate(() => {
    for (const button of document.querySelectorAll("button")) {
      if (getComputedStyle(button).textTransform !== "lowercase")
        throw new Error("Buttons must use lowercase text");
    }
  });
  await page.evaluate(() => window.scrollTo(0, 0));
  await delay(300);
  const layout = await page.evaluate(() => {
    const main = document.querySelector("main");
    const bad = [];
    for (const node of [
      document.documentElement,
      document.body,
      main,
      ...document.querySelectorAll(
        ".connection-card, .home-workspace, .sidebar, .settings-devices",
      ),
    ]) {
      if (
        node &&
        (node.scrollHeight > node.clientHeight + 1 ||
          node.scrollWidth > node.clientWidth + 1)
      )
        bad.push(node.className || node.tagName);
    }
    return bad;
  });
  if (layout.length)
    throw new Error("Content exceeds fixed canvas: " + layout.join(", "));
  await page.getByRole("button", { name: "Свернуть", exact: true }).waitFor();
  await page.getByRole("button", { name: "Закрыть", exact: true }).waitFor();
  nativeWindow("Capture", name);
  await page.screenshot({
    path: path.join(output, name + "-content.png"),
    fullPage: true,
  });
}

async function main() {
  await waitForUrl("http://127.0.0.1:8000/me");
  app = spawn(executable, [], {
    env: {
      ...process.env,
      WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:
        "--remote-debugging-port=9222 --disable-gpu",
      WEBVIEW2_USER_DATA_FOLDER: webviewProfile,
    },
    stdio: ["ignore", log, log],
  });
  await waitForUrl("http://127.0.0.1:9222/json/version");
  browser = await chromium.connectOverCDP("http://127.0.0.1:9222");
  for (let attempt = 0; attempt < 60; attempt++) {
    page = browser
      .contexts()
      .flatMap((context) => context.pages())
      .find((candidate) => {
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
  await page
    .locator(".sidebar-versions")
    .getByText(frontendVersion, { exact: true })
    .waitFor();
  await page
    .locator(".sidebar-versions")
    .getByText("недоступна", { exact: true })
    .waitFor();
  const navigation = await page
    .getByRole("navigation")
    .getByRole("link")
    .evaluateAll((links) =>
      links.map((link) => ({
        label: link.getAttribute("aria-label"),
        text: link.textContent,
        icon: Boolean(link.querySelector("svg")),
      })),
    );
  if (
    JSON.stringify(navigation.map((link) => link.label)) !==
      JSON.stringify(["главная", "настройки", "о приложении"]) ||
    navigation.some((link) => link.text.trim() || !link.icon)
  )
    throw new Error("Expected ordered icon-only navigation");
  const logo = page.locator(".window-titlebar img");
  await logo.waitFor();
  if (!(await logo.evaluate((img) => img.complete && img.naturalWidth > 0)))
    throw new Error("Original lock icon did not load");
  const navItems = page.getByRole("navigation").getByRole("link");
  for (const item of await navItems.all()) {
    if (
      (await item.getAttribute("aria-disabled")) !== "true" ||
      (await item.getAttribute("href")) !== null
    )
      throw new Error("Authentication navigation must be disabled");
    await item.click({ force: true });
  }
  await page.getByRole("heading", { name: "войти по email" }).waitFor();
  await page.getByText("отправим одноразовый код", { exact: true }).waitFor();
  if (await page.getByText("без пароля", { exact: true }).count())
    throw new Error("Passwordless eyebrow must be removed");
  const emailField = page.getByPlaceholder("example@email.com");
  const appearance = await page.evaluate(() => {
    const input = document.querySelector("#login-email");
    const icon = document.querySelector(".window-titlebar img");
    const version = document.querySelector(".sidebar-versions dt");
    const alpha = (color) => {
      return color.startsWith("rgba(")
        ? Number(color.slice(color.lastIndexOf(",") + 1, -1))
        : 1;
    };
    return {
      placeholderAlpha: alpha(getComputedStyle(input, "::placeholder").color),
      inputAlpha: alpha(getComputedStyle(input).color),
      iconBackgroundAlpha: alpha(getComputedStyle(icon).backgroundColor),
      versionAlpha: alpha(getComputedStyle(version).color),
      lowercase: getComputedStyle(document.body).textTransform === "lowercase",
    };
  });
  if (
    appearance.placeholderAlpha > 0.3 ||
    appearance.inputAlpha !== 1 ||
    appearance.iconBackgroundAlpha !== 0 ||
    appearance.versionAlpha >= 1 ||
    !appearance.lowercase
  )
    throw new Error(
      "Unexpected login appearance: " + JSON.stringify(appearance),
    );
  await screenshot("01-login");
  await emailField.fill("User@Example.COM");
  if ((await emailField.inputValue()) !== "User@Example.COM")
    throw new Error("Input must preserve the entered value");
  await screenshot("01b-login-filled");
  await emailField.fill("");

  await page.getByRole("button", { name: "продолжить", exact: true }).click();
  await page.getByText("Введите корректный email.", { exact: true }).waitFor();
  await screenshot("02-login-validation");

  await page.getByLabel("Email", { exact: true }).fill("ui-review@example.com");
  await page.getByRole("button", { name: "продолжить", exact: true }).click();
  await page
    .getByRole("heading", { name: "введите код", exact: true })
    .waitFor();
  await screenshot("03-otp");

  await page.getByLabel("Шестизначный код", { exact: true }).fill("123456");
  await page.getByRole("button", { name: "подтвердить", exact: true }).click();
  await page
    .getByRole("heading", { name: "PrettyLisaVPN", exact: true })
    .waitFor();
  await page
    .getByRole("heading", { name: "Куда подключиться", exact: true })
    .waitFor();
  await page
    .getByRole("heading", { name: "Not connected", exact: true })
    .waitFor();
  for (const item of await page
    .getByRole("navigation")
    .getByRole("link")
    .all()) {
    if (
      !(await item.getAttribute("href")) ||
      (await item.getAttribute("aria-disabled")) === "true"
    )
      throw new Error("Authenticated navigation must be enabled");
  }
  await screenshot("04-home");

  await page
    .getByRole("navigation")
    .getByRole("link", { name: "настройки", exact: true })
    .click();
  await page.getByRole("heading", { name: "настройки", exact: true }).waitFor();
  await screenshot("05-settings");
  await page.getByRole("link", { name: /устройства/ }).click();
  const settingsNav = page
    .getByRole("navigation")
    .getByRole("link", { name: "настройки", exact: true });
  if ((await settingsNav.getAttribute("aria-current")) !== "page")
    throw new Error("Settings must stay active on devices");
  await page
    .getByRole("heading", { name: "Windows device", exact: true })
    .waitFor();
  await page
    .getByRole("heading", { name: "Android phone", exact: true })
    .waitFor();
  await screenshot("06-devices");
  await page
    .getByRole("button", { name: "отозвать доступ", exact: true })
    .click();
  await page.getByRole("alertdialog").waitFor();
  await screenshot("07-device-confirmation");
  await page.getByRole("button", { name: "отмена", exact: true }).click();

  await page
    .getByRole("navigation")
    .getByRole("link", { name: "о приложении", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "о приложении", exact: true })
    .waitFor();
  await page
    .locator("main")
    .getByText(frontendVersion, { exact: true })
    .waitFor();
  await screenshot("08-about");
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "настройки", exact: true })
    .click();
  await page.getByRole("button", { name: /выйти/ }).click();
  await page.getByRole("heading", { name: "войти по email" }).waitFor();
  await screenshot("09-after-logout");
  nativeWindow("VerifyFixed", "10-login-fixed");
  await page.getByRole("button", { name: "Свернуть", exact: true }).click();
  await delay(300);
  nativeWindow("VerifyMinimized", "unused");
  nativeWindow("Restore", "11-login-after-minimize");
  await page.getByRole("button", { name: "Закрыть", exact: true }).click();
  for (let attempt = 0; attempt < 50 && app.exitCode === null; attempt++) {
    await delay(100);
  }
  if (app.exitCode === null)
    throw new Error("Native Close did not exit the app");
  fs.writeFileSync(
    path.join(output, "capture-result.json"),
    JSON.stringify(
      {
        status: "passed",
        nativeWindows: true,
        nativeWindowChrome: true,
        windowControlsVerified: [
          "custom minimize",
          "restore",
          "custom close",
          "fixed size",
          "native rounded region",
        ],
        loginAppearanceVerified: true,
        authNavigationDisabledVerified: true,
        iconNavigationVerified: true,
        settingsDevicesAndLogoutVerified: true,
        backendVersionFallbackVerified: true,
        fontFamily: "Rubik",
        fontWeightsVerified: [400, 600, 700],
        syntheticApi: true,
        vpnTested: false,
        screenshots: fs
          .readdirSync(output)
          .filter((name) => name.endsWith(".png")),
      },
      null,
      2,
    ),
  );
  // Transport only synthetic fixture screenshots through the GitHub connector.
  for (const name of fs
    .readdirSync(output)
    .filter(
      (file) => file.endsWith(".png") && !file.endsWith("-content.png"),
    )) {
    console.log(
      "UI_SCREENSHOT " +
        JSON.stringify({
          name,
          base64: fs.readFileSync(path.join(output, name)).toString("base64"),
        }),
    );
  }
}

main()
  .catch(async (error) => {
    console.error(error);
    if (page) {
      await screenshot("failure").catch(() => {});
      fs.writeFileSync(
        path.join(output, "failure-page.txt"),
        await page
          .locator("body")
          .innerText()
          .catch(() => ""),
      );
    }
    process.exitCode = 1;
  })
  .finally(async () => {
    if (browser) await browser.close().catch(() => {});
    for (const child of [app, api]) {
      if (child?.pid)
        spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
          timeout: 5000,
          stdio: "ignore",
        });
    }
    fs.closeSync(log);
    try {
      fs.rmSync(webviewProfile, {
        recursive: true,
        force: true,
        maxRetries: 10,
        retryDelay: 500,
      });
    } catch {
      // Windows may retain a WebView2 handle after the application exits.
      // This isolated temporary directory is never part of the artifact.
      console.warn(
        "Temporary WebView2 profile cleanup deferred to the runner.",
      );
    }
  });
