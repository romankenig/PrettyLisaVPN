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
  purchasePresentation,
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

const liveOverview = () => ({
  revision: "server-revision",
  plan: "FREE",
  new_contract_required: true,
  provider_mode: "LIVE",
  payment_operations_available: true,
  actions: ["SUBSCRIBE"],
  payment_routes: [{ id: "SBP", recurring_currencies: ["RUB"] }],
  offers: [
    {
      id: "server-offer",
      prices: { RUB: { amount_minor: 39900 }, USD: { amount_minor: 500 } },
    },
  ],
});
test("purchase remains visible with reference prices without granting checkout authority", () => {
  for (const plan of ["FREE", "PLATINUM", "DEMO"]) {
    const value = {
      ...liveOverview(),
      plan,
      offers: [],
      actions: [],
      provider_mode: "DISABLED",
    };
    for (const [currency, amount] of [
      ["RUB", 39900],
      ["USD", 500],
    ]) {
      const display = purchasePresentation(value, currency);
      assert.equal(display.amount, amount);
      assert.equal(display.reference, true);
      assert.equal(display.canPay, false);
      assert.equal(display.offer, undefined);
    }
  }
});
test("live checkout requires a fresh supported offer and explicit account capabilities", () => {
  const value = liveOverview();
  assert.equal(purchasePresentation(value, "RUB").canPay, true);
  for (const changed of [
    { provider_mode: "DISABLED" },
    { provider_mode: "SANDBOX" },
    { payment_operations_available: false },
    { actions: [] },
    { payment_routes: [] },
    { revision: null },
    { offers: [{ prices: { RUB: { amount_minor: 39900 } } }] },
  ])
    assert.equal(
      purchasePresentation({ ...value, ...changed }, "RUB").canPay,
      false,
    );
  assert.equal(purchasePresentation(value, "USD").canPay, false);
  assert.equal(purchasePresentation(value, "RUB", null, true).canPay, false);
});
test("renewal keeps the immutable contract price and currency even when the catalog changes", () => {
  const value = {
    ...liveOverview(),
    plan: "PREMIUM",
    new_contract_required: false,
    current_price: { amount_minor: 19900, currency: "RUB" },
    actions: ["RENEW"],
  };
  const display = purchasePresentation(value, "USD");
  assert.equal(display.amount, 19900);
  assert.equal(display.currency, "RUB");
  assert.equal(display.original, null);
  assert.equal(
    display.canPay,
    false,
    "a mismatched new offer cannot charge the existing contract",
  );
  value.offers[0].prices.RUB.amount_minor = 19900;
  assert.equal(purchasePresentation(value, "USD").canPay, true);
  assert.equal(purchasePresentation(value, "USD", null, true).amount, 19900);
});
test("a cached public price affects display only and never supplies an offer or a charge", () => {
  const display = purchasePresentation(null, "USD", {
    prices: { RUB: 45500, USD: 600 },
    original: {},
  });
  assert.equal(display.amount, 600);
  assert.equal(display.canPay, false);
  assert.equal(display.offer, undefined);
  assert.equal(purchasePresentation(null, "invalid").currency, "RUB");
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
