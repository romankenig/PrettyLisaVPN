export interface Money {
  amount_minor: number;
  currency: "RUB" | "USD";
}

export function portalURL(value: unknown): string {
  const raw = object(value).url;
  if (
    typeof raw !== "string" ||
    !/^https:\/\/prettylisavpn\.com\/account\/#handoff=[A-Za-z0-9_-]{43}$/.test(
      raw,
    )
  )
    throw new Error("PAYMENT_URL_NOT_ALLOWED");
  return raw;
}
export interface Billing {
  plan: string;
  status: string;
  paid_until: string | null;
  auto_renew: boolean;
  current_price: Money | null;
  next_charge_at: string | null;
  next_charge_price: Money | null;
  new_contract_required: boolean;
  method: string | null;
  methodKind: "CARD" | "SBP" | "UNKNOWN" | null;
  offers: { id: string; prices: { RUB: Money; USD: Money } }[];
}
const object = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("INVALID_BILLING_RESPONSE");
  return value as Record<string, unknown>;
};
const date = (value: unknown): string | null => {
  if (value == null) return null;
  if (
    typeof value !== "string" ||
    !/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) ||
    !Number.isFinite(Date.parse(value))
  )
    throw new Error("INVALID_BILLING_RESPONSE");
  return value;
};
const money = (value: unknown): Money => {
  const v = object(value);
  if (
    !Number.isSafeInteger(v.amount_minor) ||
    Number(v.amount_minor) <= 0 ||
    Number(v.amount_minor) > 1e12 ||
    !["RUB", "USD"].includes(String(v.currency))
  )
    throw new Error("INVALID_BILLING_RESPONSE");
  return {
    amount_minor: Number(v.amount_minor),
    currency: v.currency as Money["currency"],
  };
};
export function parseBilling(value: unknown): Billing {
  const v = object(value);
  if (
    !["FREE", "PREMIUM", "PLATINUM"].includes(String(v.plan)) ||
    !["FREE", "ACTIVE", "CANCELED", "EXPIRED"].includes(String(v.status)) ||
    typeof v.auto_renew !== "boolean" ||
    !Array.isArray(v.offers) ||
    !(
      v.new_contract_required === undefined ||
      typeof v.new_contract_required === "boolean"
    )
  )
    throw new Error("INVALID_BILLING_RESPONSE");
  let method: string | null = null;
  let methodKind: Billing["methodKind"] = null;
  if (v.payment_method != null) {
    const m = object(v.payment_method);
    if (
      typeof m.label !== "string" ||
      m.label.length > 128 ||
      (m.label.match(/\d/g) ?? []).length > 4
    )
      throw new Error("INVALID_BILLING_RESPONSE");
    const kind = m.kind ?? "UNKNOWN";
    if (kind === "CARD") {
      const brands: Record<string, string> = {
        visa: "Visa",
        mastercard: "Mastercard",
        mir: "МИР",
        unknown: "",
      };
      if (
        typeof m.card_brand !== "string" ||
        !Object.hasOwn(brands, m.card_brand) ||
        typeof m.card_last4 !== "string" ||
        !/^[0-9]{4}$/.test(m.card_last4)
      )
        throw new Error("INVALID_BILLING_RESPONSE");
      method = `${brands[m.card_brand]} •••• ${m.card_last4}`.trim();
    } else {
      if (
        !["UNKNOWN", "SBP"].includes(String(kind)) ||
        m.card_brand != null ||
        m.card_last4 != null
      )
        throw new Error("INVALID_BILLING_RESPONSE");
      method = m.label;
    }
    methodKind = kind as Billing["methodKind"];
  }
  const current = v.current_price == null ? null : money(v.current_price);
  const next = v.next_charge_price == null ? null : money(v.next_charge_price);
  const at = date(v.next_charge_at);
  if (
    (at || next) &&
    (!at ||
      !next ||
      !current ||
      !v.auto_renew ||
      !method ||
      next.amount_minor !== current.amount_minor ||
      next.currency !== current.currency)
  )
    throw new Error("INVALID_BILLING_RESPONSE");
  const paid = date(v.paid_until);
  if (
    (["ACTIVE", "CANCELED"].includes(String(v.status)) && !paid) ||
    (v.status === "CANCELED" && (v.auto_renew || method))
  )
    throw new Error("INVALID_BILLING_RESPONSE");
  return {
    plan: String(v.plan),
    status: String(v.status),
    paid_until: paid,
    auto_renew: v.auto_renew,
    current_price: current,
    next_charge_at: at,
    next_charge_price: next,
    method,
    methodKind,
    new_contract_required: v.new_contract_required === true,
    offers: v.offers.map((raw) => {
      const o = object(raw),
        prices = object(o.prices);
      if (
        typeof o.id !== "string" ||
        o.plan !== "PREMIUM" ||
        o.period !== "MONTH"
      )
        throw new Error("INVALID_BILLING_RESPONSE");
      return {
        id: o.id,
        prices: {
          RUB: money({ ...object(prices.RUB), currency: "RUB" }),
          USD: money({ ...object(prices.USD), currency: "USD" }),
        },
      };
    }),
  };
}
