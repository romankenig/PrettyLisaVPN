import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile, writeFile, mkdir, stat } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { pages, locales, escape } from "../src/pages.mjs";
import {
  languages,
  platforms,
  legalKeys,
  routeFor,
} from "../src/structure.mjs";
import { website, releaseBlockers } from "../src/model.mjs";
import { releaseMetadata } from "../src/downloads.mjs";
import { build, dist, root } from "../scripts/build.mjs";
import { createPreviewServer } from "../scripts/preview.mjs";

function shape(value) {
  if (Array.isArray(value)) return value.map(shape);
  if (value && typeof value === "object")
    return Object.fromEntries(
      Object.entries(value).map(([key, child]) => [key, shape(child)]),
    );
  assert.equal(typeof value, "string");
  assert.ok(value.trim());
  return "string";
}

test("billing preserves the published moderation layout and uses API-owned pricing", () => {
  for (const language of languages) {
    const all = pages();
    const html = all.get(routeFor(language));
    assert.match(html, /platega test/);
    assert.equal((html.match(/class="document-button"/g) ?? []).length, 4);
    assert.match(html, /id="documents"/);
    assert.doesNotMatch(html, /183475316809|Кениг Роман|Roman Kenig/);
    assert.match(html, /android-home\.png/);
    assert.match(html, /data-price="RUB"/);
    assert.match(html, /data-price="USD"/);
    assert.match(html, /name="currency" value="RUB" checked/);
    assert.match(html, /data-free-currency="RUB"/);
    assert.match(html, /data-free-currency="USD"/);
    const pricing = html.match(/<section class="pricing[\s\S]*?<\/section>/)[0];
    const purchaseLabel = `>${escape(locales[language].pricing.buy)}</a>`;
    assert.equal(pricing.split(purchaseLabel).length - 1, 2);
    assert.ok(!pricing.includes(`>${escape(locales[language].pricing.manage)}</a>`));
    assert.doesNotMatch(
      html,
      /data-amount-minor=|data-purchase=|id="payment-dialog"/,
    );
    assert.match(html, new RegExp(`href="${routeFor(language, "/account/")}"`));
    assert.match(all.get(routeFor(language, "/account/")), /data-portal/);
  }
});
test("DEMO is below Premium and Free with localized device limits and Android entry", () => {
  const all = pages();
  for (const language of languages) {
    const html = all.get(routeFor(language));
    const premium = html.indexOf('class="plan premium-plan"');
    const free = html.indexOf('class="plan free-plan"');
    const demo = html.indexOf('class="demo-plan"');
    assert.ok(premium >= 0 && free > premium && demo > free);
    const section = html.slice(demo, html.indexOf('</aside>', demo));
    assert.ok(section.includes(escape(locales[language].pricing.demo.description)));
    assert.ok(section.includes(routeFor(language, '/download/android/')));
    assert.ok(!section.includes('class="button"'));
  }
});
test("all six client languages have complete UI, download instructions and four documents", async () => {
  assert.deepEqual(languages, ["ru", "en", "de", "fr", "es", "zh"]);
  const windows = await readFile(
    path.resolve(root, "../../apps/windows/src/i18n/language.ts"),
    "utf8",
  );
  const android = await readFile(
    path.resolve(
      root,
      "../../apps/android/app/src/main/java/com/prettylisavpn/android/ui/AppPresentation.kt",
    ),
    "utf8",
  );
  for (const code of languages) {
    assert.deepEqual(shape(locales[code]), shape(locales.ru), code);
    assert.ok(windows.includes(`"${code}"`), code);
    assert.ok(android.includes(`"${code}"`), code);
    assert.equal(
      (JSON.stringify(locales[code]).match(/prettylisavpn(?!\.com)/g) ?? [])
        .length,
      0,
    );
  }
  assert.throws(() => routeFor("unknown"));
  assert.equal(escape('<script>"&'), "&lt;script&gt;&quot;&amp;");
});
test("home has five sections including database-backed prices, one launch notice and seven distinct platform pages", () => {
  const all = pages();
  assert.equal(all.size, 96);
  for (const language of languages) {
    const html = all.get(routeFor(language));
    assert.equal((html.match(/<section /g) ?? []).length, 5);
    assert.equal((html.match(/class="launch"/g) ?? []).length, 1);
    assert.ok(html.includes(locales[language].launch));
    assert.equal((html.match(/class="platform-card /g) ?? []).length, 7);
    assert.match(html, /<h2 class="faq-title">FAQ<\/h2>/);
    const questions = html
      .split('<div class="questions">')[1]
      .split("<aside")[0];
    assert.equal((questions.match(/<details>/g) ?? []).length, 6);
    assert.doesNotMatch(questions, /\[[^\]]+\]/);
    assert.match(questions, /<p>[^<]*<a href="[^"]*\/download\/android\/">/);
    assert.match(questions, /<a href="mailto:help@prettylisavpn.com">/);
    const protectionAnswer = questions
      .split('<div class="faq-answer">')[3]
      .split("</details>")[0];
    assert.match(protectionAnswer, /https/i);
    assert.doesNotMatch(protectionAnswer, /<a /);
    for (const platform of platforms) {
      const page = all.get(routeFor(language, `/download/${platform.id}/`));
      assert.ok(page);
      assert.equal(
        (page.match(/class="store-option" disabled/g) ?? []).length,
        platform.stores.length,
      );
      if (platform.file) {
        assert.ok(page.includes(`href="/downloads/${platform.file}" download`));
        assert.ok(page.includes(`/downloads/${platform.id}-sources.tar.gz`));
      } else {
        assert.ok(page.includes(escape(locales[language].platforms.soon)));
        assert.doesNotMatch(page, /href="\/downloads\//);
        assert.match(page, /class="button" disabled/);
      }
    }
  }
});
test("all links and anchors resolve; documents and language links preserve context", () => {
  const all = pages();
  const files = new Set([
    "android.apk",
    "windows.exe",
    "android-sources.tar.gz",
    "windows-sources.tar.gz",
    "windows-licenses.txt",
  ]);
  for (const [route, html] of all) {
    assert.equal((html.match(/<h1[ >]/g) ?? []).length, 1, route);
    assert.match(html, /noindex,nofollow/);
    assert.equal((html.match(/hreflang=/g) ?? []).length, 12);
    assert.doesNotMatch(
      html,
      /Stripe|Cryptomus|1Plat|черновик|не утверждён|предпросмотр|<iframe|type="password"|autocomplete="cc-/i,
    );
    for (const [, href] of html.matchAll(/href="([^" ]+)"/g)) {
      if (href.startsWith("mailto:") || href.startsWith("https:")) continue;
      const url = new URL(href, "https://prettylisavpn.com" + route);
      if (url.pathname.startsWith("/assets/")) continue;
      if (url.pathname.startsWith("/downloads/")) {
        assert.ok(files.has(url.pathname.split("/").at(-1)));
        continue;
      }
      assert.ok(all.has(url.pathname), `${route} → ${href}`);
      if (url.hash)
        assert.ok(
          all.get(url.pathname).includes(`id="${url.hash.slice(1)}"`),
          `${route} → ${href}`,
        );
    }
    assert.equal((html.match(/class="legal-links"/g) ?? []).length, 1);
  }
  for (const route of [
    "/plans/",
    "/checkout/",
    "/readiness/",
    "/legal/seller/",
    "/legal/acceptable-use/",
  ])
    assert.ok(!all.has(route));
  assert.equal(legalKeys.length, 4);
});
test("legal templates keep numbered sections, working contents and every localized clause", () => {
  const all = pages();
  for (const language of languages) {
    for (const key of legalKeys) {
      assert.doesNotMatch(
        JSON.stringify(locales[language].legal[key]),
        /PREMIUM|PLATINUM|DEMO|\bSBP\b|СБП|Platega/i,
      );
      assert.doesNotMatch(
        JSON.stringify(locales[language].legal[key]),
        /\bFREE\b/,
      );
    }
    for (const [key, sectionCount] of [
      ["terms", 10],
      ["privacy", 7],
    ]) {
      const document = locales[language].legal[key];
      const html = all.get(routeFor(language, `/legal/${key}/`));
      assert.equal(document.length, sectionCount);
      assert.equal(
        (html.match(/class="document-section"/g) ?? []).length,
        sectionCount,
      );
      assert.match(html, /class="document-contents"/);
      assert.match(html, /class="document-list"/);
      assert.match(html, /href="mailto:help@prettylisavpn.com"/);
      assert.doesNotMatch(
        html,
        /183475316809|Кениг Роман|Roman Kenig|ваш сайт|тг бот|\/start/,
      );
      for (const [index, section] of document.entries()) {
        assert.ok(html.includes(`href="#section-${index + 1}"`));
        assert.ok(html.includes(`id="section-${index + 1}"`));
        for (const [
          paragraphIndex,
          paragraph,
        ] of section.paragraphs.entries()) {
          // The template's final acceptance sentence is intentionally unnumbered.
          if (key === "terms" && index === 9 && paragraphIndex === 1) continue;
          assert.ok(
            paragraph.startsWith(`${index + 1}.${paragraphIndex + 1}. `),
          );
        }
      }
    }
  }
});

test("legal section titles, paragraphs and list items are escaped before rendering", () => {
  const section = locales.ru.legal.terms[0];
  const previous = { title: section.title, paragraphs: section.paragraphs };
  try {
    section.title = '<img src=x onerror="alert(1)">';
    section.paragraphs = [
      '1.1. <script>alert(1)</script>\n<a href="javascript:alert(1)">unsafe</a>\nhelp@prettylisavpn.com',
    ];
    const html = pages().get("/legal/terms/");
    assert.ok(html.includes(escape(section.title)));
    assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
    assert.match(html, /<li>&lt;a href=&quot;javascript:/);
    assert.match(html, /<li><a href="mailto:help@prettylisavpn.com">/);
    assert.doesNotMatch(html, /<img src=x|<script>alert|href="javascript:/);
  } finally {
    Object.assign(section, previous);
  }
});

test("release metadata is optional, validated and cannot change download destinations", () => {
  const data = {
    version: "0.21.0",
    bytes: 28990237,
    sha256: "a".repeat(64),
    url: "https://attacker.invalid/",
  };
  const index = { schema: 1, clients: { android: data } };
  for (const language of languages) {
    const result = releaseMetadata(index, "android", language);
    assert.equal(result.version, "0.21.0");
    assert.equal(result.sha256, data.sha256);
    assert.ok(result.size.length);
    assert.equal(result.url, undefined);
  }
  for (const value of [null, {}, { schema: 2, clients: index.clients }])
    assert.equal(releaseMetadata(value, "android"), null);
  for (const patch of [
    { version: "<img>" },
    { bytes: -1 },
    { bytes: 1.5 },
    { sha256: "<script>" },
  ])
    assert.equal(
      releaseMetadata(
        { schema: 1, clients: { android: { ...data, ...patch } } },
        "android",
      ),
      null,
    );
  assert.equal(releaseMetadata(index, "ios"), null);
});
test("screenshots retain exact native artifact bytes and recorded provenance", async () => {
  const provenance = JSON.parse(
    await readFile(path.join(root, "assets/screenshots/sources.json"), "utf8"),
  );
  const raw = JSON.stringify(provenance);
  for (const file of ["windows-home", "android-home"]) {
    const bytes = await readFile(
      path.join(root, `assets/screenshots/${file}.png`),
    );
    assert.equal(bytes.subarray(1, 4).toString(), "PNG");
    assert.ok(raw.includes(createHash("sha256").update(bytes).digest("hex")));
    assert.ok(raw.includes(file + ".png"));
  }
});
test("commercial launch remains separate from authorized informational publication", () => {
  assert.equal(website.renewal, "MONTHLY_SUBSCRIPTION");
  assert.equal(website.paymentAdapterImplemented, false);
  assert.equal(website.providers.platega.approved, false);
  assert.ok(
    releaseBlockers().includes("Нет одобренного и настроенного способа оплаты"),
  );
  const result = spawnSync(process.execPath, ["scripts/build.mjs"], {
    cwd: root,
    env: { ...process.env, SITE_RELEASE: "1" },
    encoding: "utf8",
  });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Publication blocked/);
});
test("clean build removes stale routes and HTTP serves localized assets without accepting payments", async (t) => {
  await mkdir(path.join(dist, "readiness"), { recursive: true });
  await writeFile(path.join(dist, "readiness/index.html"), "obsolete");
  await build();
  await assert.rejects(stat(path.join(dist, "readiness/index.html")));
  const server = createPreviewServer();
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const verification = await fetch(
    origin + "/shop-verification-xO2ZZeK02A.txt",
  );
  assert.equal(verification.status, 200);
  assert.match(verification.headers.get("content-type"), /^text\/plain/);
  assert.equal(
    (await verification.text()).trim(),
    "shop-verification-xO2ZZeK02A",
  );
  const identity = await (await fetch(origin + "/build-identity.json")).json();
  assert.equal(
    identity.version,
    JSON.parse(await readFile(path.join(root, "package.json"), "utf8")).version,
  );
  assert.equal(identity.source_sha, process.env.WEBSITE_SOURCE_SHA ?? null);
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
    "Rubik.ttf",
    "OFL.txt",
    "app.js",
    "downloads.mjs",
    "style.css",
    "screenshots/windows-home.png",
    "screenshots/android-home.png",
  ])
    assert.equal((await fetch(origin + "/assets/" + asset)).status, 200);
  for (const route of ["/readiness/", "/plans/", "/checkout/"])
    assert.equal((await fetch(origin + route)).status, 404);
  assert.equal((await fetch(origin + "/%5c..%5ckeys")).status, 400);
  assert.equal(
    (await fetch(origin + "/", { method: "POST", body: "private-marker" }))
      .status,
    405,
  );
  const denied = await fetch(origin + "/checkout/?approved=true", {
    method: "POST",
    body: "private-marker",
  });
  assert.equal(denied.status, 503);
  assert.deepEqual(await denied.json(), {
    error: { code: "WEB_CHECKOUT_DISABLED" },
  });
  assert.ok(
    !(await (await fetch(origin + "/?secret=private-marker")).text()).includes(
      "private-marker",
    ),
  );
});
