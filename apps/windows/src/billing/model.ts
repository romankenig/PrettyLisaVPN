import { getLanguage } from "../i18n/language";
export type Currency = "RUB" | "USD";
export type PaymentRoute = "MIR" | "BANK_CARD" | "ALIPAY_WECHAT" | "CRYPTO";
export type BillingAction = "SUBSCRIBE" | "RENEW" | "CHANGE_METHOD" | "CANCEL";
export const paymentRoutes: readonly PaymentRoute[] = [
  "MIR",
  "BANK_CARD",
  "ALIPAY_WECHAT",
  "CRYPTO",
];
export interface RouteCapability {
  readonly id: PaymentRoute;
  readonly currencies: readonly Currency[];
  readonly recurring_currencies: readonly Currency[];
}
export interface Price {
  readonly amount_minor: number;
  readonly original_amount_minor: number | null;
}
export interface Offer {
  readonly id: string;
  readonly plan: string;
  readonly period: "MONTH";
  readonly prices: Readonly<Record<Currency, Price>>;
}
export interface BillingOverview {
  readonly provider_mode: "DISABLED" | "SANDBOX" | "LIVE";
  readonly payment_routes: readonly RouteCapability[];
  readonly payment_operations_available?: boolean;
  readonly revision: string;
  readonly pending_operation_id: string | null;
  readonly plan: string;
  readonly status: "FREE" | "ACTIVE" | "CANCELED" | "EXPIRED";
  readonly paid_until: string | null;
  readonly auto_renew: boolean;
  readonly current_price: {
    readonly amount_minor: number;
    readonly currency: Currency;
  } | null;
  readonly next_charge_at?: string | null;
  readonly next_charge_price?: {
    readonly amount_minor: number;
    readonly currency: Currency;
  } | null;
  readonly new_contract_required?: boolean;
  readonly payment_method: {
    readonly provider: string;
    readonly label: string;
    readonly kind?: "CARD" | "SBP" | "UNKNOWN";
    readonly card_brand?: "visa" | "mastercard" | "mir" | "unknown" | null;
    readonly card_last4?: string | null;
  } | null;
  readonly offers: readonly Offer[];
  readonly actions: readonly BillingAction[];
}
export interface BillingCommand {
  readonly payment_route: PaymentRoute | null;
  readonly action: BillingAction;
  readonly request_id: string;
  readonly expected_revision: string;
  readonly offer_id: string | null;
  readonly currency: Currency;
}
export interface BillingOperation {
  readonly id: string;
  readonly status: "PENDING" | "SUCCEEDED" | "FAILED" | "CANCELED";
  readonly redirect_url: string | null;
}
export interface BillingClient {
  catalog?(signal: AbortSignal): Promise<readonly Offer[]>;
  portal?(token: string, signal: AbortSignal): Promise<string>;
  overview(token: string, signal: AbortSignal): Promise<BillingOverview>;
  start(
    token: string,
    command: BillingCommand,
    signal: AbortSignal,
  ): Promise<BillingOperation>;
  operation(
    token: string,
    id: string,
    signal: AbortSignal,
  ): Promise<BillingOperation>;
}

export function formatPrice(amount: number, currency: Currency): string {
  return new Intl.NumberFormat(getLanguage(), {
    style: "currency",
    currency,
    minimumFractionDigits: amount % 100 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(amount / 100);
}

export function paymentsEnabled(value: BillingOverview | null): boolean {
  return (
    value?.provider_mode === "LIVE" &&
    value.payment_operations_available === true &&
    value.payment_routes.length === 4
  );
}

function parseRoutes(value: unknown): readonly RouteCapability[] {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.length !== paymentRoutes.length)
    throw new Error("INVALID_BILLING_RESPONSE");
  const routes = value.map((raw) => {
    const cap = record(raw);
    if (
      !paymentRoutes.includes(cap.id as PaymentRoute) ||
      !Array.isArray(cap.currencies) ||
      !cap.currencies.every(currency) ||
      !Array.isArray(cap.recurring_currencies) ||
      !cap.recurring_currencies.every(currency) ||
      new Set(cap.currencies).size !== cap.currencies.length ||
      new Set(cap.recurring_currencies).size !==
        cap.recurring_currencies.length ||
      !cap.recurring_currencies.every(
        (code) =>
          cap.currencies instanceof Array && cap.currencies.includes(code),
      ) ||
      (["CRYPTO", "ALIPAY_WECHAT"].includes(String(cap.id)) &&
        cap.recurring_currencies.length !== 0)
    )
      throw new Error("INVALID_BILLING_RESPONSE");
    return {
      id: cap.id as PaymentRoute,
      currencies: cap.currencies as Currency[],
      recurring_currencies: cap.recurring_currencies as Currency[],
    };
  });
  if (new Set(routes.map((cap) => cap.id)).size !== paymentRoutes.length)
    throw new Error("INVALID_BILLING_RESPONSE");
  return routes;
}

export function parseOverview(value: unknown): BillingOverview {
  const v = record(value);
  const mode = v.provider_mode === undefined ? "DISABLED" : v.provider_mode;
  if (
    typeof mode !== "string" ||
    !["DISABLED", "SANDBOX", "LIVE"].includes(mode)
  )
    throw new Error("INVALID_BILLING_RESPONSE");
  const capabilities = parseRoutes(v.payment_routes);
  const date = (value: unknown) =>
    typeof value === "string" &&
    /T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    Number.isFinite(Date.parse(value));
  if (
    !text(v.revision) ||
    !(v.pending_operation_id === null || text(v.pending_operation_id)) ||
    !plan(v.plan) ||
    !["FREE", "ACTIVE", "CANCELED", "EXPIRED"].includes(String(v.status)) ||
    !(v.paid_until === null || date(v.paid_until)) ||
    typeof v.auto_renew !== "boolean" ||
    !Array.isArray(v.offers) ||
    !Array.isArray(v.actions) ||
    !v.actions.every((a) =>
      ["SUBSCRIBE", "RENEW", "CHANGE_METHOD", "CANCEL"].includes(String(a)),
    )
  ) {
    throw new Error("INVALID_BILLING_RESPONSE");
  }
  if (!(
    v.payment_operations_available === undefined ||
    typeof v.payment_operations_available === "boolean"
  ))
    throw new Error("INVALID_BILLING_RESPONSE");
  if (
    v.payment_operations_available === false &&
    (v.actions.length !== 0 || v.pending_operation_id !== null)
  )
    throw new Error("INVALID_BILLING_RESPONSE");
  if (
    (v.status === "ACTIVE" || v.status === "CANCELED") &&
    v.paid_until === null
  )
    throw new Error("INVALID_BILLING_RESPONSE");
  if (v.auto_renew && (v.status === "FREE" || v.status === "CANCELED"))
    throw new Error("INVALID_BILLING_RESPONSE");
  if (v.status === "CANCELED" && (v.auto_renew || v.payment_method !== null))
    throw new Error("INVALID_BILLING_RESPONSE");
  let current: BillingOverview["current_price"] = null;
  if (v.current_price !== null) {
    const p = record(v.current_price);
    if (!money(p.amount_minor) || !currency(p.currency))
      throw new Error("INVALID_BILLING_RESPONSE");
    current = { amount_minor: p.amount_minor, currency: p.currency };
  }
  let method: BillingOverview["payment_method"] = null;
  if (v.payment_method !== null) {
    const p = record(v.payment_method);
    if (!text(p.provider) || !text(p.label))
      throw new Error("INVALID_BILLING_RESPONSE");
    if ((p.label.match(/\d/g) ?? []).length > 4)
      throw new Error("INVALID_BILLING_RESPONSE");
    const kind = p.kind ?? "UNKNOWN";
    if (!["CARD", "SBP", "UNKNOWN"].includes(String(kind)))
      throw new Error("INVALID_BILLING_RESPONSE");
    if (kind === "CARD") {
      if (
        !/^[0-9]{4}$/.test(String(p.card_last4 ?? "")) ||
        !["visa", "mastercard", "mir", "unknown"].includes(String(p.card_brand))
      )
        throw new Error("INVALID_BILLING_RESPONSE");
    } else if (p.card_last4 != null || p.card_brand != null) {
      throw new Error("INVALID_BILLING_RESPONSE");
    }
    method = {
      provider: p.provider,
      label: p.label,
      kind: kind as NonNullable<BillingOverview["payment_method"]>["kind"],
      card_brand: p.card_brand as NonNullable<
        BillingOverview["payment_method"]
      >["card_brand"],
      card_last4: p.card_last4 as string | null | undefined,
    };
  }
  if (
    !(v.next_charge_at == null || date(v.next_charge_at)) ||
    !(
      v.new_contract_required === undefined ||
      typeof v.new_contract_required === "boolean"
    )
  )
    throw new Error("INVALID_BILLING_RESPONSE");
  let nextPrice: BillingOverview["next_charge_price"] = null;
  if (v.next_charge_price != null) {
    const p = record(v.next_charge_price);
    if (
      !money(p.amount_minor) ||
      !currency(p.currency) ||
      !v.next_charge_at ||
      !v.auto_renew ||
      !method ||
      !current ||
      p.amount_minor !== current.amount_minor ||
      p.currency !== current.currency
    )
      throw new Error("INVALID_BILLING_RESPONSE");
    nextPrice = { amount_minor: p.amount_minor, currency: p.currency };
  }
  if (v.next_charge_at && (!v.auto_renew || !method || !nextPrice))
    throw new Error("INVALID_BILLING_RESPONSE");
  const offers = parseOffers(v.offers);
  if (new Set(offers.map((o) => o.id)).size !== offers.length)
    throw new Error("INVALID_BILLING_RESPONSE");
  return {
    provider_mode: mode as BillingOverview["provider_mode"],
    payment_routes: capabilities,
    payment_operations_available: v.payment_operations_available as
      boolean | undefined,
    revision: v.revision,
    pending_operation_id: v.pending_operation_id as string | null,
    plan: v.plan,
    status: v.status as BillingOverview["status"],
    paid_until: v.paid_until as string | null,
    auto_renew: v.auto_renew,
    current_price: current,
    next_charge_at: v.next_charge_at as string | null | undefined,
    next_charge_price: nextPrice,
    new_contract_required: v.new_contract_required as boolean | undefined,
    payment_method: method,
    offers,
    actions: v.actions as BillingAction[],
  };
}
export function paymentMethodLabel(
  method: NonNullable<BillingOverview["payment_method"]>,
): string {
  if (method.kind !== "CARD" || !method.card_last4) return method.label;
  const brand = {
    visa: "Visa",
    mastercard: "Mastercard",
    mir: "МИР",
    unknown: "карта",
  };
  return `${brand[method.card_brand ?? "unknown"]} •••• ${method.card_last4}`;
}
export function parseOperation(value: unknown): BillingOperation {
  const v = record(value);
  if (
    !text(v.id) ||
    !["PENDING", "SUCCEEDED", "FAILED", "CANCELED"].includes(
      String(v.status),
    ) ||
    !(v.redirect_url === null || text(v.redirect_url))
  )
    throw new Error("INVALID_BILLING_RESPONSE");
  return {
    id: v.id,
    status: v.status as BillingOperation["status"],
    redirect_url: v.redirect_url as string | null,
  };
}
function parsePrice(value: unknown): Price {
  const p = record(value);
  if (
    !money(p.amount_minor) ||
    !(
      p.original_amount_minor === null ||
      (money(p.original_amount_minor) &&
        p.original_amount_minor > p.amount_minor)
    )
  )
    throw new Error("INVALID_BILLING_RESPONSE");
  return {
    amount_minor: p.amount_minor,
    original_amount_minor: p.original_amount_minor as number | null,
  };
}
/** Display only; server remains authoritative for access and renewal. */
export function remainingPaidDays(
  until: string | null,
  now = Date.now(),
): number | null {
  if (!until || !Number.isFinite(Date.parse(until))) return null;
  return Math.max(0, Math.ceil((Date.parse(until) - now) / 86_400_000));
}
function record(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    throw new Error("INVALID_BILLING_RESPONSE");
  return value as Record<string, unknown>;
}
function text(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= 2048;
}
function plan(value: unknown): value is string {
  return typeof value === "string" && /^[A-Z][A-Z0-9_]{0,31}$/.test(value);
}
function money(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}
function currency(value: unknown): value is Currency {
  return value === "RUB" || value === "USD";
}

export function parseOffers(value: unknown): readonly Offer[] {
  if (!Array.isArray(value) || value.length > 100)
    throw new Error("INVALID_BILLING_RESPONSE");
  const offers = value.map((raw) => {
    const p = record(raw),
      prices = record(p.prices);
    if (!text(p.id) || !plan(p.plan) || p.period !== "MONTH")
      throw new Error("INVALID_BILLING_RESPONSE");
    return {
      id: p.id,
      plan: p.plan,
      period: "MONTH" as const,
      prices: { RUB: parsePrice(prices.RUB), USD: parsePrice(prices.USD) },
    };
  });
  if (new Set(offers.map((o) => o.id)).size !== offers.length)
    throw new Error("INVALID_BILLING_RESPONSE");
  return offers;
}
