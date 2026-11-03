export const website = Object.freeze({
  version: "0.1.0",
  reviewedOn: "2026-11-03",
  mode: "draft",
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
  publicDownloadsReady: false,
  paymentAdapterImplemented: false,
  providers: Object.freeze({
    cardlink: Object.freeze({
      approved: false,
      configured: false,
      status: "Аккаунт создан. Заявка не подана.",
    }),
  }),
});

export function currencyFrom(value) {
  return value === "USD" ? "USD" : "RUB";
}
export function money(minor, currency) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency,
    maximumFractionDigits: currency === "RUB" ? 0 : 2,
  }).format(minor / 100);
}
export function nextMonth(instant) {
  const date = new Date(instant);
  if (!Number.isFinite(date.getTime())) throw new Error("Invalid date");
  const day = date.getUTCDate();
  date.setUTCDate(1);
  date.setUTCMonth(date.getUTCMonth() + 1);
  const end = new Date(date);
  end.setUTCMonth(end.getUTCMonth() + 1);
  end.setUTCDate(0);
  date.setUTCDate(Math.min(day, end.getUTCDate()));
  return date;
}
export function checkoutSummary(currency) {
  const selected = currencyFrom(currency);
  return {
    currency: selected,
    baseMinor: website.prices[selected],
    feeMinor: null,
    totalMinor: null,
    available: false,
    redirect: null,
    code: "WEB_CHECKOUT_DISABLED",
  };
}
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
export function supportMail(topic, message) {
  const subjects = {
    question: "Вопрос о PrettyLisaVPN",
    access: "Не получен доступ PrettyLisaVPN",
    refund: "Запрос возврата PrettyLisaVPN",
    privacy: "Запрос о персональных данных PrettyLisaVPN",
  };
  if (!Object.hasOwn(subjects, topic))
    throw new Error("Выберите тему обращения.");
  const body = String(message ?? "").trim();
  if (body.length < 10 || body.length > 1500)
    throw new Error("Напишите от 10 до 1500 символов.");
  return `mailto:${website.seller.email}?subject=${encodeURIComponent(subjects[topic])}&body=${encodeURIComponent(body)}`;
}
