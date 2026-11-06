export const website = Object.freeze({
  version: "0.4.1",
  reviewedOn: "2026-11-06",
  mode: "prelaunch",
  moderationMarker: "platega test",
  seller: Object.freeze({ email: "help@prettylisavpn.com" }),
  period: "CALENDAR_MONTH",
  renewal: "MONTHLY_SUBSCRIPTION",
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
      status: "Проверка СБ. Merchant ID и API-секрет ещё не выданы.",
    }),
  }),
});

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
