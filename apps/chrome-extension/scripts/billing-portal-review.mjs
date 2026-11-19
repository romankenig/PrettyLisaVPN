import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import assert from "node:assert/strict";
import { build } from "../../../sites/public-website/scripts/build.mjs";
import { createPreviewServer } from "../../../sites/public-website/scripts/preview.mjs";
import { portalCopy } from "../../../sites/public-website/src/portal-copy.mjs";

// Real rendered website, simulated account/provider API. No merchant credentials or charges.
await build();
const server = createPreviewServer();
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ headless: true });
const output = "review/billing";
await mkdir(output, { recursive: true });
const account = "11111111-1111-4111-8111-111111111111";
const offer = "22222222-2222-4222-8222-222222222222";
const operationID = "33333333-3333-4333-8333-333333333333";
let authenticated = false,
  state = "FREE",
  status = "PENDING",
  operation = null;
let loseResponse = false;
let overviewAvailable = true;
let providerMode = "LIVE",
  offersAvailable = true;
const commands = [];
const errors = [];
const overview = () => ({
  account_id: account,
  email: "subscriber@example.test",
  billing: {
    revision: "fixture-revision",
    provider_mode: providerMode,
    payment_operations_available: providerMode === "LIVE",
    plan:
      state === "PLATINUM" ? "PLATINUM" : state === "FREE" ? "FREE" : "PREMIUM",
    status:
      state === "FREE" ? "FREE" : state === "CANCELED" ? "CANCELED" : "ACTIVE",
    paid_until: state === "FREE" ? null : "2026-12-06T10:00:00Z",
    auto_renew: state === "ACTIVE",
    current_price:
      state === "FREE" || state === "PLATINUM"
        ? null
        : { amount_minor: 19900, currency: "RUB" },
    payment_method:
      state === "ACTIVE"
        ? { kind: "SBP", label: "СБП · банковский счёт" }
        : null,
    next_charge_at: state === "ACTIVE" ? "2026-12-06T10:00:00Z" : null,
    next_charge_price:
      state === "ACTIVE" ? { amount_minor: 19900, currency: "RUB" } : null,
    new_contract_required: state !== "ACTIVE",
    pending_operation_id:
      operation && status === "PENDING" ? operation.id : null,
    payment_routes: [
      { id: "SBP", currencies: ["RUB"], recurring_currencies: ["RUB"] },
    ],
    offers: !offersAvailable
      ? []
      : [
          {
            id: offer,
            prices: {
              RUB: { amount_minor: state === "FREE" ? 19900 : 29900 },
              USD: { amount_minor: 399 },
            },
          },
        ],
    actions:
      providerMode !== "LIVE"
        ? []
        : state === "ACTIVE"
          ? ["CANCEL"]
          : ["SUBSCRIBE"],
  },
});
try {
  const page = await browser.newPage({
    viewport: { width: 1280, height: 1000 },
    locale: "ru-RU",
  });
  page.on("pageerror", (error) => errors.push(error.message));
  let catalogAvailable = true;
  await page.route("**/api/billing/catalog", (route) =>
    route.fulfill({
      status: catalogAvailable ? 200 : 503,
      json: {
        offers: [
          {
            id: offer,
            plan: "PREMIUM",
            period: "MONTH",
            prices: {
              RUB: { amount_minor: 12345, original_amount_minor: 15000 },
              USD: { amount_minor: 789, original_amount_minor: 999 },
            },
          },
        ],
      },
    }),
  );
  // Check both initial themes and live changes under the production-equivalent CSP.
  for (const initial of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme: initial });
    await page.goto(origin + "/");
    assert.equal(await page.title(), "PrettyLisaVPN");
    for (const theme of [initial, initial === "light" ? "dark" : "light"]) {
      await page.emulateMedia({ colorScheme: theme });
      await page.waitForFunction(
        (expected) =>
          globalThis.document
            .querySelector('link[rel="icon"]')
            ?.getAttribute("href") === `/assets/favicon-${expected}.svg`,
        theme,
      );
    }
  }
  await page.emulateMedia({ colorScheme: "light" });
  for (const language of ["", "en", "de", "fr", "es", "zh"]) {
    for (const width of [320, 390, 1280]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(origin + (language ? `/${language}/` : "/"));
      await page.waitForFunction(() =>
        globalThis.document
          .querySelector('[data-price="RUB"]')
          ?.textContent.includes("123"),
      );
      assert.match(
        await page.locator('[data-reference-price="RUB"]').textContent(),
        /150/,
      );
      assert.equal(await page.locator('[data-price="RUB"]').isVisible(), true);
      assert.equal(
        await page.locator('[data-free-currency="RUB"]').isVisible(),
        true,
      );
      assert.equal(await page.locator(".document-button").count(), 4);
      assert.equal(await page.locator(".device-pair").count(), 2);
      assert.equal(
        await page
          .locator("figcaption, .eyebrow, [data-price-reference-note]")
          .count(),
        0,
      );
      assert.equal(
        await page.evaluate(
          () =>
            globalThis.document.documentElement.scrollWidth <=
            globalThis.innerWidth,
        ),
        true,
      );
      if (!language && width === 1280)
        for (const section of ["features", "download"])
          await page
            .locator(`#${section}`)
            .screenshot({ path: `${output}/00-${section}-desktop.png` });
      if (!language && width === 390)
        for (const section of ["features", "download"])
          await page
            .locator(`#${section}`)
            .screenshot({ path: `${output}/00-${section}-mobile.png` });
      if (!language && width === 1280)
        await page
          .locator("#pricing")
          .screenshot({ path: `${output}/00-pricing-desktop.png` });
      await page.getByText("$ USD", { exact: true }).click();
      assert.equal(await page.locator('[data-price="USD"]').isVisible(), true);
      assert.equal(await page.locator('[data-price="RUB"]').isVisible(), false);
      assert.equal(
        await page.locator('[data-free-currency="USD"]').isVisible(),
        true,
      );
      assert.match(
        await page.locator('[data-price="USD"]').textContent(),
        /7[.,]89/,
      );
      if (!language && width === 390)
        await page
          .locator("#pricing")
          .screenshot({ path: `${output}/00-pricing-mobile.png` });
    }
  }
  catalogAvailable = false;
  await Promise.all([
    page.waitForResponse("**/api/billing/catalog"),
    page.goto(origin + "/"),
  ]);
  assert.match(
    await page.locator('[data-price="RUB"]').textContent(),
    /123[.,]45/,
  );
  assert.equal(await page.locator("[data-price-reference-note]").count(), 0);
  await page.evaluate(() => globalThis.localStorage.clear());
  await Promise.all([
    page.waitForResponse("**/api/billing/catalog"),
    page.reload(),
  ]);
  assert.match(await page.locator('[data-price="RUB"]').textContent(), /399/);
  assert.match(
    await page.locator('[data-reference-price="RUB"]').textContent(),
    /499/,
  );
  await page
    .locator("#pricing")
    .screenshot({ path: `${output}/00-pricing-offline.png` });
  await page.getByText("$ USD", { exact: true }).click();
  assert.match(await page.locator('[data-price="USD"]').textContent(), /5/);
  assert.match(
    await page.locator('[data-reference-price="USD"]').textContent(),
    /7/,
  );
  catalogAvailable = true;
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.route("**/api/web/billing/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace(
      "/api/web/billing",
      "",
    );
    const reply = (value, code = 200) =>
      route.fulfill({
        status: code,
        contentType: "application/json",
        body: JSON.stringify(value),
      });
    if (path === "/request-otp") return reply({ status: "accepted" }, 202);
    if (path === "/login" || path === "/exchange") {
      authenticated = true;
      return reply({ status: "authenticated" });
    }
    if (!authenticated) return reply({ error: { code: "AUTH_INVALID" } }, 401);
    if (path === "/overview")
      return overviewAvailable
        ? reply(overview())
        : reply({ error: { code: "BILLING_UNAVAILABLE" } }, 503);
    if (path === "/operations") {
      const command = route.request().postDataJSON();
      commands.push(command);
      assert.equal(command.currency, "RUB");
      assert.equal(command.amount_minor, undefined);
      assert.equal(command.user_id, undefined);
      operation = {
        id: operationID,
        status,
        redirect_url: "https://pay.platega.io/subscription/" + operationID,
      };
      if (command.action === "CANCEL") {
        state = "CANCELED";
        status = "SUCCEEDED";
        operation.status = status;
      }
      if (loseResponse) {
        loseResponse = false;
        return route.abort("failed");
      }
      return reply(operation);
    }
    if (path === "/operations/" + operationID) {
      if (status === "SUCCEEDED" && state === "FREE") state = "ACTIVE";
      return reply({ ...operation, status });
    }
    return reply({ error: { code: "NOT_FOUND" } }, 404);
  });
  // Unavailable checkout stays on the offer: no dead-end page or payment POST.
  providerMode = "DISABLED";
  offersAvailable = false;
  catalogAvailable = false;
  await page.goto(origin + "/");
  await page.getByText("$ USD", { exact: true }).click();
  await page.locator('.price-option[data-currency="USD"] .button').click();
  await page.getByLabel("Электронная почта").fill("subscriber@example.test");
  await page.getByRole("button", { name: "получить код" }).click();
  await page.getByLabel("Код из письма").fill("123456");
  await page.getByRole("button", { name: "войти", exact: true }).click();
  await page.locator("[data-payment-unavailable]").waitFor();
  assert.equal(new URL(page.url()).pathname, "/account/");
  assert.equal(new URL(page.url()).searchParams.get("currency"), "USD");
  assert.equal(
    await page
      .getByRole("button", { name: "оплатить", exact: true })
      .isDisabled(),
    true,
  );
  assert.equal(commands.length, 0);
  for (const language of ["", "en", "de", "fr", "es", "zh"]) {
    for (const width of [320, 390, 1280]) {
      await page.setViewportSize({ width, height: 1000 });
      const prefix = language ? `/${language}` : "";
      await page.goto(origin + prefix + "/account/unavailable/?currency=RUB");
      await page.locator("[data-payment-unavailable]").waitFor();
      assert.equal(new URL(page.url()).pathname, prefix + "/account/");
      assert.equal(
        await page.locator("[data-purchase-offer] > .button").isDisabled(),
        true,
      );
      assert.equal(
        await page.evaluate(
          () =>
            globalThis.document.documentElement.scrollWidth <=
            globalThis.innerWidth,
        ),
        true,
      );
    }
  }
  await page.goto(origin + "/account/success/?preview=1&currency=USD");
  await page.locator("[data-payment-unavailable]").waitFor();
  assert.equal(new URL(page.url()).pathname, "/account/");
  assert.equal(new URL(page.url()).searchParams.has("preview"), false);
  assert.equal(
    await page.locator(".portal-success-icon, .portal-preview-label").count(),
    0,
  );
  const privatePage = await browser.newPage();
  await privatePage.addInitScript(() => {
    Object.defineProperty(globalThis, "localStorage", {
      get() {
        throw new Error("Storage unavailable");
      },
    });
  });
  let privateMutations = 0;
  await privatePage.route("**/api/web/billing/**", (route) => {
    if (route.request().method() === "POST") privateMutations++;
    return route.fulfill({ json: overview() });
  });
  await privatePage.goto(origin + "/account/");
  await privatePage.locator("[data-payment-unavailable]").waitFor();
  assert.equal(privateMutations, 0);
  await privatePage.close();
  offersAvailable = true;
  for (const [mode, currency] of [
    ["SANDBOX", "RUB"],
    ["LIVE", "USD"],
  ]) {
    providerMode = mode;
    await page.goto(origin + "/account/?currency=" + currency);
    await page.locator("[data-payment-unavailable]").waitFor();
    assert.equal(
      await page.locator("[data-purchase-offer] > .button").isDisabled(),
      true,
    );
    assert.equal(commands.length, 0);
  }
  // Single Pay action opens the provider in the SAME tab; consent is on the offer.
  providerMode = "LIVE";
  let providerVisits = 0;
  const checkoutURL = "https://pay.platega.io/subscription/" + operationID;
  await page.route("https://pay.platega.io/**", (route) => {
    providerVisits++;
    return route.fulfill({
      contentType: "text/html",
      body: "<h1>Provider checkout fixture</h1>",
    });
  });
  for (const language of ["", "en", "de", "fr", "es", "zh"]) {
    for (const width of [320, 390, 1280]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(origin + (language ? `/${language}` : "") + "/account/");
      await page.getByRole("checkbox").waitFor();
      assert.equal(
        await page.locator("[data-purchase-offer] > .button").isDisabled(),
        true,
      );
      await page.getByRole("checkbox").check();
      assert.equal(
        await page.locator("[data-purchase-offer] > .button").isEnabled(),
        true,
      );
      assert.equal(
        await page.evaluate(
          () =>
            globalThis.document.documentElement.scrollWidth <=
            globalThis.innerWidth,
        ),
        true,
      );
      if (!language && [390, 1280].includes(width))
        await page.screenshot({
          path: `${output}/direct-checkout-${width}.png`,
          fullPage: true,
        });
    }
  }
  await page.goto(origin + "/account/");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "оплатить", exact: true }).click();
  await page.waitForURL(checkoutURL);
  assert.equal(commands.length, 1);
  assert.equal(providerVisits, 1);
  assert.equal(
    page.context().pages().length,
    1,
    "checkout must not require a popup",
  );
  await page.goBack();
  await page.getByRole("button", { name: "проверить оплату" }).waitFor();
  assert.equal(providerVisits, 1, "Back must not cause a redirect loop");
  assert.equal(
    await page
      .getByRole("link", { name: "открыть оплату platega" })
      .getAttribute("target"),
    null,
  );
  status = "SUCCEEDED";
  await page.getByRole("button", { name: "проверить оплату" }).click();
  await page.getByRole("heading", { name: "всё получилось" }).waitFor();
  await page.getByRole("button", { name: "управлять подпиской" }).click();
  await page.getByText(portalCopy.ru.sbpAccount, { exact: true }).waitFor();
  assert.equal(
    await page.locator("[data-purchase-offer]").count(),
    0,
    "active contract keeps its fixed price",
  );
  await page
    .getByRole("button", { name: "отвязать счёт и отключить продление" })
    .click();
  await page
    .getByRole("button", {
      name: "отвязать и отключить продление",
      exact: true,
    })
    .click();
  await page.getByRole("heading", { name: "всё получилось" }).waitFor();
  await page.getByRole("button", { name: "управлять подпиской" }).click();
  await page.getByText("автопродление отключено.", { exact: false }).waitFor();
  assert.match(await page.locator(".portal-price strong").textContent(), /299/);
  // Lost POST response recovers the accepted operation and redirects without a new POST.
  state = "FREE";
  status = "PENDING";
  operation = null;
  await page.goto(origin + "/account/");
  await page.getByRole("checkbox").check();
  loseResponse = true;
  await page.getByRole("button", { name: "оплатить", exact: true }).click();
  await page.getByRole("alert").waitFor();
  const afterLostResponse = commands.length;
  await page.reload();
  await page.waitForURL(checkoutURL);
  assert.equal(commands.length, afterLostResponse);
  await page.goto(origin + "/account/unavailable/");
  await page.getByRole("button", { name: "проверить оплату" }).waitFor();
  assert.equal(await page.locator("[data-payment-unavailable]").count(), 0);
  status = "FAILED";
  await page.getByRole("button", { name: "проверить оплату" }).click();
  await page.getByRole("heading", { name: "оплата не завершена" }).waitFor();
  await page.getByRole("button", { name: "попробовать снова" }).click();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "оплатить", exact: true }).click();
  await page.getByRole("heading", { name: "оплата не завершена" }).waitFor();
  await page.getByRole("button", { name: "попробовать снова" }).click();
  // An unknown operation without a URL must never fabricate one or make a new charge.
  status = "PENDING";
  operation = { id: operationID, status, redirect_url: null };
  const beforeUnknown = commands.length;
  await page.reload();
  await page.getByRole("button", { name: "проверить оплату" }).waitFor();
  assert.equal(
    await page.getByRole("link", { name: "открыть оплату platega" }).count(),
    0,
  );
  await page.getByRole("button", { name: "проверить оплату" }).click();
  assert.equal(commands.length, beforeUnknown);
  operation = null;
  overviewAvailable = false;
  await page.reload();
  await page.locator("[data-reference-prices]").waitFor();
  assert.equal(
    await page
      .getByRole("button", { name: "оплатить", exact: true })
      .isDisabled(),
    true,
  );
  assert.equal(commands.length, beforeUnknown);
  overviewAvailable = true;
  await page.getByRole("button", { name: "обновить", exact: true }).click();
  await page.getByRole("checkbox").waitFor();
  // Public Chrome downloads share the publisher's verified metadata, across locales.
  await page.route("**/downloads/index.json", (route) =>
    route.fulfill({
      json: {
        schema: 1,
        clients: {
          chrome: {
            version: "0.3.0",
            bytes: 300000,
            sha256: "a".repeat(64),
            url: "https://untrusted.invalid/download",
          },
        },
      },
    }),
  );
  for (const locale of ["ru", "en", "de", "fr", "es", "zh"]) {
    for (const width of [390, 1280]) {
      await page.setViewportSize({ width, height: 844 });
      await page.goto(
        origin + (locale === "ru" ? "" : `/${locale}`) + "/download/chrome/",
      );
      await page.locator("[data-release=chrome]:not([hidden])").waitFor();
      assert.equal(await page.locator("[data-version]").textContent(), "0.3.0");
      assert.equal(
        await page.locator("a[download]").getAttribute("href"),
        "/downloads/chrome-extension.zip",
      );
      assert.equal(await page.locator(".setup li").count(), 3);
      assert.equal(await page.locator(".download-screen").count(), 0);
      assert.ok(
        await page.evaluate(
          () =>
            globalThis.document.documentElement.scrollWidth <=
            globalThis.document.documentElement.clientWidth,
        ),
        `Chrome download ${locale} at ${width}px must not overflow`,
      );
      await page.screenshot({
        path: `${output}/chrome-download-${locale}-${width}.png`,
        fullPage: true,
      });
    }
  }
  assert.deepEqual(errors, []);
  console.log(
    "Billing portal: OTP, consent, lost-response recovery, verified success, cancellation, fixed price, failure/retry and mobile layout passed.",
  );
} finally {
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
