import { describe, expect, it } from "vitest";
import { parseBilling, portalURL } from "./billing";

it("allows only the fixed billing portal with a one-time fragment", () => {
  const url = "https://prettylisavpn.com/account/#handoff=" + "a".repeat(43);
  expect(portalURL({ url })).toBe(url);
  for (const value of [
    url.replace(".com", ".com.evil.test"),
    url.replace("#", "?"),
    url + "&redirect=evil",
    "javascript:alert(1)",
  ])
    expect(() => portalURL({ url: value })).toThrow("PAYMENT_URL_NOT_ALLOWED");
});

const active = {
  plan: "PREMIUM",
  status: "ACTIVE",
  paid_until: "2027-01-01T00:00:00Z",
  auto_renew: true,
  current_price: { amount_minor: 12345, currency: "RUB" },
  next_charge_at: "2027-01-01T00:00:00Z",
  next_charge_price: { amount_minor: 12345, currency: "RUB" },
  payment_method: {
    label: "Visa •••• 4242",
    kind: "CARD",
    card_brand: "visa",
    card_last4: "4242",
  },
  offers: [],
};
describe("billing presentation", () => {
  it("uses the verified masked summary and authoritative contract price", () => {
    const value = parseBilling(active);
    expect(value.method).toBe("Visa •••• 4242");
    expect(value.next_charge_price).toEqual(value.current_price);
    expect(value).not.toHaveProperty("payment_method.reference");
  });
  it("never displays raw card data or an invented schedule", () => {
    for (const update of [
      {
        payment_method: {
          ...active.payment_method,
          label: "4242 4242 4242 4242",
        },
      },
      {
        payment_method: {
          ...active.payment_method,
          card_last4: "4242424242424242",
        },
      },
      { payment_method: { ...active.payment_method, kind: "SBP" } },
      { auto_renew: false },
      { next_charge_at: null },
      { next_charge_price: { amount_minor: 54321, currency: "RUB" } },
    ])
      expect(() => parseBilling({ ...active, ...update })).toThrow(
        "INVALID_BILLING_RESPONSE",
      );
  });
});
