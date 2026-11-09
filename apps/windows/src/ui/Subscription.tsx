import { GuestSubscription } from "./GuestSubscription";
import { PlanComparison, referenceOffer, planLabel } from "./PlanComparison";
import { t, useLanguage, getLanguage } from "../i18n";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import { useApplication } from "../state/application";
import {
  formatPrice,
  remainingPaidDays,
  paymentsEnabled,
  paymentMethodLabel,
  type BillingAction,
  type BillingOperation,
  type BillingOverview,
  type Currency,
  type Offer,
  type PaymentRoute,
} from "../billing/model";
import {
  clearRequestId,
  COUNTRY_EVENT,
  pendingOperation,
  preferredCurrency,
  requestId,
  saveCurrency,
  savePendingOperation,
} from "../billing/preferences";
import { PaymentChoice } from "./PaymentChoice";

type CheckoutSelection = {
  readonly action: "SUBSCRIBE" | "RENEW";
  readonly currency: Currency;
  readonly offer: Offer;
  readonly revision: string;
};

export function Subscription() {
  useLanguage();
  const { session } = useApplication();
  const active = useSyncExternalStore(
    session.subscribe,
    session.current,
    session.current,
  );
  return active ? (
    active.plan === "DEMO" ? (
      <GuestSubscription key={active.sessionId} />
    ) : (
      <SubscriptionContent key={active.sessionId} />
    )
  ) : null;
}

function SubscriptionContent() {
  useLanguage();
  const { billing, paymentBrowser, session } = useApplication();
  const active = useSyncExternalStore(
    session.subscribe,
    session.current,
    session.current,
  );
  const [data, setData] = useState<BillingOverview | null>(null);
  const latestData = useRef(data);
  latestData.current = data;
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [currency, setCurrency] = useState<Currency>(() =>
    preferredCurrency(active?.userId ?? ""),
  );
  const [busy, setBusy] = useState(false);
  const [operation, setOperation] = useState<BillingOperation | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [checkout, setCheckout] = useState<CheckoutSelection | null>(null);
  const inFlight = useRef(false);
  const current = useRef(active);
  current.current = active;
  const requests = useRef(new Set<AbortController>());
  const portalOpened = useRef(false);
  const token = active?.accessToken;
  const user = active?.userId;

  useEffect(() => {
    const refreshOnReturn = () => {
      if (!portalOpened.current || inFlight.current) return;
      setAttempt((value) => value + 1);
    };
    window.addEventListener("focus", refreshOnReturn);
    return () => window.removeEventListener("focus", refreshOnReturn);
  }, []);

  useEffect(() => {
    setCurrency(preferredCurrency(user ?? ""));
    const onCountry = () => setCurrency(preferredCurrency(user ?? ""));
    window.addEventListener(COUNTRY_EVENT, onCountry);
    return () => window.removeEventListener(COUNTRY_EVENT, onCountry);
  }, [user]);

  useEffect(() => {
    const controllers = requests.current;
    inFlight.current = false;
    setBusy(false);
    return () => {
      for (const c of controllers) c.abort();
      controllers.clear();
    };
  }, [token]);

  useEffect(() => {
    if (!token || !user) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setData(null);
    if (!billing) {
      setLoading(false);
      setError("данные подписки пока недоступны");
      return;
    }
    void billing
      .overview(token, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setData(value);
        if (value.payment_operations_available === false) {
          savePendingOperation(user, null);
          setOperation(null);
          setCheckout(null);
          setConfirm(false);
          return;
        }
        const pending = value.pending_operation_id ?? pendingOperation(user);
        if (pending)
          setOperation((old) =>
            old?.id === pending
              ? old
              : { id: pending, status: "PENDING", redirect_url: null },
          );
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setNotice(null);
        if (err instanceof ApiError && err.code === "AUTH_INVALID") {
          void session
            .clear()
            .catch(() => setError("не удалось завершить сессию"));
        } else setError("не удалось загрузить подписку. попробуйте ещё раз");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [attempt, billing, session, token, user]);

  useEffect(() => {
    if (
      !token ||
      !user ||
      !billing ||
      data?.payment_operations_available === false ||
      operation?.status !== "PENDING"
    )
      return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let count = 0;
    let checking = false;
    const refresh = async () => {
      if (checking || controller.signal.aborted) return;
      checking = true;
      clearTimeout(timer);
      try {
        const value = await billing.operation(
          token,
          operation.id,
          controller.signal,
        );
        if (controller.signal.aborted) return;
        if (value.status !== "PENDING") {
          // A return URL is never evidence of a successful charge/cancellation.
          savePendingOperation(user, null);
          clearRequestId(user);
          setOperation(null);
          setNotice(
            value.status === "SUCCEEDED"
              ? "действие подтверждено"
              : "действие не завершено. списание не подтверждено",
          );
          setAttempt((a) => a + 1);
          return;
        }
        setOperation(value);
      } catch (err) {
        if (
          !controller.signal.aborted &&
          err instanceof ApiError &&
          err.code === "AUTH_INVALID"
        ) {
          void session
            .clear()
            .catch(() => setError("не удалось завершить сессию"));
        }
        // Keep pending; do not reissue an operation after a timeout.
      } finally {
        checking = false;
        if (!controller.signal.aborted && ++count < 30)
          timer = setTimeout(() => void refresh(), 3000);
      }
    };
    void refresh();
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    return () => {
      controller.abort();
      clearTimeout(timer);
      window.removeEventListener("focus", onFocus);
    };
  }, [
    billing,
    operation?.id,
    operation?.status,
    token,
    user,
    attempt,
    session,
    data?.payment_operations_available,
  ]);

  if (!active) return null;
  const paid =
    data !== null && (data.status === "ACTIVE" || data.status === "CANCELED");
  const newContract =
    data?.new_contract_required ?? (!paid || data?.plan === "PLATINUM");
  const purchaseAction = newContract ? "SUBSCRIBE" : "RENEW";
  const offers = data?.offers ?? [];
  const offer = offers.find((o) => o.plan === data?.plan) ?? offers[0];
  const pending = operation?.status === "PENDING";
  const disabled = busy || pending || loading;
  const can = (action: BillingAction) =>
    paymentsEnabled(data) &&
    (data?.actions.includes(action) ?? false) &&
    (action !== "CHANGE_METHOD" ||
      (data?.payment_routes.some((cap) =>
        cap.recurring_currencies.includes(
          data?.current_price?.currency ?? currency,
        ),
      ) ??
        false));
  const readOnly = !paymentsEnabled(data);
  const checkoutCurrency =
    purchaseAction === "RENEW" && data?.current_price
      ? data.current_price.currency
      : currency;
  const currencyAvailable =
    data?.payment_routes.some((cap) =>
      cap.currencies.includes(checkoutCurrency),
    ) ?? false;

  async function openProvider(url: string) {
    if (!paymentsEnabled(latestData.current)) return;
    try {
      if (!paymentBrowser) throw new Error("PAYMENT_BROWSER_UNAVAILABLE");
      await paymentBrowser.open(url);
    } catch {
      if (current.current?.accessToken === active?.accessToken)
        setError("не удалось открыть платёжный сервис. попробуйте ещё раз");
    }
  }
  function choosePayment(action: CheckoutSelection["action"]) {
    if (!data || !offer || disabled || !can(action) || !currencyAvailable)
      return;
    const contract = action === "RENEW" ? data.current_price : null;
    if (action === "RENEW" && !contract) return;
    const quotedOffer = contract
      ? {
          ...offer,
          prices: {
            ...offer.prices,
            [contract.currency]: {
              amount_minor: contract.amount_minor,
              original_amount_minor: null,
            },
          },
        }
      : offer;
    setCheckout({
      action,
      offer: quotedOffer,
      currency: contract?.currency ?? currency,
      revision: data.revision,
    });
  }

  async function start(
    action: BillingAction,
    route: PaymentRoute | null = null,
    selection?: CheckoutSelection,
  ) {
    if (
      !active ||
      !billing ||
      !data ||
      inFlight.current ||
      pending ||
      !can(action)
    )
      return;
    const checkoutAction = action === "SUBSCRIBE" || action === "RENEW";
    const selectedOffer = selection?.offer ?? offer;
    if (checkoutAction && (!selectedOffer || route === null)) return;
    const selectedCurrency = selection?.currency ?? currency;
    const revision = selection?.revision ?? data.revision;
    if (
      revision !== data.revision ||
      (checkoutAction &&
        !data.payment_routes.some(
          (cap) =>
            cap.id === route && cap.currencies.includes(selectedCurrency),
        ))
    ) {
      setCheckout(null);
      setError("условия оплаты изменились. выберите способ оплаты заново");
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setError(null);
    setNotice(null);
    setConfirm(false);
    setCheckout(null);
    const controller = new AbortController();
    requests.current.add(controller);
    const offer_id = checkoutAction ? selectedOffer.id : null;
    try {
      const value = await billing.start(
        active.accessToken,
        {
          action,
          request_id: requestId(
            active.userId,
            revision,
            action,
            offer_id,
            selectedCurrency,
            route,
          ),
          expected_revision: revision,
          offer_id,
          currency: selectedCurrency,
          payment_route: route,
        },
        controller.signal,
      );
      if (
        controller.signal.aborted ||
        current.current?.accessToken !== active.accessToken
      )
        return;
      // Persist only the opaque ID; never a provider URL/token or payment details.
      savePendingOperation(active.userId, value.id);
      setOperation({ ...value, status: "PENDING" });
      setNotice("проверяем подтверждение платёжного сервиса…");
      if (value.status === "PENDING" && value.redirect_url)
        await openProvider(value.redirect_url);
    } catch (err) {
      if (
        controller.signal.aborted ||
        current.current?.accessToken !== active.accessToken
      )
        return;
      if (err instanceof ApiError && err.code === "AUTH_INVALID")
        await session
          .clear()
          .catch(() => setError("не удалось завершить сессию"));
      else
        setError(
          "не удалось подтвердить действие. обновите данные и попробуйте снова",
        );
    } finally {
      requests.current.delete(controller);
      if (
        !controller.signal.aborted &&
        current.current?.accessToken === active.accessToken
      ) {
        inFlight.current = false;
        setBusy(false);
      }
    }
  }

  async function openPortal() {
    if (!active || !billing?.portal || !paymentBrowser || busy) return;
    setBusy(true);
    setError(null);
    const controller = new AbortController();
    requests.current.add(controller);
    try {
      const url = await billing.portal(active.accessToken, controller.signal);
      portalOpened.current = true;
      if (
        !controller.signal.aborted &&
        current.current?.sessionId === active.sessionId
      )
        await paymentBrowser.open(url);
    } catch (failure) {
      if (!controller.signal.aborted) {
        if (failure instanceof ApiError && failure.code === "AUTH_INVALID") {
          await session
            .clear()
            .catch(() => setError("не удалось завершить сессию"));
        } else setError("не удалось открыть кабинет оплаты");
      }
    } finally {
      requests.current.delete(controller);
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return (
    <section className="subscription-page" aria-labelledby="subscription-title">
      <Link className="settings-back" to="/settings">
        {t("← настройки")}
      </Link>
      <div className="subscription-heading">
        <h1 id="subscription-title">{t("подписка")}</h1>
        <button
          className="location-refresh"
          aria-label={t("обновить подписку")}
          title={t("обновить подписку")}
          type="button"
          disabled={busy || loading}
          onClick={() => setAttempt((a) => a + 1)}
        >
          <span aria-hidden="true">↻</span>
        </button>
      </div>
      <div className="subscription-scroll">
        {loading ? <p role="status">{t("загружаем подписку…")}</p> : null}
        <div className="current-plan-summary">
          <span>{t("ваш тариф")}</span>
          <strong className="plan-name">
            {planLabel(data?.plan ?? active.plan)}
          </strong>
          {data?.plan === "PLATINUM" && (
            <span>{t("тариф назначен вручную")}</span>
          )}
          {paid && data?.paid_until && (
            <span>
              {t("доступ до")}{" "}
              <time dateTime={data.paid_until}>
                {dateLabel(data.paid_until)}
              </time>{" "}
              · {t(`осталось дней: ${remainingPaidDays(data.paid_until, now)}`)}
            </span>
          )}
        </div>
        <PlanComparison
          plan={data?.plan ?? active.plan}
          offer={offer ?? referenceOffer}
          currency={currency}
          onCurrency={(value) => {
            setCurrency(value);
            saveCurrency(active.userId, value);
          }}
          busy={disabled}
          buyLabel={
            (data?.plan ?? active.plan) !== "PREMIUM" || newContract
              ? "купить"
              : "продлить подписку"
          }
          onBuy={
            (data?.plan ?? active.plan) !== "PREMIUM" ||
            newContract ||
            can("RENEW")
              ? () => {
                  if (
                    !readOnly &&
                    offer &&
                    can(purchaseAction) &&
                    currencyAvailable
                  )
                    choosePayment(purchaseAction);
                  else if (billing?.portal) {
                    void openPortal();
                  } else setNotice("оплата пока недоступна. попробуйте позже");
                }
              : undefined
          }
        >
          {!readOnly && !currencyAvailable && (
            <p>{t("в этой валюте оплата недоступна")}</p>
          )}
          {readOnly && (
            <p className="plan-purchase-note">
              {t(
                "оплата пока недоступна. данные подписки доступны для просмотра.",
              )}
            </p>
          )}
        </PlanComparison>
        {data && paid && (
          <section
            className="billing-card subscription-details"
            aria-label={t("тариф и стоимость")}
          >
            <h2>{t("ваша подписка")}</h2>
            <dl className="subscription-facts">
              {(data.plan !== "PLATINUM" || data.current_price) && (
                <div>
                  <dt>{t("стоимость подписки:")}</dt>
                  <dd>
                    {data.current_price
                      ? formatPrice(
                          data.current_price.amount_minor,
                          data.current_price.currency,
                        ) +
                        " " +
                        t("/ месяц")
                      : t("сведения недоступны")}
                  </dd>
                </div>
              )}
              <div>
                <dt>{t("автопродление")}</dt>
                <dd>
                  {t(
                    data.auto_renew
                      ? "автопродление включено"
                      : "автопродление отключено",
                  )}
                </dd>
              </div>
              <div>
                <dt>{t("способ оплаты")}</dt>
                <dd>
                  {data.payment_method
                    ? data.payment_method.kind === "SBP"
                      ? t("СБП · привязанный банковский счёт")
                      : paymentMethodLabel(data.payment_method)
                    : t(
                        data.status === "ACTIVE" && data.plan !== "PLATINUM"
                          ? "сведения о способе оплаты недоступны"
                          : "не привязан",
                      )}
                </dd>
              </div>
              {data.next_charge_at && data.next_charge_price && (
                <div>
                  <dt>{t("следующее списание")}</dt>
                  <dd>
                    <time dateTime={data.next_charge_at}>
                      {dateLabel(data.next_charge_at)}
                    </time>{" "}
                    ·{" "}
                    {formatPrice(
                      data.next_charge_price.amount_minor,
                      data.next_charge_price.currency,
                    )}
                  </dd>
                </div>
              )}
            </dl>
            {data.current_price && !newContract && (
              <p className="billing-footnote">
                {t("цена закреплена до отмены подписки и нового оформления")}
              </p>
            )}
            {newContract && data.plan !== "PLATINUM" && (
              <p>
                {t(
                  "списаний больше не будет. новую подписку можно оформить по текущей цене",
                )}
              </p>
            )}
          </section>
        )}
        {(can("CHANGE_METHOD") ||
          can("CANCEL") ||
          (paid && billing?.portal)) && (
          <section className="billing-card subscription-management">
            {can("CHANGE_METHOD") && (
              <button
                type="button"
                className="billing-secondary"
                disabled={disabled}
                onClick={() => void start("CHANGE_METHOD")}
              >
                {t("изменить способ оплаты")}
              </button>
            )}
            {paid && billing?.portal && (
              <button
                type="button"
                className="billing-secondary"
                disabled={disabled}
                onClick={() => void openPortal()}
              >
                {t("изменить подписку")}
              </button>
            )}
            {can("CANCEL") && (
              <button
                type="button"
                className="billing-danger"
                disabled={disabled}
                onClick={() => setConfirm(true)}
              >
                {t("отменить подписку")}
              </button>
            )}
          </section>
        )}
        {pending ? (
          <div className="billing-pending" role="status">
            <span>{t("ожидаем подтверждения платёжного сервиса")}</span>
            {operation.redirect_url && !readOnly ? (
              <button
                type="button"
                className="billing-refresh"
                onClick={() => void openProvider(operation.redirect_url!)}
              >
                {t("открыть платёжный сервис")}
              </button>
            ) : null}
          </div>
        ) : notice ? (
          <p className="billing-notice" role="status">
            {t(notice)}
          </p>
        ) : null}
        {error ? (
          <p className="billing-error" role="alert">
            {t(error)}
          </p>
        ) : null}
      </div>
      {checkout && !readOnly && checkout.revision === data?.revision ? (
        <PaymentChoice
          currency={checkout.currency}
          offer={checkout.offer}
          capabilities={data?.payment_routes ?? []}
          onClose={() => setCheckout(null)}
          onConfirm={(route) => void start(checkout.action, route, checkout)}
        />
      ) : null}
      {confirm && !readOnly && data?.paid_until ? (
        <CancelConfirmation
          until={dateLabel(data.paid_until)}
          onClose={() => setConfirm(false)}
          onConfirm={() => void start("CANCEL")}
          onReplace={
            can("CHANGE_METHOD") ? () => void start("CHANGE_METHOD") : undefined
          }
        />
      ) : null}
    </section>
  );
}

function dateLabel(date: string) {
  const formatter = new Intl.DateTimeFormat(getLanguage(), {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  return formatter.format(new Date(date)).replace(/\s?г\.$/, "");
}
function CancelConfirmation({
  until,
  onClose,
  onConfirm,
  onReplace,
}: {
  readonly until: string;
  readonly onClose: () => void;
  readonly onConfirm: () => void;
  readonly onReplace?: () => void;
}) {
  useLanguage();
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    return () => previous?.focus();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="billing-dialog"
      aria-labelledby="cancel-title"
      aria-describedby="cancel-description"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <h2 id="cancel-title">{t("отменить подписку?")}</h2>
      <p id="cancel-description">
        {t("доступ сохранится до ")}
        {t(until)}
        {t(
          ". автопродление отключится, способ оплаты отвяжется. новых списаний не будет.",
        )}
      </p>
      {onReplace ? (
        <p>
          {t(
            "хотите заменить карту? условия подписки и оплаченный срок сохранятся",
          )}
        </p>
      ) : null}
      <div>
        {onReplace ? (
          <button className="billing-primary" type="button" onClick={onReplace}>
            {t("заменить карту")}
          </button>
        ) : null}
        <button
          className="billing-secondary"
          type="button"
          autoFocus
          onClick={onClose}
        >
          {t("оставить подписку")}
        </button>
        <button className="billing-danger" type="button" onClick={onConfirm}>
          {t("да, отменить")}
        </button>
      </div>
    </dialog>
  );
}
