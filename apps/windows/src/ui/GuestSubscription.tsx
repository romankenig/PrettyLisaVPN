import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useRegistration } from "../auth/useRegistration";
import type { Currency, Offer } from "../billing/model";
import { t, useLanguage } from "../i18n";
import { useApplication } from "../state/application";
import { PlanComparison, referenceOffer } from "./PlanComparison";

export function GuestSubscription() {
  useLanguage();
  const { billing } = useApplication();
  const [offer, setOffer] = useState<Offer>(referenceOffer);
  const [currency, setCurrency] = useState<Currency>("RUB");
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(false);
  const registration = useRegistration();
  useEffect(() => {
    if (!billing?.catalog) return;
    const controller = new AbortController();
    setLoading(true);
    void billing
      .catalog(controller.signal)
      .then((offers) => {
        if (!controller.signal.aborted && offers[0]) setOffer(offers[0]);
      })
      .catch(() => {})
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [billing, attempt]);
  return (
    <section className="subscription-page" aria-labelledby="subscription-title">
      <Link className="settings-back" to="/settings">
        {t("← настройки")}
      </Link>
      <div className="subscription-heading">
        <h1 id="subscription-title">{t("подписка")}</h1>
        <button
          className="location-refresh"
          type="button"
          disabled={loading}
          aria-label={t("обновить подписку")}
          title={t("обновить подписку")}
          onClick={() => setAttempt((value) => value + 1)}
        >
          ↻
        </button>
      </div>
      <div className="subscription-scroll">
        <PlanComparison
          plan="DEMO"
          offer={offer}
          currency={currency}
          onCurrency={setCurrency}
          busy={registration.busy}
          onBuy={() => void registration.register("/settings/subscription")}
          onRegister={() => void registration.register()}
        />
        {registration.error && (
          <p role="alert">
            {t("не удалось завершить гостевую сессию. попробуйте снова")}
          </p>
        )}
      </div>
    </section>
  );
}
