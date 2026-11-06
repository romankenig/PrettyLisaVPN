import test from "node:test";
import assert from "node:assert/strict";
import { providerURL } from "../src/portal.mjs";
import { pages } from "../src/pages.mjs";
import { portalCopy } from "../src/portal-copy.mjs";

test("all six portal languages include recurring consent, cancellation and recovery", () => {
  const keys = Object.keys(portalCopy.en).sort();
  for (const lang of ["ru", "en", "de", "fr", "es", "zh-CN"]) {
    assert.deepEqual(Object.keys(portalCopy[lang]).sort(), keys);
    assert.ok(
      Object.values(portalCopy[lang]).every(
        (value) => typeof value === "string" && value.length > 0,
      ),
    );
  }
});

test("checkout links require the exact provider origin without credentials", () => {
  assert.equal(
    providerURL("https://pay.platega.io/subscription/abc"),
    "https://pay.platega.io/subscription/abc",
  );
  for (const value of [
    "http://pay.platega.io/pay",
    "https://pay.platega.io.evil.test/pay",
    "https://secret@pay.platega.io/pay",
    "javascript:alert(1)",
    "https://pay.platega.io/pay#token",
  ])
    assert.throws(() => providerURL(value));
});

test("return pages load the authenticated portal rather than assert payment success", () => {
  for (const path of ["/account/", "/account/success/", "/account/failure/"]) {
    const html = pages().get(path);
    assert.ok(html.includes("data-portal"));
    assert.ok(!html.includes("status=CONFIRMED"));
    assert.ok(!html.includes("card_number"));
  }
});
