export type Currency = "RUB" | "USD";
export type BillingAction = "SUBSCRIBE" | "RENEW" | "CHANGE_METHOD" | "CANCEL";
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
  readonly payment_method: {
    readonly provider: string;
    readonly label: string;
  } | null;
  readonly offers: readonly Offer[];
  readonly actions: readonly BillingAction[];
}
export interface BillingCommand {
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
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency,
    minimumFractionDigits: amount % 100 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(amount / 100);
}

export function parseOverview(value: unknown): BillingOverview {
  const v = record(value);
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
  if (
    (v.status === "ACTIVE" || v.status === "CANCELED") &&
    v.paid_until === null
  )
    throw new Error("INVALID_BILLING_RESPONSE");
  if (v.auto_renew && (v.status !== "ACTIVE" || v.payment_method === null))
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
    method = { provider: p.provider, label: p.label };
  }
  const offers = v.offers.map((raw) => {
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
  return {
    revision: v.revision,
    pending_operation_id: v.pending_operation_id as string | null,
    plan: v.plan,
    status: v.status as BillingOverview["status"],
    paid_until: v.paid_until as string | null,
    auto_renew: v.auto_renew,
    current_price: current,
    payment_method: method,
    offers,
    actions: v.actions as BillingAction[],
  };
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
