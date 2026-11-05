export const website = Object.freeze({
  version: "0.3.1",
  reviewedOn: "2026-11-05",
  mode: "prelaunch",
  moderationMarker: "platega test",
  seller: Object.freeze({
    email: "help@prettylisavpn.com",
  }),
  prices: Object.freeze({ RUB: 39900, USD: 500 }),
  referencePrices: Object.freeze({ RUB: 49900, USD: 700 }),
  period: "CALENDAR_MONTH",
  renewal: "MANUAL",
  priceConfirmed: true,
  legalApproved: false,
  refundPolicyApproved: false,
  receiptProcessApproved: false,
  publicDownloadsReady: true,
  paymentAdapterImplemented: false,
  providers: Object.freeze({
    platega: Object.freeze({
      approved: false,
      configured: false,
      status: "Сайт подготовлен к модерации. Приём платежей не подключён.",
    }),
    cardlink: Object.freeze({
      approved: false,
      configured: false,
      status: "Аккаунт создан. Заявка не подана.",
    }),
  }),
});

// RUB limit supplied by the provider; all amounts are integer minor units.
export const MAX_TRANSACTION_RUB_MINOR = 1_000_000;
// Only the owner's existing $5 offer / $7 reference price is approved for display.
// This is not an exchange rate or a USD transaction limit from the provider.
const MAX_APPROVED_USD_PRICE_MINOR = 700;
export function assertPricePolicy(config = website) {
  for (const prices of [config.prices, config.referencePrices]) {
    if (Object.keys(prices).sort().join(",") !== "RUB,USD")
      throw new Error("Unapproved price currency");
    for (const [currency, amount] of Object.entries(prices)) {
      const maximum =
        currency === "RUB"
          ? MAX_TRANSACTION_RUB_MINOR
          : MAX_APPROVED_USD_PRICE_MINOR;
      if (!Number.isSafeInteger(amount) || amount <= 0 || amount > maximum)
        throw new Error(`Price exceeds approved policy: ${currency}`);
    }
  }
}

export function releaseBlockers(config = website) {
  return [
    !config.legalApproved && "Документы не утверждены",
    !config.refundPolicyApproved && "Не утверждены правила возврата",
    !config.receiptProcessApproved && "Не определена отправка чеков",
    !config.publicDownloadsReady &&
      "Нет общедоступной доставки клиентских сборок",
    !config.paymentAdapterImplemented &&
      "Нет подключённого и проверенного платёжного адаптера",
    !Object.values(config.providers).some((p) => p.approved && p.configured) &&
      "Нет одобренного и настроенного способа оплаты",
  ].filter(Boolean);
}
