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

// Display only: no offer IDs, revisions, actions, entitlements or payment authority.
export const referencePrices = Object.freeze({ RUB: 39900, USD: 500 });
export const referenceOriginalPrices = Object.freeze({ RUB: 49900, USD: 700 });
export const priceCacheKey = "prettylisa.public-prices.v1";
const maxAge = 7 * 24 * 60 * 60 * 1000;
export const referencePriceCopy = {
  ru: "Справочные цены для новой подписки. Перед оплатой подтвердим актуальные условия. Цена действующей подписки не меняется.",
  en: "Reference prices for a new subscription. We will confirm current terms before payment. Your existing contract price stays unchanged.",
  de: "Richtpreise für ein neues Abonnement. Die aktuellen Konditionen werden vor der Zahlung bestätigt. Ihr bestehender Vertragspreis bleibt unverändert.",
  es: "Precios orientativos para una nueva suscripción. Confirmaremos las condiciones antes del pago. El precio de tu contrato actual no cambia.",
  fr: "Prix indicatifs pour un nouvel abonnement. Les conditions seront confirmées avant le paiement. Le prix de votre contrat actuel reste inchangé.",
  zh: "新订阅的参考价格。付款前将确认最新条款。现有订阅的合同价格保持不变。",
};

export function cachedPrices(storage, now = Date.now()) {
  try {
    const saved = JSON.parse(storage.getItem(priceCacheKey));
    if (
      !Number.isSafeInteger(saved?.at) ||
      saved.at > now ||
      now - saved.at > maxAge
    )
      return null;
    const catalog = {
      offers: [{ plan: "PREMIUM", period: "MONTH", prices: saved.prices }],
    };
    const prices = acquisitionPrices(catalog);
    return prices
      ? { prices, original: acquisitionReferencePrices(catalog) }
      : null;
  } catch {
    return null;
  }
}

export function savePublicPrices(storage, catalog, now = Date.now()) {
  const prices = acquisitionPrices(catalog);
  if (!prices) return;
  const original = acquisitionReferencePrices(catalog);
  try {
    storage.setItem(
      priceCacheKey,
      JSON.stringify({
        at: now,
        prices: Object.fromEntries(
          Object.entries(prices).map(([currency, amount_minor]) => [
            currency,
            {
              amount_minor,
              original_amount_minor: original[currency] ?? null,
            },
          ]),
        ),
      }),
    );
  } catch {
    /* Storage is optional; display and checkout do not depend on it. */
  }
}
