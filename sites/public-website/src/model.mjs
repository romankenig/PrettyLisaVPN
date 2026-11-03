export const website = Object.freeze({
  version: "0.2.1",
  reviewedOn: "2026-11-03",
  mode: "prelaunch",
  seller: Object.freeze({
    name: "Кениг Роман Сергеевич",
    status: "Самозанятый (НПД)",
    country: "Россия",
    inn: "183475316809",
    address: null,
    email: "help@prettylisavpn.com",
  }),
  prices: Object.freeze({ RUB: 19900, USD: 299 }),
  period: "CALENDAR_MONTH",
  renewal: "MANUAL",
  priceConfirmed: true,
  legalApproved: false,
  refundPolicyApproved: false,
  receiptProcessApproved: false,
  publicDownloadsReady: true,
  paymentAdapterImplemented: false,
  providers: Object.freeze({
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
