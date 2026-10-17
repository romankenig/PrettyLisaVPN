import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import { useApplication } from "../state/application";
import { formatPrice, type BillingAction, type BillingOperation, type BillingOverview, type Currency, type Offer } from "../billing/model";
import { clearRequestId, COUNTRY_EVENT, pendingOperation, preferredCurrency, requestId, saveCurrency, savePendingOperation } from "../billing/preferences";
import { NavigationIcon } from "./NavigationIcon";

export function Subscription() {
  const { session } = useApplication();
  const active = useSyncExternalStore(session.subscribe, session.current, session.current);
  return active ? <SubscriptionContent key={active.sessionId} /> : null;
}

function SubscriptionContent() {
  const { billing, paymentBrowser, session } = useApplication();
  const active = useSyncExternalStore(session.subscribe, session.current, session.current);
  const [data, setData] = useState<BillingOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [currency, setCurrency] = useState<Currency>(() => preferredCurrency(active?.userId ?? ""));
  const [offerId, setOfferId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [operation, setOperation] = useState<BillingOperation | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
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
    return () => { for (const c of controllers) c.abort(); controllers.clear(); };
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
    void billing.overview(token, controller.signal).then(value => {
      if (controller.signal.aborted) return;
      setData(value);
      const pending = value.pending_operation_id ?? pendingOperation(user);
      if (pending) setOperation(old => old?.id === pending ? old : { id: pending, status: "PENDING", redirect_url: null });
    }).catch((err: unknown) => {
      if (controller.signal.aborted) return;
      if (err instanceof ApiError && err.code === "AUTH_INVALID") {
        void session.clear().catch(() => setError("не удалось завершить сессию"));
      } else setError("не удалось загрузить подписку. попробуйте ещё раз");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [attempt, billing, session, token, user]);

  useEffect(() => {
    if (!token || !user || !billing || operation?.status !== "PENDING") return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let count = 0;
    let checking = false;
    const refresh = async () => {
      if (checking || controller.signal.aborted) return;
      checking = true;
      clearTimeout(timer);
      try {
        const value = await billing.operation(token, operation.id, controller.signal);
        if (controller.signal.aborted) return;
        if (value.status !== "PENDING") {
          // A return URL is never evidence of a successful charge/cancellation.
          savePendingOperation(user, null);
          clearRequestId(user);
          setOperation(null);
          setNotice(value.status === "SUCCEEDED" ? "действие подтверждено" : "действие не завершено. списание не подтверждено");
          setAttempt(a => a + 1);
          return;
        }
        setOperation(value);
      } catch (err) {
        if (!controller.signal.aborted && err instanceof ApiError && err.code === "AUTH_INVALID") {
          void session.clear().catch(() => setError("не удалось завершить сессию"));
        }
        // Keep pending; do not reissue an operation after a timeout.
      }
      finally {
        checking = false;
        if (!controller.signal.aborted && ++count < 30) timer = setTimeout(() => void refresh(), 3000);
      }
    };
    void refresh();
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    return () => { controller.abort(); clearTimeout(timer); window.removeEventListener("focus", onFocus); };
  }, [billing, operation?.id, operation?.status, token, user, attempt, session]);

  if (!active) return null;
  const paid = data !== null && (data.status === "ACTIVE" || data.status === "CANCELED");
  const offers = (data?.offers ?? []).filter(o => !paid || o.plan === data?.plan);
  const offer = offers.find(o => o.id === offerId) ?? offers.find(o => o.plan === data?.plan) ?? offers[0];
  const pending = operation?.status === "PENDING";
  const disabled = busy || pending || loading;
  const can = (action: BillingAction) => data?.actions.includes(action) ?? false;

  async function openProvider(url: string) {
    try {
      if (!paymentBrowser) throw new Error("PAYMENT_BROWSER_UNAVAILABLE");
      await paymentBrowser.open(url);
    } catch {
      if (current.current?.accessToken === active?.accessToken) setError("не удалось открыть платёжный сервис. попробуйте ещё раз");
    }
  }
  async function start(action: BillingAction) {
    if (!active || !billing || !data || inFlight.current || pending || !can(action)) return;
    if ((action === "SUBSCRIBE" || action === "RENEW") && !offer) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    setNotice(null);
    setConfirm(false);
    const controller = new AbortController();
    requests.current.add(controller);
    const offer_id = action === "SUBSCRIBE" || action === "RENEW" ? offer.id : null;
    try {
      const value = await billing.start(active.accessToken, {
        action,
        request_id: requestId(active.userId, data.revision, action, offer_id, currency),
        expected_revision: data.revision,
        offer_id,
        currency,
      }, controller.signal);
      if (controller.signal.aborted || current.current?.accessToken !== active.accessToken) return;
      // Persist only the opaque ID; never a provider URL/token or payment details.
      savePendingOperation(active.userId, value.id);
      setOperation({ ...value, status: "PENDING" });
      setNotice("проверяем подтверждение платёжного сервиса…");
      if (value.status === "PENDING" && value.redirect_url) await openProvider(value.redirect_url);
    } catch (err) {
      if (controller.signal.aborted || current.current?.accessToken !== active.accessToken) return;
      if (err instanceof ApiError && err.code === "AUTH_INVALID") await session.clear().catch(() => setError("не удалось завершить сессию"));
      else setError("не удалось подтвердить действие. повторная попытка не создаст новый платёж");
    } finally {
      requests.current.delete(controller);
      if (!controller.signal.aborted && current.current?.accessToken === active.accessToken) {
        inFlight.current = false;
        setBusy(false);
      }
    }
  }

  return (
    <section className="subscription-page" aria-labelledby="subscription-title">
      <Link className="settings-back" to="/settings">← настройки</Link>
      <div className="subscription-heading">
        <h1 id="subscription-title">подписка</h1>
        <button className="billing-refresh" type="button" disabled={busy || loading} onClick={() => setAttempt(a => a + 1)}>обновить</button>
      </div>
      <div className="subscription-scroll">
        {loading ? <p role="status">загружаем подписку…</p> : null}
        {!loading && !data ? <div className="billing-card"><h2>{planName(active.plan)}</h2><p>данные подписки пока недоступны</p><p>цены и способы оплаты появятся после загрузки</p></div> : null}
        {data ? <div className="billing-grid">
          <section className="billing-card billing-plan" aria-label="тариф и стоимость">
            <span className="billing-eyebrow">ваш тариф</span>
            <h2>{planName(data.plan)}</h2>
            <p className="billing-term">{paid ? <>доступ до <time dateTime={data.paid_until!}>{dateLabel(data.paid_until!)}</time></> : data.status === "EXPIRED" ? "подписка закончилась" : "бесплатный доступ"}</p>
            {paid && data.current_price ? <p className="billing-current">стоимость подписки: {formatPrice(data.current_price.amount_minor, data.current_price.currency)} / месяц</p> : null}
            {paid ? <p className={`billing-renewal ${data.auto_renew ? "" : "billing-renewal--off"}`}>{data.auto_renew ? "автопродление включено" : "автопродление отключено"}</p> : <p className="billing-intro">без рекламы и ограничений по времени</p>}
            {offers.length > 1 ? <label className="billing-offer-select">тариф на месяц<select aria-label="тариф на месяц" value={offer.id} disabled={disabled} onChange={e => setOfferId(e.target.value)}>{offers.map(o => <option key={o.id} value={o.id}>{planName(o.plan)}</option>)}</select></label> : null}
            <div className="billing-price-heading"><span>{paid ? "продлить на месяц" : `${offer ? planName(offer.plan) : "подписка"} на месяц`}</span><div className="billing-currencies" role="group" aria-label="основная валюта">{(["RUB", "USD"] as const).map(value => <button key={value} type="button" aria-pressed={currency === value} disabled={disabled} onClick={() => { setCurrency(value); saveCurrency(active.userId, value); }}>{value === "RUB" ? "₽" : "$"}</button>)}</div></div>
            {offer ? <OfferPrices offer={offer} currency={currency} /> : <p>цены пока недоступны</p>}
            <button className="billing-primary" type="button" disabled={disabled || !offer || !can(paid ? "RENEW" : "SUBSCRIBE")} onClick={() => void start(paid ? "RENEW" : "SUBSCRIBE")}>{busy ? "подождите…" : paid ? "продлить подписку" : "оформить подписку"}</button>
            <p className="billing-footnote">{paid ? "оплата и новый способ оплаты — на стороне платёжного сервиса" : "способ оплаты и автопродление подтверждаются при оформлении"}</p>
          </section>
          <section className="billing-card billing-method" aria-labelledby="payment-method-title">
            <div className="billing-method-heading"><NavigationIcon name="subscription" /><h2 id="payment-method-title">способ оплаты</h2></div>
            {data.payment_method ? <div className="billing-method-value"><strong>{data.payment_method.provider}</strong><span>{data.payment_method.label}</span></div> : <p className="billing-method-value">не привязан</p>}
            {can("CHANGE_METHOD") ? <button className="billing-secondary" type="button" disabled={disabled} onClick={() => void start("CHANGE_METHOD")}>{data.payment_method ? "изменить способ оплаты" : "привязать способ оплаты"}</button> : null}
            <p className="billing-footnote">реквизиты хранятся у платёжного сервиса. подтверждение откроется в браузере</p>
            {paid && !data.auto_renew ? <p className="billing-no-renew">{data.payment_method ? "автоматических списаний нет" : "способ оплаты не привязан. автоматических списаний нет"}</p> : null}
            {can("CANCEL") ? <div className="billing-cancel-area"><p>доступ сохранится до оплаченной даты</p><button className="billing-danger" type="button" disabled={disabled} onClick={() => setConfirm(true)}>отменить подписку</button></div> : null}
          </section>
        </div> : null}
        {pending ? <div className="billing-pending" role="status"><span>ожидаем подтверждения. после оплаты обновим подписку</span>{operation.redirect_url ? <button type="button" className="billing-refresh" onClick={() => void openProvider(operation.redirect_url!)}>открыть платёжный сервис</button> : null}</div> : notice ? <p className="billing-notice" role="status">{notice}</p> : null}
        {error ? <p className="billing-error" role="alert">{error}</p> : null}
      </div>
      {confirm && data?.paid_until ? <CancelConfirmation until={dateLabel(data.paid_until)} onClose={() => setConfirm(false)} onConfirm={() => void start("CANCEL")} /> : null}
    </section>
  );
}

function OfferPrices({ offer, currency }: { readonly offer: Offer; readonly currency: Currency }) {
  const secondary = currency === "RUB" ? "USD" : "RUB";
  return <div className="billing-prices">{[currency, secondary].map((code, i) => <div key={code} className={i === 0 ? "billing-price-primary" : "billing-price-secondary"} aria-label={code === "RUB" ? "цена в рублях" : "цена в долларах"}>{offer.prices[code].original_amount_minor !== null ? <del>{formatPrice(offer.prices[code].original_amount_minor!, code)}</del> : null}<strong>{formatPrice(offer.prices[code].amount_minor, code)}</strong><span>/ месяц</span></div>)}</div>;
}
function planName(plan: string) {
  return plan === "PREMIUM" ? "premium ⭐" : plan === "PLATINUM" ? "platinum 💎" : plan.toLowerCase();
}
function dateLabel(date: string) {
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric" }).format(new Date(date));
}
function CancelConfirmation({ until, onClose, onConfirm }: { readonly until: string; readonly onClose: () => void; readonly onConfirm: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    return () => previous?.focus();
  }, []);
  return <dialog ref={dialog} className="billing-dialog" aria-labelledby="cancel-title" aria-describedby="cancel-description" onCancel={e => { e.preventDefault(); onClose(); }}>
    <h2 id="cancel-title">отменить подписку?</h2>
    <p id="cancel-description">доступ сохранится до {until}. автопродление отключится, способ оплаты отвяжется. новых списаний не будет.</p>
    <div><button className="billing-secondary" type="button" autoFocus onClick={onClose}>оставить подписку</button><button className="billing-danger" type="button" onClick={onConfirm}>да, отменить</button></div>
  </dialog>;
}
