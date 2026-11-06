import test from "node:test";
import assert from "node:assert/strict";
import { acquisitionPrices, formatMonthlyPrice } from "../src/pricing.mjs";

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
