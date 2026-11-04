export const website = Object.freeze({
  version: "0.3.0",
  reviewedOn: "2026-11-04",
  mode: "prelaunch",
  seller: Object.freeze({
    name: "Кениг Роман Сергеевич",
    status: "Самозанятый (НПД)",
    country: "Россия",
    inn: "183475316809",
    address: null,
    email: "help@prettylisavpn.com",
    claimsEmail: "feedback@prettylisavpn.com",
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

export function releaseBlockers(config = website) {
  return [
    !config.seller.address && "Не указан адрес для письменных претензий",
    !config.legalApproved && "Документы не утверждены",
    !config.refundPolicyApproved && "Не утверждены правила возврата",
    !config.receiptProcessApproved && "Не определена отправка чеков НПД",
    !config.publicDownloadsReady &&
      "Нет общедоступной доставки клиентских сборок",
    !config.paymentAdapterImplemented &&
      "Нет подключённого и проверенного платёжного адаптера",
    !Object.values(config.providers).some((p) => p.approved && p.configured) &&
      "Нет одобренного и настроенного способа оплаты",
  ].filter(Boolean);
}
