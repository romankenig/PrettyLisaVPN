import { t, useLanguage, getLanguage } from "../i18n";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import { useApplication } from "../state/application";
import {
  formatPrice,
  paymentsEnabled,
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
import { NavigationIcon } from "./NavigationIcon";
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
  return active ? <SubscriptionContent key={active.sessionId} /> : null;
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
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [currency, setCurrency] = useState<Currency>(() =>
    preferredCurrency(active?.userId ?? ""),
  );
  const [offerId, setOfferId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [operation, setOperation] = useState<BillingOperation | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [checkout, setCheckout] = useState<CheckoutSelection | null>(null);
  const inFlight = useRef(false);
  const current = useRef(active);
  current.current = active;
  const requests = useRef(new Set<AbortController>());
  const token = active?.accessToken;
  const user = active?.userId;

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
  const offers = (data?.offers ?? []).filter(
    (o) => !paid || o.plan === data?.plan,
  );
  const offer =
    offers.find((o) => o.id === offerId) ??
    offers.find((o) => o.plan === data?.plan) ??
    offers[0];
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
  const currencyAvailable =
    data?.payment_routes.some((cap) => cap.currencies.includes(currency)) ??
    false;
  const manualPlan = data?.plan === "PLATINUM" && offers.length === 0;

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
    setCheckout({ action, offer, currency, revision: data.revision });
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

  return (
    <section className="subscription-page" aria-labelledby="subscription-title">
      <Link className="settings-back" to="/settings">
        {t("← настройки")}
      </Link>
      <div className="subscription-heading">
        <h1 id="subscription-title">{t("подписка")}</h1>
        <button
          className="billing-refresh"
          type="button"
          disabled={busy || loading}
          onClick={() => setAttempt((a) => a + 1)}
        >
          {t("обновить")}
        </button>
      </div>
      <div className="subscription-scroll">
        {loading ? <p role="status">{t("загружаем подписку…")}</p> : null}
        {!loading && !data ? (
          <div className="billing-card">
            <h2>{t(planName(active.plan))}</h2>
            <p>{t("данные подписки пока недоступны")}</p>
            <p>{t("цены и способы оплаты появятся после загрузки")}</p>
          </div>
        ) : null}
        {data ? (
          <div className="billing-grid">
            <section
              className="billing-card billing-plan"
              aria-label={t("тариф и стоимость")}
            >
              <span className="billing-eyebrow">{t("ваш тариф")}</span>
              <h2>{t(planName(data.plan))}</h2>
              <p className="billing-term">
                {paid ? (
                  <>
                    {t("доступ до")}
                    {t(" ")}
                    <time dateTime={data.paid_until!}>
                      {t(dateLabel(data.paid_until!))}
                    </time>
                  </>
                ) : data.status === "EXPIRED" ? (
                  "платный доступ не активен"
                ) : (
                  "бесплатный доступ"
                )}
              </p>
              {paid && data.current_price ? (
                <p className="billing-current">
                  {t("стоимость подписки:")}
                  {t(" ")}
                  {t(
                    formatPrice(
                      data.current_price.amount_minor,
                      data.current_price.currency,
                    ),
                  )}
                  {t(" ")}
                  {t("/ месяц")}
                </p>
              ) : null}
              {paid && !data.current_price ? (
                <p className="billing-current">
                  {t("стоимость подписки: сведения недоступны")}
                </p>
              ) : null}
              {paid ? (
                <p
                  className={`billing-renewal ${data.auto_renew ? "" : "billing-renewal--off"}`}
                >
                  {t(
                    data.auto_renew
                      ? "автопродление включено"
                      : "автопродление отключено",
                  )}
                </p>
              ) : null}
              {readOnly ? (
                <p className="billing-footnote" role="status">
                  {t(
                    "оплата пока недоступна. данные подписки доступны для просмотра.",
                  )}
                </p>
              ) : null}
              {manualPlan ? (
                <p>
                  {t(
                    "тариф назначен вручную. продление через оплату недоступно.",
                  )}
                </p>
              ) : (
                <>
                  {offers.length > 1 ? (
                    <label className="billing-offer-select">
                      {t("тариф на месяц")}
                      <select
                        aria-label={t("тариф на месяц")}
                        value={offer.id}
                        disabled={disabled}
                        onChange={(e) => setOfferId(e.target.value)}
                      >
                        {offers.map((o) => (
                          <option key={o.id} value={o.id}>
                            {t(planName(o.plan))}
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : null}
                  <div className="billing-price-heading">
                    <span>
                      {t(
                        readOnly && paid
                          ? "предложение на месяц"
                          : paid
                            ? "продлить на месяц"
                            : `${offer ? planName(offer.plan) : "подписка"} на месяц`,
                      )}
                    </span>
                    <div
                      className="billing-currencies"
                      role="group"
                      aria-label={t("основная валюта")}
                    >
                      {(["RUB", "USD"] as const).map((value) => (
                        <button
                          key={value}
                          type="button"
                          aria-pressed={currency === value}
                          disabled={disabled}
                          onClick={() => {
                            setCurrency(value);
                            saveCurrency(active.userId, value);
                          }}
                        >
                          {t(value === "RUB" ? "₽" : "$")}
                        </button>
                      ))}
                    </div>
                  </div>
                  {offer ? (
                    <OfferPrices offer={offer} currency={currency} />
                  ) : (
                    <p>{t("цены пока недоступны")}</p>
                  )}
                  <button
                    className="billing-primary"
                    type="button"
                    disabled={
                      disabled ||
                      !offer ||
                      !currencyAvailable ||
                      !can(paid ? "RENEW" : "SUBSCRIBE")
                    }
                    onClick={() => choosePayment(paid ? "RENEW" : "SUBSCRIBE")}
                  >
                    {t(
                      busy
                        ? "подождите…"
                        : paid
                          ? "продлить подписку"
                          : "оформить подписку",
                    )}
                  </button>
                  {!readOnly && !currencyAvailable ? (
                    <p className="billing-footnote">
                      {t(
                        "в этой валюте оплата недоступна. выберите другую валюту",
                      )}
                    </p>
                  ) : null}
                  <p className="billing-footnote">
                    {t(
                      readOnly
                        ? paid && data.current_price
                          ? "условия действующей подписки. списание не выполняется."
                          : "цены предложения на месяц. списание не выполняется."
                        : paid
                          ? "оплата и новый способ оплаты — на стороне платёжного сервиса"
                          : "способ оплаты и автопродление подтверждаются при оформлении",
                    )}
                  </p>
                </>
              )}
            </section>
            <section
              className="billing-card billing-method"
              aria-labelledby="payment-method-title"
            >
              <div className="billing-method-heading">
                <NavigationIcon name="subscription" />
                <h2 id="payment-method-title">{t("способ оплаты")}</h2>
              </div>
              {data.payment_method ? (
                <div className="billing-method-value">
                  <strong>{t(data.payment_method.provider)}</strong>
                  <span>{t(data.payment_method.label)}</span>
                </div>
              ) : (
                <p className="billing-method-value">
                  {t(
                    data.auto_renew
                      ? "сведения о способе оплаты недоступны"
                      : "не привязан",
                  )}
                </p>
              )}
              {can("CHANGE_METHOD") ? (
                <button
                  className="billing-secondary"
                  type="button"
                  disabled={disabled}
                  onClick={() => void start("CHANGE_METHOD")}
                >
                  {t(
                    data.payment_method
                      ? "изменить способ оплаты"
                      : "привязать способ оплаты",
                  )}
                </button>
              ) : null}
              <p className="billing-footnote">
                {t(
                  readOnly
                    ? "управление оплатой пока недоступно"
                    : "реквизиты хранятся у платёжного сервиса. подтверждение откроется в браузере",
                )}
              </p>
              {paid && !data.auto_renew && !readOnly ? (
                <p className="billing-no-renew">
                  {t("автоматических списаний нет")}
                </p>
              ) : null}
              {can("CANCEL") ? (
                <div className="billing-cancel-area">
                  <p>{t("доступ сохранится до оплаченной даты")}</p>
                  <button
                    className="billing-danger"
                    type="button"
                    disabled={disabled}
                    onClick={() => setConfirm(true)}
                  >
                    {t("отменить подписку")}
                  </button>
                </div>
              ) : null}
            </section>
          </div>
        ) : null}
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
        />
      ) : null}
    </section>
  );
}

function OfferPrices({
  offer,
  currency,
}: {
  readonly offer: Offer;
  readonly currency: Currency;
}) {
  useLanguage();
  const secondary: Currency = currency === "RUB" ? "USD" : "RUB";
  return (
    <div className="billing-prices">
      {([currency, secondary] as const).map((code, i) => (
        <div
          key={code}
          className={
            i === 0 ? "billing-price-primary" : "billing-price-secondary"
          }
          aria-label={t(code === "RUB" ? "цена в рублях" : "цена в долларах")}
        >
          {offer.prices[code].original_amount_minor !== null ? (
            <del>
              {t(formatPrice(offer.prices[code].original_amount_minor!, code))}
            </del>
          ) : null}
          <strong>
            {t(formatPrice(offer.prices[code].amount_minor, code))}
          </strong>
          <span>{t("/ месяц")}</span>
        </div>
      ))}
    </div>
  );
}
function planName(plan: string) {
  return plan === "PREMIUM"
    ? "premium ⭐"
    : plan === "PLATINUM"
      ? "platinum 💎"
      : plan.toLowerCase();
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
}: {
  readonly until: string;
  readonly onClose: () => void;
  readonly onConfirm: () => void;
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
      <div>
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
