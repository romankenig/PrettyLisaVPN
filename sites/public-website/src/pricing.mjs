// The public catalog is informational. Checkout must quote the authenticated account again.
export function acquisitionPrices(value) {
  const offer = value?.offers?.length === 1 ? value.offers[0] : null;
  if (!offer || offer.plan !== "PREMIUM" || offer.period !== "MONTH")
    return null;
  const result = {};
  for (const currency of ["RUB", "USD"]) {
    const price = offer.prices?.[currency]?.amount_minor;
    if (!Number.isSafeInteger(price) || price <= 0 || price > 1e12) return null;
    result[currency] = price;
  }
  return result;
}

export function acquisitionReferencePrices(value) {
  const prices = acquisitionPrices(value);
  if (!prices) return {};
  return Object.fromEntries(
    Object.entries(prices).flatMap(([currency, current]) => {
      const original = value.offers[0].prices[currency].original_amount_minor;
      return Number.isSafeInteger(original) &&
        original > current &&
        original <= 1e12
        ? [[currency, original]]
        : [];
    }),
  );
}

export function formatMonthlyPrice(amount, currency, language) {
  return new Intl.NumberFormat(language, {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
    minimumFractionDigits: amount % 100 ? 2 : 0,
  }).format(amount / 100);
}
