import test from "node:test";
import assert from "node:assert/strict";
import {
  cachedPrices,
  savePublicPrices,
  priceCacheKey,
  referencePrices,
  acquisitionPrices,
  acquisitionReferencePrices,
  formatMonthlyPrice,
} from "../src/pricing.mjs";

const catalog = (rub = 12345) => ({
  offers: [
    {
      plan: "PREMIUM",
      period: "MONTH",
      prices: { RUB: { amount_minor: rub }, USD: { amount_minor: 789 } },
    },
  ],
});
test("prices come from the API in minor units without conversion", () => {
  assert.deepEqual(acquisitionPrices(catalog()), { RUB: 12345, USD: 789 });
  assert.match(formatMonthlyPrice(789, "USD", "en"), /7.89/);
});
test("missing or malformed prices never fall back to a commercial amount", () => {
  for (const value of [
    null,
    {},
    { offers: [] },
    { offers: [...catalog().offers, ...catalog().offers] },
    catalog("19900"),
    catalog(1.5),
    catalog(-1),
    catalog(1e13),
  ])
    assert.equal(acquisitionPrices(value), null);
});

test("a reference price is shown only when the database supplies a valid higher amount", () => {
  const value = catalog();
  assert.deepEqual(acquisitionReferencePrices(value), {});
  value.offers[0].prices.RUB.original_amount_minor = 15000;
  value.offers[0].prices.USD.original_amount_minor = 789;
  assert.deepEqual(acquisitionReferencePrices(value), { RUB: 15000 });
  value.offers[0].prices.RUB.original_amount_minor = "15000";
  assert.deepEqual(acquisitionReferencePrices(value), {});
  assert.deepEqual(acquisitionReferencePrices(null), {});
});

const storage = () => {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
};
test("only validated public amounts survive cache round trips; expiry falls back to approved references", () => {
  const store = storage(),
    now = 1000000000;
  assert.equal(cachedPrices(store, now), null);
  savePublicPrices(
    store,
    { ...catalog(), secret: "never-cache", actions: ["SUBSCRIBE"] },
    now,
  );
  assert.deepEqual(cachedPrices(store, now), {
    prices: { RUB: 12345, USD: 789 },
    original: {},
  });
  assert.equal(store.getItem(priceCacheKey).includes("never-cache"), false);
  assert.equal(store.getItem(priceCacheKey).includes("SUBSCRIBE"), false);
  assert.equal(cachedPrices(store, now - 1), null);
  assert.equal(cachedPrices(store, now + 8 * 86400000), null);
  savePublicPrices(store, catalog(-1), now);
  assert.equal(cachedPrices(store, now).prices.RUB, 12345);
  assert.deepEqual(referencePrices, { RUB: 39900, USD: 500 });
});
test("corrupt or denied optional storage cannot prevent price rendering", () => {
  const store = storage();
  store.setItem(priceCacheKey, "{broken");
  assert.equal(cachedPrices(store), null);
  store.setItem(
    priceCacheKey,
    JSON.stringify({
      at: Date.now(),
      prices: { RUB: { amount_minor: "39900" } },
    }),
  );
  assert.equal(cachedPrices(store), null);
  const denied = {
    getItem() {
      throw new Error("denied");
    },
    setItem() {
      throw new Error("denied");
    },
  };
  assert.equal(cachedPrices(denied), null);
  assert.doesNotThrow(() => savePublicPrices(denied, catalog()));
});
