import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { pages } from "../src/pages.mjs";
import {
  website,
  currencyFrom,
  money,
  nextMonth,
  checkoutSummary,
  releaseBlockers,
  supportMail,
} from "../src/model.mjs";
import { build, dist, root } from "../scripts/build.mjs";
import { createPreviewServer } from "../scripts/preview.mjs";

test("approved preview prices retain integer minor units and safe currency selection", () => {
  assert.equal(currencyFrom("USD"), "USD");
  for (const value of [undefined, "EUR", "<script>", "usd"])
    assert.equal(currencyFrom(value), "RUB");
  assert.equal(checkoutSummary("RUB").baseMinor, 19900);
  assert.equal(checkoutSummary("USD").baseMinor, 299);
  assert.match(money(19900, "RUB"), /199/);
});
test("calendar month handles short months, leap years and year boundaries", () => {
  for (const [from, to] of [
    ["2026-01-31T11:13:25Z", "2026-02-28T11:13:25.000Z"],
    ["2028-01-31T11:13:25Z", "2028-02-29T11:13:25.000Z"],
    ["2026-12-30T11:13:25Z", "2027-01-30T11:13:25.000Z"],
  ])
    assert.equal(nextMonth(from).toISOString(), to);
  assert.throws(() => nextMonth("not-a-date"));
});
test("checkout cannot invent a fee, total, approval or redirect", () => {
  for (const value of ["RUB", "USD", "LIVE", "?approved=true"]) {
    const quote = checkoutSummary(value);
    assert.equal(quote.feeMinor, null);
    assert.equal(quote.totalMinor, null);
    assert.equal(quote.available, false);
    assert.equal(quote.redirect, null);
    assert.equal(quote.code, "WEB_CHECKOUT_DISABLED");
  }
  assert.deepEqual(Object.keys(website.providers), ["cardlink"]);
  assert.equal(website.providers.cardlink.approved, false);
  assert.equal(website.renewal, "MANUAL");
  assert.ok(releaseBlockers().length >= 7);
});
test("support validates text and encodes it into a fixed mail recipient without sending", () => {
  assert.throws(() => supportMail("question", "short"));
  assert.throws(() => supportMail("refund", "x".repeat(1501)));
  assert.throws(() => supportMail("bcc=attacker", "Enough text here"));
  const url = new URL(
    supportMail("refund", "Не получен доступ & номер заказа 123\nСпасибо."),
  );
  assert.equal(url.pathname, "help@prettylisavpn.com");
  assert.equal(
    url.searchParams.get("subject"),
    "Запрос возврата PrettyLisaVPN",
  );
  assert.equal(
    url.searchParams.get("body"),
    "Не получен доступ & номер заказа 123\nСпасибо.",
  );
  assert.equal(url.searchParams.get("bcc"), null);
});
test("all internal links resolve and each page has draft status, footer documents and one main heading", () => {
  const all = pages();
  assert.equal(all.size, 16);
  for (const [route, html] of all) {
    assert.equal((html.match(/<h1[ >]/g) ?? []).length, 1, route);
    assert.match(html, /noindex,nofollow/);
    assert.match(html, /Предпросмотр сайта/);
    assert.match(html, /\/legal\/seller\//);
    assert.match(html, /\/legal\/privacy\//);
    assert.match(html, /\/legal\/refunds\//);
    assert.doesNotMatch(
      html,
      /Stripe|Cryptomus|1Plat|<iframe|type="password"|autocomplete="cc-/i,
    );
    for (const [, href] of html.matchAll(/href="(\/[^"#]*)"/g)) {
      const dest = new URL(href, "https://preview.invalid").pathname;
      if (!dest.startsWith("/assets/"))
        assert.ok(all.has(dest), `${route} → ${dest}`);
    }
  }
  for (const [route, html] of all)
    if (route.startsWith("/legal/") && route !== "/legal/")
      assert.match(html, /ЧЕРНОВИК · НЕ УТВЕРЖДЁН/);
  assert.match(all.get("/checkout/"), /button class="button" disabled/);
  assert.doesNotMatch(all.get("/checkout/"), /type="checkbox"[^>]*checked/);
});
test("public release is blocked while mandatory details and provider integration are missing", () => {
  const result = spawnSync(process.execPath, ["scripts/build.mjs"], {
    cwd: root,
    env: { ...process.env, SITE_RELEASE: "1" },
    encoding: "utf8",
  });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Publication blocked/);
});
test("built preview serves routes and assets, rejects payment POST and never reflects submitted secrets", async (t) => {
  await build();
  const server = createPreviewServer();
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const identity = await (await fetch(origin + "/build-identity.json")).json();
  const manifest = JSON.parse(
    await readFile(path.join(root, "package.json"), "utf8"),
  );
  assert.equal(identity.version, manifest.version);
  assert.equal(identity.channel, "preview");
  assert.equal(identity.deployment, "not-published");
  assert.equal(identity.source_sha, process.env.WEBSITE_SOURCE_SHA ?? null);
  assert.equal(identity.run_id, process.env.WEBSITE_BUILD_RUN ?? null);
  assert.equal(identity.run_attempt, process.env.WEBSITE_BUILD_ATTEMPT ?? null);
  for (const route of pages().keys()) {
    const response = await fetch(origin + route);
    assert.equal(response.status, 200, route);
    assert.match(
      response.headers.get("content-security-policy"),
      /form-action 'none'/,
    );
    assert.equal(response.headers.get("cache-control"), "no-store");
  }
  for (const asset of [
    "lock.svg",
    "logo.svg",
    "Rubik.ttf",
    "OFL.txt",
    "app.js",
    "model.mjs",
    "style.css",
  ])
    assert.equal((await fetch(origin + "/assets/" + asset)).status, 200);
  assert.equal((await fetch(origin + "/missing/")).status, 404);
  assert.equal((await fetch(origin + "/%5c..%5ckeys")).status, 400);
  assert.equal(
    (
      await fetch(origin + "/support/", {
        method: "POST",
        body: "private-marker",
      })
    ).status,
    405,
  );
  const denied = await fetch(origin + "/checkout/?approved=true", {
    method: "POST",
    body: JSON.stringify({
      approved: true,
      total: 1,
      secret: "private-marker",
    }),
  });
  assert.equal(denied.status, 503);
  assert.deepEqual(await denied.json(), {
    error: { code: "WEB_CHECKOUT_DISABLED" },
  });
  const page = await (
    await fetch(origin + "/checkout/?status=paid&email=private-marker")
  ).text();
  assert.ok(!page.includes("private-marker"));
  assert.match(
    await readFile(path.join(dist, "robots.txt"), "utf8"),
    /Disallow: \//,
  );
});
