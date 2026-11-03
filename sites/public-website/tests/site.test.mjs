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
    assert.ok(locales[code].footer.seller.includes("183475316809"));
    assert.equal(
      (JSON.stringify(locales[code]).match(/prettylisavpn(?!\.com)/g) ?? [])
        .length,
      0,
    );
  }
  assert.throws(() => routeFor("unknown"));
  assert.equal(escape('<script>"&'), "&lt;script&gt;&quot;&amp;");
});
test("home has exactly four sections, one launch notice and seven distinct platform pages", () => {
  const all = pages();
  assert.equal(all.size, 78);
  for (const language of languages) {
    const html = all.get(routeFor(language));
    assert.equal((html.match(/<section /g) ?? []).length, 4);
    assert.equal((html.match(/class="launch"/g) ?? []).length, 1);
    assert.ok(html.includes(locales[language].launch));
    assert.equal((html.match(/class="platform-card /g) ?? []).length, 7);
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
    "/account/",
    "/readiness/",
    "/legal/seller/",
    "/legal/acceptable-use/",
  ])
    assert.ok(!all.has(route));
  assert.equal(legalKeys.length, 4);
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
  for (const file of ["windows-home", "android-services"]) {
    const bytes = await readFile(
      path.join(root, `assets/screenshots/${file}.png`),
    );
    assert.equal(bytes.subarray(1, 4).toString(), "PNG");
    assert.ok(raw.includes(createHash("sha256").update(bytes).digest("hex")));
    assert.ok(raw.includes(file + ".png"));
  }
});
test("commercial launch remains separate from authorized informational publication", () => {
  assert.equal(website.renewal, "MANUAL");
  assert.equal(website.paymentAdapterImplemented, false);
  assert.equal(website.providers.cardlink.approved, false);
  assert.ok(releaseBlockers().length >= 6);
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
  const verification = await fetch(origin + "/shop-verification-xO2ZZeK02A.txt");
  assert.equal(verification.status, 200);
  assert.match(verification.headers.get("content-type"), /^text\/plain/);
  assert.equal((await verification.text()).trim(), "shop-verification-xO2ZZeK02A");
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
    "screenshots/android-services.png",
  ])
    assert.equal((await fetch(origin + "/assets/" + asset)).status, 200);
  for (const route of ["/readiness/", "/plans/", "/account/", "/checkout/"])
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
