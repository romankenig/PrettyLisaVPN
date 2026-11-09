import type { ReactNode } from "react";
import { formatPrice, type Currency, type Offer } from "../billing/model";
import { t, useLanguage } from "../i18n";

/** Display-only fallback. This ID must never be used to authorize a checkout. */
export const referenceOffer: Offer = {
  id: "display-only",
  plan: "PREMIUM",
  period: "MONTH",
  prices: {
    RUB: { amount_minor: 39900, original_amount_minor: 49900 },
    USD: { amount_minor: 500, original_amount_minor: 700 },
  },
};
export function planLabel(plan: string) {
  return `${plan.toUpperCase()} ${plan === "PREMIUM" ? "⭐" : plan === "PLATINUM" ? "💎" : plan === "DEMO" ? "⏳" : "🕊️"}`;
}
export function PlanComparison({
  plan,
  offer = referenceOffer,
  currency,
  onCurrency,
  onBuy,
  onRegister,
  busy = false,
  buyLabel = "купить",
  children,
}: {
  plan: string;
  offer?: Offer;
  currency: Currency;
  onCurrency: (currency: Currency) => void;
  onBuy?: () => void;
  onRegister?: () => void;
  busy?: boolean;
  buyLabel?: string;
  children?: ReactNode;
}) {
  useLanguage();
  const price = offer.prices[currency];
  return (
    <div className="plan-comparison">
      <section className="plan-card plan-premium" aria-label="PREMIUM">
        <div className="plan-card-heading">
          <h2 className="plan-name">{planLabel("PREMIUM")}</h2>
          {plan === "PREMIUM" ? (
            <span className="plan-current">{t("ваш тариф")}</span>
          ) : (
            <span className="plan-tagline">{t("больше свободы")}</span>
          )}
        </div>
        <ul className="plan-benefits">
          <li>
            <strong>{t("без ограничений времени и трафика")}</strong>
          </li>
          <li>{t("премиум-серверы и все доступные страны")}</li>
          <li>{t("до 5 устройств · без рекламы")}</li>
        </ul>
        <div className="plan-price-row">
          <div
            className="plan-price"
            aria-label={t(
              currency === "RUB" ? "цена в рублях" : "цена в долларах",
            )}
          >
            {price.original_amount_minor !== null && (
              <del>{formatPrice(price.original_amount_minor, currency)}</del>
            )}
            <strong>{formatPrice(price.amount_minor, currency)}</strong>
            <span>{t("за календарный месяц")}</span>
          </div>
          <div
            className="plan-currencies"
            role="group"
            aria-label={t("основная валюта")}
          >
            {(["RUB", "USD"] as const).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={currency === value}
                disabled={busy}
                onClick={() => onCurrency(value)}
              >
                {value}
              </button>
            ))}
          </div>
        </div>
        {onBuy && (
          <button
            className="plan-buy"
            type="button"
            disabled={busy}
            onClick={onBuy}
          >
            {t(buyLabel)}
          </button>
        )}
        {children}
      </section>
      <div className="plan-secondary-grid">
        <section className="plan-card plan-free" aria-label="FREE">
          <div className="plan-card-heading">
            <h2 className="plan-name">{planLabel("FREE")}</h2>
            {plan === "FREE" && (
              <span className="plan-current">{t("ваш тариф")}</span>
            )}
          </div>
          <ul className="plan-benefits">
            <li>
              <strong>{t("1 час в день")}</strong>
            </li>
            <li>{t("бесплатные серверы · без рекламы")}</li>
          </ul>
          {onRegister && (
            <button
              className="plan-register"
              type="button"
              disabled={busy}
              onClick={onRegister}
            >
              {t("зарегистрироваться")}
            </button>
          )}
        </section>
        <section className="plan-card plan-demo" aria-label="DEMO">
          <div className="plan-card-heading">
            <h2 className="plan-name">{planLabel("DEMO")}</h2>
            {plan === "DEMO" && (
              <span className="plan-current">{t("ваш тариф")}</span>
            )}
          </div>
          <ul className="plan-benefits">
            <li>
              <strong>{t("15 минут в день на этом устройстве")}</strong>
            </li>
            <li>{t("только автопилот и весь трафик")}</li>
            <li>{t("без регистрации")}</li>
          </ul>
        </section>
      </div>
    </div>
  );
}
