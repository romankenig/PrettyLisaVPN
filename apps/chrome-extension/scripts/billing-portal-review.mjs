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
      assert.equal(
        await page.evaluate(
          () =>
            globalThis.document.documentElement.scrollWidth <=
            globalThis.innerWidth,
        ),
        true,
      );
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
  assert.equal(
    await page.locator("[data-price-reference-note]").isVisible(),
    true,
  );
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
  // Follow the actual purchase link, including the selected currency, through OTP.
  providerMode = "DISABLED";
  offersAvailable = false;
  catalogAvailable = false;
  await page.goto(origin + "/");
  await page.getByText("$ USD", { exact: true }).click();
  await page.locator('.price-option[data-currency="USD"] .button').click();
  await page.getByLabel("Электронная почта").waitFor();
  assert.equal(new URL(page.url()).searchParams.get("currency"), "USD");
  assert.match(await page.locator(".portal-price strong").textContent(), /5/);
  await page.screenshot({
    path: `${output}/11-purchase-login.png`,
    fullPage: true,
  });
  await page.getByLabel("Электронная почта").fill("subscriber@example.test");
  await page.getByRole("button", { name: "Получить код" }).click();
  await page.getByLabel("Код из письма").fill("123456");
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await page.getByRole("button", { name: "Оплатить", exact: true }).waitFor();
  assert.match(await page.locator(".portal-price strong").textContent(), /5/);
  await page.screenshot({
    path: `${output}/12-purchase-free-usd.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "Оплатить", exact: true }).click();
  await page.locator("[data-success-preview]").waitFor();
  assert.equal(new URL(page.url()).pathname, "/account/success/");
  assert.equal(new URL(page.url()).searchParams.get("preview"), "1");
  assert.equal(new URL(page.url()).searchParams.get("currency"), "USD");
  assert.equal(
    await page.getByText(portalCopy.ru.placeholderText).isVisible(),
    true,
  );
  assert.equal(commands.length, 0);
  assert.equal(state, "FREE", "preview cannot grant Premium");
  await page.reload();
  await page.locator("[data-success-preview]").waitFor();
  assert.match(await page.locator("[data-success-preview]").textContent(), /5/);
  await page.screenshot({
    path: `${output}/13-success-preview.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "Назад", exact: true }).click();
  await page.getByLabel("RUB", { exact: true }).check();
  assert.equal(
    await page
      .getByLabel("RUB", { exact: true })
      .evaluate((input) => input === globalThis.document.activeElement),
    true,
  );
  await page.keyboard.press("ArrowDown");
  assert.equal(await page.getByLabel("USD", { exact: true }).isChecked(), true);
  await page.keyboard.press("ArrowUp");
  assert.equal(await page.getByLabel("RUB", { exact: true }).isChecked(), true);
  await page.reload();
  await page.getByRole("button", { name: "Оплатить", exact: true }).waitFor();
  assert.equal(new URL(page.url()).searchParams.get("currency"), "RUB");
  assert.match(await page.locator(".portal-price strong").textContent(), /399/);
  assert.match(await page.locator(".portal-price s").textContent(), /499/);
  await page.screenshot({
    path: `${output}/14-purchase-free-rub.png`,
    fullPage: true,
  });
  await page.goto(origin + "/account/success/");
  await page.getByRole("button", { name: "Оплатить", exact: true }).waitFor();
  assert.equal(
    await page.locator("[data-success-preview]").count(),
    0,
    "the success path alone cannot assert payment or preview",
  );
  state = "PLATINUM";
  for (const language of ["", "en", "de", "fr", "es", "zh"]) {
    for (const width of [320, 390, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(
        origin + (language ? `/${language}` : "") + "/account/?currency=RUB",
      );
      await page.locator("[data-purchase-offer] > .button").waitFor();
      assert.match(
        await page.locator(".portal-price strong").textContent(),
        /399/,
      );
      assert.equal(
        await page.evaluate(
          () =>
            globalThis.document.documentElement.scrollWidth <=
            globalThis.innerWidth,
        ),
        true,
      );
      if (!language && width === 390)
        assert.ok(
          (await page.locator("[data-purchase-offer] > .button").boundingBox())
            .y < 844,
          "payment action should be visible on the initial mobile screen",
        );
      if (!language && width === 390)
        await page.screenshot({
          path: `${output}/15-purchase-platinum-mobile.png`,
          fullPage: true,
        });
      await page.locator("[data-purchase-offer] > .button").click();
      await page.locator("[data-success-preview]").waitFor();
      const prefix = language ? `/${language}` : "";
      const copy = portalCopy[language === "zh" ? "zh-CN" : language || "ru"];
      assert.equal(new URL(page.url()).pathname, prefix + "/account/success/");
      assert.equal(
        await page
          .getByRole("heading", { name: copy.success, exact: true })
          .isVisible(),
        true,
      );
      assert.equal(
        await page.getByText(copy.placeholderText).isVisible(),
        true,
      );
      assert.equal(
        await page.getByRole("link", { name: copy.home }).getAttribute("href"),
        prefix + "/",
      );
      assert.equal(
        await page.evaluate(
          () =>
            globalThis.document.documentElement.scrollWidth <=
            globalThis.innerWidth,
        ),
        true,
      );
      if (!language && width === 390)
        await page.screenshot({
          path: `${output}/16-success-preview-mobile.png`,
          fullPage: true,
        });
    }
  }
  assert.equal(commands.length, 0, "disabled checkout never creates a payment");
  const privatePage = await browser.newPage();
  privatePage.on("pageerror", (error) => errors.push(error.message));
  let privateMutations = 0;
  await privatePage.addInitScript(() => {
    Object.defineProperty(globalThis, "localStorage", {
      get() {
        throw new Error("Storage unavailable");
      },
    });
  });
  await privatePage.route("**/api/web/billing/**", (route) => {
    if (route.request().method() === "POST") privateMutations++;
    return route.fulfill({ json: overview() });
  });
  await privatePage.goto(origin + "/account/");
  await privatePage
    .getByRole("button", { name: "Оплатить", exact: true })
    .click();
  await privatePage.locator("[data-success-preview]").waitFor();
  assert.equal(
    privateMutations,
    0,
    "blocked optional storage must not hide the purchase or create payments",
  );
  await privatePage.close();
  // Sandbox and unsupported USD use the marked success preview without charging.
  offersAvailable = true;
  providerMode = "SANDBOX";
  state = "FREE";
  await page.goto(origin + "/account/");
  await page.getByRole("button", { name: "Оплатить", exact: true }).click();
  await page.locator("[data-success-preview]").waitFor();
  providerMode = "LIVE";
  await page.goto(origin + "/account/?currency=USD");
  await page.getByRole("button", { name: "Оплатить", exact: true }).click();
  await page.locator("[data-success-preview]").waitFor();
  assert.equal(
    commands.length,
    0,
    "unsupported currency cannot silently charge RUB",
  );
  authenticated = false;
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.goto(origin + "/account/success/?preview=1");
  await page.getByLabel("Электронная почта").waitFor();
  assert.equal(await page.locator("[data-success-preview]").count(), 0);
  await page.goto(origin + "/account/");
  await page.getByLabel("Электронная почта").fill("subscriber@example.test");
  await page.getByRole("button", { name: "Получить код" }).click();
  await page.getByLabel("Код из письма").waitFor();
  await page.screenshot({ path: `${output}/01-otp.png`, fullPage: true });
  await page.getByLabel("Код из письма").fill("123456");
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await page.getByRole("button", { name: "Оплатить" }).waitFor();
  await page.screenshot({ path: `${output}/02-free.png`, fullPage: true });
  await page.getByRole("button", { name: "Оплатить" }).click();
  const pay = page.getByRole("button", { name: "Оплатить" });
  assert.equal(await pay.isDisabled(), true);
  await page.getByRole("checkbox").check();
  await page.screenshot({ path: `${output}/03-consent.png`, fullPage: true });
  loseResponse = true;
  await pay.click();
  await page.getByRole("alert").waitFor();
  await page.reload();
  await page.getByRole("heading", { name: "Ждём подтверждения" }).waitFor();
  assert.equal(
    commands.length,
    1,
    "lost response must not create a new charge",
  );
  await page.screenshot({ path: `${output}/04-pending.png`, fullPage: true });
  await page.goto(origin + "/account/success/?preview=1");
  await page.getByRole("heading", { name: "Ждём подтверждения" }).waitFor();
  assert.equal(
    await page.locator("[data-success-preview]").count(),
    0,
    "pending provider operation takes precedence over the preview flag",
  );
  assert.equal(commands.length, 1);
  status = "SUCCEEDED";
  await page.getByRole("button", { name: "Проверить оплату" }).click();
  await page.getByRole("heading", { name: "Всё получилось" }).waitFor();
  await page.screenshot({ path: `${output}/05-success.png`, fullPage: true });
  await page.getByRole("button", { name: "Управлять подпиской" }).click();
  await page
    .getByText("СБП · привязанный банковский счёт", { exact: true })
    .waitFor();
  assert.equal(
    await page.locator("[data-purchase-offer]").count(),
    0,
    "active contract must not adopt new catalog price",
  );
  await page.screenshot({ path: `${output}/06-premium.png`, fullPage: true });
  await page
    .getByRole("button", { name: "Отвязать счёт и отключить продление" })
    .click();
  await page.screenshot({ path: `${output}/07-cancel.png`, fullPage: true });
  await page
    .getByRole("button", {
      name: "Отвязать и отключить продление",
      exact: true,
    })
    .click();
  await page.getByRole("heading", { name: "Всё получилось" }).waitFor();
  await page.getByRole("button", { name: "Управлять подпиской" }).click();
  await page.getByText("Автопродление отключено.", { exact: false }).waitFor();
  assert.match(await page.locator(".portal-price strong").textContent(), /299/);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: `${output}/08-canceled-mobile.png`,
    fullPage: true,
  });
  state = "FREE";
  status = "FAILED";
  operation = null;
  await page.reload();
  await page.getByRole("button", { name: "Оплатить" }).click();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Оплатить" }).click();
  await page.getByRole("heading", { name: "Оплата не завершена" }).waitFor();
  await page.screenshot({
    path: `${output}/09-failure-mobile.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "Попробовать снова" }).click();
  await page.getByRole("button", { name: "Оплатить" }).waitFor();
  const commandCount = commands.length;
  overviewAvailable = false;
  await page.reload();
  await page.locator("[data-reference-prices]").waitFor();
  assert.match(
    await page.locator("[data-reference-prices]").textContent(),
    /399/,
  );
  assert.equal(await page.getByRole("button", { name: "Оплатить" }).count(), 1);
  assert.equal(commands.length, commandCount);
  await page.getByRole("button", { name: "Оплатить", exact: true }).click();
  await page.locator("[data-success-preview]").waitFor();
  assert.equal(
    commands.length,
    commandCount,
    "an outage cannot authorize a payment from stale data",
  );
  await page.screenshot({
    path: `${output}/10-overview-offline.png`,
    fullPage: true,
  });
  overviewAvailable = true;
  await page.getByRole("button", { name: "Назад", exact: true }).click();
  await page.getByRole("button", { name: "Обновить", exact: true }).click();
  await page.getByRole("button", { name: "Оплатить" }).waitFor();
  assert.deepEqual(errors, []);
  console.log(
    "Billing portal: OTP, consent, lost-response recovery, verified success, cancellation, fixed price, failure/retry and mobile layout passed.",
  );
} finally {
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
