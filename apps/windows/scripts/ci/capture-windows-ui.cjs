/* eslint @typescript-eslint/no-require-imports: "off" */
/* global console, process, setTimeout, URL, fetch, AbortSignal, require, document, window, getComputedStyle */
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { spawn, spawnSync } = require("node:child_process");
const { chromium } = require("playwright-core");

const evidencePath = process.env.DEVICE_BACKEND_EVIDENCE_PATH;
const deviceEvidence = evidencePath
  ? JSON.parse(fs.readFileSync(evidencePath, "utf8"))
  : null;
const billingEvidencePath = process.env.BILLING_BACKEND_EVIDENCE_PATH;
const billingEvidence = billingEvidencePath
  ? JSON.parse(fs.readFileSync(billingEvidencePath, "utf8"))
  : null;
const accountEmail = deviceEvidence?.account_email || "ui-review@example.com";
const frontendVersion = JSON.parse(
  fs.readFileSync("package.json", "utf8"),
).version;
const webviewProfile = fs.mkdtempSync(
  path.join(os.tmpdir(), "prettylisavpn-ui-"),
);
const output = path.resolve("artifacts/ui-review");
fs.mkdirSync(output, { recursive: true });
if (deviceEvidence)
  fs.copyFileSync(evidencePath, path.join(output, "device-response.json"));
if (billingEvidence)
  fs.copyFileSync(
    billingEvidencePath,
    path.join(output, "billing-response.json"),
  );
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
    deviceEvidence
      ? "Devices replay actual backend HTTP responses from disposable CI PostgreSQL; auth and node agent are simulated. No live account was accessed."
      : "Account, devices and countries are loopback-only synthetic fixtures.",
    "Announcements and acknowledgements use --simulate-messages; real cross-device delivery is not tested.",
    "Primary PNGs capture the real native window, including the custom application title bar.",
    "Extra *-content.png files capture the fixed WebView canvas (only collections scroll).",
    "Tunnel dependencies, keys and session API are synthetic fixtures; no real tunnel was started or verified.",
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
fs.copyFileSync(
  "scripts/ci/billing-fixtures.json",
  path.join(output, "billing-fixtures.json"),
);
const log = fs.openSync(path.join(output, "capture-process.log"), "w");
const api = spawn(
  "python",
  ["scripts/ci/mock-ui-api.py", "--simulate-vpn", "--simulate-messages"],
  {
    stdio: ["ignore", log, log],
  },
);
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
    { encoding: "utf8", timeout: 60000 },
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
    for (const brand of document.querySelectorAll(".product-name")) {
      if (brand.innerText !== "PrettyLisaVPN")
        throw new Error("Product name must preserve PrettyLisaVPN casing");
    }
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
        ".connection-card, .home-workspace, .sidebar, .settings-devices, .subscription-scroll, .payment-choice",
      ),
    ]) {
      if (
        node &&
        ((node.scrollHeight > node.clientHeight + 1 &&
          !node.matches(".connection-card")) ||
          node.scrollWidth > node.clientWidth + 1)
      )
        bad.push(
          `${node.className || node.tagName} (${node.scrollHeight}/${node.clientHeight}, ${node.scrollWidth}/${node.clientWidth})`,
        );
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
  await page.getByRole("heading", { name: "вход по email" }).waitFor();
  const syntheticVpn = await page.evaluate(
    () => document.documentElement.dataset.vpnReview,
  );
  if (syntheticVpn !== "synthetic")
    throw new Error(
      "Review tunnel dependencies must be injected before any VPN action",
    );
  if ((await page.locator("#login-help").innerText()).endsWith("."))
    throw new Error("Login helper must have no trailing dot");
  await page
    .locator(".sidebar-versions")
    .getByText(frontendVersion, { exact: true })
    .waitFor();
  await page
    .locator(".sidebar-versions")
    .getByText(deviceEvidence?.version.application_version || "недоступна", {
      exact: true,
    })
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
  await page.getByRole("heading", { name: "вход по email" }).waitFor();
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

  await page.getByLabel("Email", { exact: true }).fill(accountEmail);
  await page.getByRole("button", { name: "продолжить", exact: true }).click();
  await page
    .getByRole("heading", { name: "введите код", exact: true })
    .waitFor();
  await screenshot("03-otp");

  await page.getByLabel("Шестизначный код", { exact: true }).fill("123456");
  await page.getByRole("button", { name: "подтвердить", exact: true }).click();
  const update = page.getByRole("dialog", {
    name: "стало удобнее",
    exact: true,
  });
  await update.waitFor();
  const beforeRead = await (
    await fetch("http://127.0.0.1:8000/ui-review/message-receipts")
  ).json();
  if (beforeRead.acknowledged !== 0 || beforeRead.attempts !== 0)
    throw new Error("Showing a message must not acknowledge it");
  await screenshot("03a-account-message");
  await update.getByRole("button", { name: "понятно", exact: true }).click();
  await update.getByRole("alert").waitFor();
  await screenshot("03b-message-confirmation-error");
  await update.getByRole("button", { name: "понятно", exact: true }).click();
  const promotion = page.getByRole("dialog", {
    name: "специальное предложение",
    exact: true,
  });
  await promotion.waitFor();
  await screenshot("03c-account-promotion");
  await promotion
    .getByRole("button", { name: "посмотреть подписку", exact: true })
    .click();
  await promotion.waitFor({ state: "detached" });
  await page.getByRole("heading", { name: "подписка", exact: true }).waitFor();
  const afterRead = await (
    await fetch("http://127.0.0.1:8000/ui-review/message-receipts")
  ).json();
  if (afterRead.acknowledged !== 2 || afterRead.attempts !== 3)
    throw new Error(
      "Message acknowledgements must be confirmed before navigation",
    );
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "главная", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "PrettyLisaVPN", exact: true })
    .waitFor();
  await page
    .getByRole("heading", { name: "куда подключиться", exact: true })
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
  await page.getByText("203.0.113.42", { exact: true }).waitFor();
  await page.getByText("PREMIUM ⭐", { exact: true }).waitFor();
  await page
    .getByRole("heading", { name: "что защищаем", exact: true })
    .waitFor();
  for (const name of [/только выбранные сайты/, /кроме выбранных сайтов/]) {
    if (!(await page.getByRole("radio", { name }).isDisabled()))
      throw new Error("Future traffic modes must be disabled");
  }
  if ((await page.locator(".account-summary").innerText()).includes("статус"))
    throw new Error("Account status must be removed");
  await screenshot("04-home");
  const combo = page.getByRole("combobox");
  await combo.click();
  await page.getByRole("listbox").waitFor();
  if (
    (await page
      .getByRole("group", { name: "топ", exact: true })
      .getByRole("option")
      .count()) !== 3
  )
    throw new Error("Expected top three countries");
  await screenshot("04a-home-dropdown");
  await page
    .getByRole("group", { name: "все страны", exact: true })
    .getByRole("option", { name: /Германия/ })
    .click();
  if (!(await combo.textContent()).includes("Германия"))
    throw new Error("Country choice failed");
  await screenshot("04b-home-country");
  await page.getByRole("button", { name: "CONNECT", exact: true }).click();
  await page.getByRole("heading", { name: "Connected", exact: true }).waitFor();
  await page.getByText("198.51.100.42", { exact: true }).waitFor();
  await page.getByLabel("способ подключения", { exact: true }).waitFor();
  const metadata = await page
    .getByLabel("способ подключения", { exact: true })
    .evaluate((node) => ({
      color: getComputedStyle(node).color,
      size: parseFloat(getComputedStyle(node).fontSize),
      text: node.innerText,
    }));
  if (
    !metadata.text.includes("192.0.2.20:51820") ||
    metadata.size > 12 ||
    !metadata.color.startsWith("rgba(")
  )
    throw new Error("Expected muted runtime connection facts");
  await screenshot("04c-home-connected-fixture");
  await page.getByText("параметры подключения", { exact: true }).click();
  await page.getByText("публичный ключ сервера", { exact: true }).waitFor();
  await page.locator(".connection-info dd").first().scrollIntoViewIfNeeded();
  await screenshot("04d-home-connection-details-fixture");
  await page.getByText("параметры подключения", { exact: true }).click();
  await page.getByRole("button", { name: "DISCONNECT", exact: true }).click();
  await page
    .getByRole("heading", { name: "Not connected", exact: true })
    .waitFor();
  if (await page.getByLabel("способ подключения", { exact: true }).count())
    throw new Error("Connection facts must disappear after disconnect");

  await page
    .getByRole("navigation")
    .getByRole("link", { name: "настройки", exact: true })
    .click();
  await page.getByRole("heading", { name: "настройки", exact: true }).waitFor();
  await screenshot("05-settings");
  async function billingScenario(scenario) {
    const response = await fetch(
      "http://127.0.0.1:8000/ui-review/billing-scenario",
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ scenario }),
      },
    );
    if (!response.ok) throw new Error("Billing fixture scenario failed");
  }
  async function confirmBilling() {
    const response = await fetch(
      "http://127.0.0.1:8000/ui-review/billing-confirm",
      { method: "POST" },
    );
    if (!response.ok) throw new Error("Billing fixture confirmation failed");
    await page.getByRole("button", { name: "обновить", exact: true }).click();
    await page.getByText("автопродление включено", { exact: true }).waitFor();
    await page
      .getByRole("button", { name: "отменить подписку", exact: true })
      .waitFor();
  }
  async function lastBillingCommand() {
    const response = await fetch(
      "http://127.0.0.1:8000/ui-review/billing-last-command",
    );
    if (!response.ok) throw new Error("Billing command fixture failed");
    return response.json();
  }
  await billingScenario("free");
  await page.getByRole("link", { name: /подписка/ }).click();
  await page.getByRole("heading", { name: "подписка", exact: true }).waitFor();
  await page
    .getByRole("button", { name: "оформить подписку", exact: true })
    .waitFor();
  if (
    (await page
      .getByRole("link", { name: "настройки", exact: true })
      .getAttribute("aria-current")) !== "page"
  )
    throw new Error("Settings must stay active on subscription");
  if (
    (await page
      .getByRole("button", { name: "₽", exact: true })
      .getAttribute("aria-pressed")) !== "true"
  )
    throw new Error("Russia before VPN must prefer RUB");
  if ((await page.getByLabel("цена в рублях").locator("del").count()) !== 1)
    throw new Error("Backend discount must be shown");
  await screenshot("05a-subscription-free");
  await page
    .getByRole("button", { name: "оформить подписку", exact: true })
    .click();
  await page.getByRole("dialog", { name: "как оплатить" }).waitFor();
  const paymentOptions = page.getByRole("dialog").getByRole("radio");
  if (
    (await paymentOptions.count()) !== 4 ||
    (await paymentOptions.first().inputValue()) !== "MIR" ||
    !(await paymentOptions.first().isChecked())
  )
    throw new Error("RUB must prefer MIR in the four-option payment choice");
  if ((await page.getByRole("dialog").locator("svg").count()) !== 4)
    throw new Error("Every payment option must have an icon");
  if (await lastBillingCommand())
    throw new Error("Opening payment choice must not create an operation");
  await screenshot("05aa-payment-choice-rub");
  await page.getByRole("button", { name: "назад", exact: true }).click();
  await page.getByRole("button", { name: "$", exact: true }).click();
  await page
    .getByRole("button", { name: "оформить подписку", exact: true })
    .click();
  await page.getByRole("dialog", { name: "как оплатить" }).waitFor();
  if (
    (await paymentOptions.first().inputValue()) !== "BANK_CARD" ||
    !(await paymentOptions.first().isChecked())
  )
    throw new Error("USD must prefer bank cards");
  await screenshot("05ab-payment-choice-usd");
  await page.keyboard.press("Escape");
  await page.getByRole("dialog").waitFor({ state: "hidden" });
  await page.getByRole("button", { name: "₽", exact: true }).click();
  await page
    .getByRole("button", { name: "оформить подписку", exact: true })
    .click();
  await page
    .getByRole("button", { name: "перейти к оплате", exact: true })
    .click();
  await page.waitForFunction(
    () => document.documentElement.dataset.paymentReviewUrl === "opened",
  );
  await page
    .getByText("ожидаем подтверждения платёжного сервиса", { exact: true })
    .waitFor();
  if (
    !(await page
      .getByRole("button", { name: "оформить подписку", exact: true })
      .isDisabled())
  )
    throw new Error("Pending operation must block duplicate checkout");
  await screenshot("05b-subscription-pending");
  await confirmBilling();
  await screenshot("05c-subscription-active");
  const checkoutCommand = await lastBillingCommand();
  if (
    checkoutCommand.action !== "SUBSCRIBE" ||
    checkoutCommand.payment_route !== "MIR"
  )
    throw new Error("Checkout must submit the explicitly confirmed MIR route");
  await page
    .getByRole("button", { name: "продлить подписку", exact: true })
    .click();
  await page.getByRole("dialog", { name: "как оплатить" }).waitFor();
  await page
    .getByRole("radio", { name: "банковская карта", exact: true })
    .locator("..")
    .click();
  await page
    .getByRole("button", { name: "перейти к оплате", exact: true })
    .click();
  await page
    .getByText("ожидаем подтверждения платёжного сервиса", { exact: true })
    .waitFor();
  const renewalCommand = await lastBillingCommand();
  if (
    renewalCommand.action !== "RENEW" ||
    renewalCommand.payment_route !== "BANK_CARD"
  )
    throw new Error("Renewal must submit its own confirmed payment route");
  await confirmBilling();
  await page
    .getByRole("button", { name: "изменить способ оплаты", exact: true })
    .click();
  await page
    .getByText("ожидаем подтверждения платёжного сервиса", { exact: true })
    .waitFor();
  await confirmBilling();
  await page
    .getByRole("button", { name: "отменить подписку", exact: true })
    .click();
  await page.getByRole("dialog").waitFor();
  await screenshot("05d-subscription-cancel-confirmation");
  await page.getByRole("button", { name: "да, отменить", exact: true }).click();
  await page.getByText("автопродление отключено", { exact: true }).waitFor();
  if (
    await page.getByText("тестовый способ •••• 4242", { exact: true }).count()
  )
    throw new Error("Canceled subscription must detach payment method");
  await page
    .getByRole("button", { name: "продлить подписку", exact: true })
    .waitFor();
  await screenshot("05e-subscription-canceled");
  await billingScenario("error");
  await page.getByRole("button", { name: "обновить", exact: true }).click();
  await page.getByRole("alert").waitFor();
  if (await page.getByLabel("цена в рублях").count())
    throw new Error(
      "Unavailable backend must not show stale or invented prices",
    );
  await screenshot("05f-subscription-unavailable");
  if (billingEvidence) {
    for (const [scenario, overview] of Object.entries(
      billingEvidence.snapshots,
    )) {
      await billingScenario(`server-${scenario}`);
      await page.getByRole("button", { name: "обновить", exact: true }).click();
      await page
        .getByText(
          "оплата пока недоступна. данные подписки доступны для просмотра.",
          { exact: true },
        )
        .waitFor();
      const offer = overview.offers[0];
      if (offer) {
        for (const [code, label] of [
          ["RUB", "цена в рублях"],
          ["USD", "цена в долларах"],
        ]) {
          const amount = offer.prices[code].amount_minor;
          const formatted = new Intl.NumberFormat("ru-RU", {
            style: "currency",
            currency: code,
            minimumFractionDigits: amount % 100 === 0 ? 0 : 2,
            maximumFractionDigits: 2,
          }).format(amount / 100);
          const actual = await page
            .getByLabel(label)
            .locator("strong")
            .textContent();
          if (actual.replace(/\s/g, "") !== formatted.replace(/\s/g, ""))
            throw new Error("Native price differs from recorded backend");
        }
      }
      if (scenario === "platinum") {
        await page
          .getByText(
            "тариф назначен вручную. продление через оплату недоступно.",
            { exact: true },
          )
          .waitFor();
        if (await page.getByLabel("цена в рублях").count())
          throw new Error("Manual Platinum must not be sold");
      } else {
        const action = page.getByRole("button", {
          name:
            overview.plan === "FREE"
              ? "оформить подписку"
              : "продлить подписку",
          exact: true,
        });
        if (!(await action.isDisabled()))
          throw new Error("Read-only payment action is enabled");
      }
      if (scenario === "active-unknown")
        await page
          .getByText("стоимость подписки: сведения недоступны", { exact: true })
          .waitFor();
      if (scenario === "expired")
        await page
          .getByText("платный доступ не активен", { exact: true })
          .waitFor();
      if (await page.getByRole("dialog").count())
        throw new Error("Read-only overview opened checkout");
      await screenshot(`05g-billing-backend-${scenario}`);
    }
    const evidence = await (
      await fetch("http://127.0.0.1:8000/ui-review/billing-readonly-evidence")
    ).json();
    if (evidence.operation_attempts !== 0)
      throw new Error("Read-only overview attempted a payment operation");
  }
  await page.getByRole("link", { name: "← настройки", exact: true }).click();
  await page.getByRole("heading", { name: "настройки", exact: true }).waitFor();
  await page.getByRole("link", { name: "главная", exact: true }).click();
  await page.getByRole("combobox").waitFor();
  await page.waitForFunction(() =>
    document
      .querySelector('[role="combobox"]')
      ?.textContent.includes("Германия"),
  );
  await page.getByRole("link", { name: "настройки", exact: true }).click();
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
  const devicesPage = page.locator(".devices-page");
  if ((await devicesPage.locator(".eyebrow").count()) !== 0)
    throw new Error("Devices must not have an account eyebrow");
  if ((await devicesPage.locator(".devices-limit br").count()) !== 1)
    throw new Error("Device instructions must have a sentence break");
  if ((await devicesPage.locator(".device-identity").count()) !== 2)
    throw new Error("Each device needs a stable identifier");
  if ((await devicesPage.locator(".device-dates time").count()) !== 3)
    throw new Error(
      "Registration and optional login timestamps must be separate",
    );
  await devicesPage
    .getByText("последний вход: нет данных", { exact: false })
    .waitFor();
  await screenshot("06-devices");
  await page
    .getByRole("button", { name: "отозвать доступ", exact: true })
    .click();
  await page.getByRole("alertdialog").waitFor();
  await screenshot("07-device-confirmation");
  if (deviceEvidence) {
    await page
      .getByRole("button", { name: "да, отозвать", exact: true })
      .click();
    await devicesPage.getByText("отозвано", { exact: true }).waitFor();
    await screenshot("07b-device-revoked");
  } else {
    await page.getByRole("button", { name: "отмена", exact: true }).click();
  }

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
  const about = page.locator(".about-page");
  if ((await about.locator(".eyebrow").count()) !== 0)
    throw new Error("About must not have an application eyebrow");
  if ((await about.getByText("окружение", { exact: true }).count()) !== 0)
    throw new Error("About must not expose the environment");
  await about.getByText("frontend", { exact: true }).waitFor();
  await about.getByText("backend", { exact: true }).waitFor();
  await about.getByRole("heading", { name: "faq", exact: true }).waitFor();
  await about
    .getByText("inspired by love of my life, Lisa", { exact: true })
    .waitFor();
  await about.getByRole("button", { name: "написать в поддержку" }).click();
  const support = page.getByRole("dialog", { name: "помощь и поддержка" });
  await support.waitFor();
  await screenshot("08a-support-empty");
  await support
    .getByRole("textbox", { name: "тема", exact: true })
    .fill("не удаётся подключиться");
  await support
    .getByRole("textbox", { name: "описание проблемы", exact: true })
    .fill("после выбора страны подключение прерывается. помогите разобраться.");
  await support
    .getByRole("textbox", { name: "email для ответа", exact: true })
    .fill(accountEmail);
  await support
    .locator('input[type="file"]')
    .setInputFiles(path.join(output, "08-about.png"));
  await support.getByText("08-about.png", { exact: true }).waitFor();
  if (
    await support
      .getByRole("button", { name: "отправить", exact: true })
      .isDisabled()
  )
    throw new Error("Configured support sender must allow submission");
  await screenshot("08b-support-filled");
  await support.getByText("что будет приложено", { exact: true }).click();
  const technical = await support.locator("pre").innerText();
  if (
    !technical.includes('"frontend_version"') ||
    technical.includes('"accessToken"') ||
    technical.includes('"private_key"')
  )
    throw new Error("Support diagnostics must use a safe whitelist");
  await screenshot("08c-support-diagnostics");
  await support.getByText("что будет приложено", { exact: true }).click();
  await support.getByRole("button", { name: "отправить", exact: true }).click();
  await support.getByRole("alert").waitFor();
  await screenshot("08d-support-network-retry");
  await support.getByRole("button", { name: "отправить", exact: true }).click();
  await support
    .getByRole("heading", { name: "обращение принято", exact: true })
    .waitFor();
  await screenshot("08e-support-accepted");
  await support
    .getByRole("button", { name: "проверить статус", exact: true })
    .click();
  await support
    .getByText("почтовый сервер принял письмо", { exact: true })
    .waitFor();
  await screenshot("08f-support-status");
  const supportEvidence = await (
    await fetch("http://127.0.0.1:8000/ui-review/support-evidence")
  ).json();
  if (supportEvidence.requests !== 1 || supportEvidence.post_attempts !== 1)
    throw new Error(
      "Lost support response must recover without another ticket",
    );
  await page.keyboard.press("Escape");
  await support.waitFor({ state: "detached" });
  await about.getByRole("button", { name: "написать в поддержку" }).click();
  if (
    (await support
      .getByRole("textbox", { name: "тема", exact: true })
      .inputValue()) !== ""
  )
    throw new Error("Support draft must not survive closing");
  await support.getByRole("button", { name: "закрыть обращение" }).click();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "настройки", exact: true })
    .click();
  await page.getByRole("button", { name: /выйти/ }).click();
  await page.getByRole("heading", { name: "вход по email" }).waitFor();
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
        subscriptionBillingUiVerified: true,
        paymentChoiceVerified: true,
        aboutSupportUiVerified: true,
        accountMessagesUiVerified: true,
        realAccountMessageSyncTested: false,
        supportEmailDeliveryTested: false,
        realPaymentsTested: false,
        backendVersionFallbackVerified: !deviceEvidence,
        recordedDeviceBackendEvidence: deviceEvidence,
        recordedBillingBackendEvidence: billingEvidence,
        readonlyBillingBackendVerified: Boolean(billingEvidence),
        liveAccountAccessed: false,
        fontFamily: "Rubik",
        fontWeightsVerified: [400, 600, 700],
        syntheticApi: true,
        vpnTested: false,
        injectedVpnFixture: true,
        connectionDetailsVerifiedWithFixtures: true,
        trafficModeUiVerified: true,
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
      console.error(
        "SYNTHETIC_UI_FAILURE " +
          (await page
            .locator("body")
            .innerText()
            .catch(() => "unavailable")),
      );
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
