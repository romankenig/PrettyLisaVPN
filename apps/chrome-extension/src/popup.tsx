import React, { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { NavigationIcon } from "./NavigationIcon";
import type { Device, Snapshot } from "./model";
import type { Billing, Money } from "./billing";
import "./style.css";

import {
  labels,
  languageCode,
  translate,
  publicUrl,
  legalKeys,
  type Language,
  type Label,
} from "./i18n";
import { LanguagePicker } from "./LanguagePicker";
type Page =
  "home" | "settings" | "about" | "devices" | "subscription" | "support";

async function send<T>(
  type: string,
  fields: Record<string, unknown> = {},
): Promise<T> {
  const result = await chrome.runtime.sendMessage({ type, ...fields });
  if (!result?.ok) throw new Error(result?.code ?? "REQUEST_FAILED");
  return result.value as T;
}
function App() {
  const [language, setLanguage] = useState<Language>("ru"),
    [page, setPage] = useState<Page>("home");
  const [state, setState] = useState<Snapshot | null>(null),
    [error, setError] = useState<string | null>(null),
    [busy, setBusy] = useState(false);
  const [draftEmail, setEmail] = useState(""),
    [code, setCode] = useState(""),
    [country, setCountry] = useState("AUTO");
  const otp = Boolean(state?.otpEmail);
  const email = state?.otpEmail ?? draftEmail;
  const [devices, setDevices] = useState<Device[]>([]),
    [billing, setBilling] = useState<Billing | null>(null);
  const [subject, setSubject] = useState(""),
    [description, setDescription] = useState(""),
    [requestId, setRequestId] = useState(() => crypto.randomUUID()),
    [sent, setSent] = useState(false);
  const t = (key: Label) => translate(key, language);
  const refresh = useCallback(async () => {
    setState(await send<Snapshot>("snapshot"));
  }, []);
  useEffect(() => {
    void chrome.storage.local
      .get("language")
      .then((v) => setLanguage(languageCode(v.language)));
    void refresh().catch(() => setError("REQUEST_FAILED"));
    void send("refresh")
      .then(refresh)
      .catch(() => undefined);
    const timer = setInterval(() => {
      void refresh().catch(() => undefined);
    }, 1500);
    return () => clearInterval(timer);
  }, [refresh]);
  const action = async (task: () => Promise<unknown>) => {
    setError(null);
    setBusy(true);
    try {
      await task();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "REQUEST_FAILED");
    } finally {
      setBusy(false);
    }
  };
  const navigate = (next: Page) => {
    if (
      state?.account?.plan === "DEMO" &&
      (next === "subscription" || next === "support")
    ) {
      register();
      return;
    }
    setPage(next);
    setError(null);
    if (next === "devices")
      void action(async () => {
        setDevices([]);
        setDevices(await send<Device[]>("devices"));
      });
    if (next === "subscription")
      void action(async () => setBilling(await send<Billing>("billing")));
  };
  const date = (value: string | null) =>
    value ? new Date(value).toLocaleString(language) : "—";
  const demo = state?.account?.plan === "DEMO";
  const register = () =>
    void action(async () => {
      await send("logout");
      setPage("home");
      setEmail("");
      setCode("");
      setCountry("AUTO");
    });
  const connected = state?.phase === "CONNECTED";
  const active =
    state &&
    ["CONNECTED", "CONNECTING", "VERIFYING", "FAILED"].includes(state.phase);
  const seconds =
    state?.account?.entitlements?.free_seconds_usable ??
    state?.account?.entitlements?.free_seconds_remaining;
  const mainTab =
    page === "devices" || page === "subscription"
      ? "settings"
      : page === "support"
        ? "about"
        : page;
  const shownError = error ?? state?.error;
  return (
    <div className="shell">
      <aside>
        <nav aria-label={t("navigation")}>
          {(["home", "settings", "about"] as const).map((tab) => (
            <button
              key={tab}
              disabled={!state?.signedIn || busy}
              title={t(tab)}
              aria-label={t(tab)}
              aria-current={mainTab === tab ? "page" : undefined}
              onClick={() => navigate(tab)}
            >
              <NavigationIcon name={tab} />
            </button>
          ))}
        </nav>
        <div className="side-bottom">
          <LanguagePicker
            language={language}
            onChange={(next) => {
              setLanguage(next);
              void chrome.storage.local.set({ language: next });
            }}
          />
          <span>
            frontend
            <br />
            <b>{chrome.runtime.getManifest().version}</b>
          </span>
          <span>
            backend
            <br />
            <b title={state?.backend ?? ""}>
              {state?.backend?.split("-")[0] ?? t("unavailable")}
            </b>
          </span>
        </div>
      </aside>
      <main>
        <header>
          <img src="logo.svg" alt="PrettyLisaVPN" />
          <span>chrome extension</span>
        </header>
        {shownError && shownError !== "VPN_CLEANUP_PENDING" && (
          <div className="error" role="alert">
            {t(shownError in labels ? (shownError as Label) : "genericError")}
            <small>{shownError}</small>
          </div>
        )}
        {state?.cleanupPending && (
          <p className="notice" role="status">
            {t("cleanup")}
          </p>
        )}
        {!state ? (
          <p className="white" role="status">
            …
          </p>
        ) : !state.signedIn ? (
          <section className="card">
            <h1>{t("login")}</h1>
            <p>{t("loginDetail")}</p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void action(async () => {
                  if (otp) {
                    await send("login", { email, code });
                    setPage("home");
                    setCode("");
                  } else {
                    await send("requestOtp", { email });
                  }
                });
              }}
            >
              <label>
                {t("email")}
                <input
                  type="email"
                  autoComplete="email"
                  value={email}
                  maxLength={254}
                  readOnly={otp}
                  required
                  onChange={(e) => setEmail(e.target.value)}
                />
              </label>
              {otp && (
                <label>
                  {t("otp")}
                  <input
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    value={code}
                    pattern="[0-9]{6}"
                    maxLength={6}
                    required
                    onChange={(e) => setCode(e.target.value)}
                  />
                </label>
              )}
              <button className="primary" disabled={busy}>
                {t(otp ? "enter" : "sendCode")}
              </button>
              {otp && (
                <button
                  type="button"
                  className="text"
                  disabled={busy}
                  onClick={() => {
                    void action(async () => {
                      await send("resetOtp");
                      setEmail("");
                      setCode("");
                    });
                  }}
                >
                  {t("otherEmail")}
                </button>
              )}
            </form>
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() =>
                void action(async () => {
                  await send("demo");
                  setPage("home");
                  setCountry("AUTO");
                  setCode("");
                })
              }
            >
              {t("demo")}
            </button>
            <p className="muted">{t("demoDetail")}</p>
            <PublicLinks language={language} />
          </section>
        ) : (
          <>
            {!["home", "settings", "about"].includes(page) && (
              <button
                className="back"
                onClick={() => navigate(mainTab)}
                disabled={busy}
              >
                ← {t("back")}
              </button>
            )}
            {page === "home" && (
              <>
                <section className="card account">
                  <label>{t("account")}</label>
                  <strong className="email">
                    {demo ? t("guest") : (state.account?.email ?? "…")}
                  </strong>
                  {demo && (
                    <button className="text" disabled={busy} onClick={register}>
                      {t("register")}
                    </button>
                  )}
                  <div className="columns">
                    <div>
                      <label>{t("plan")}</label>
                      <strong>
                        {demo
                          ? "demo 🌱"
                          : state.account?.plan === "PLATINUM"
                            ? "Platinum 💎"
                            : state.account?.plan === "PREMIUM"
                              ? "Premium"
                              : "Free"}
                      </strong>
                      {state.account?.plan === "FREE" && (
                        <button
                          className="text"
                          onClick={() => navigate("subscription")}
                        >
                          {t("upgrade")}
                        </button>
                      )}
                    </div>
                    <div>
                      <label>{t("activeDevices")}</label>
                      <strong>
                        {state.account?.active_device_count ?? "…"} /{" "}
                        {demo ? 1 : 5}
                      </strong>
                    </div>
                  </div>
                  {typeof seconds === "number" && (
                    <div className="balance">
                      <span>{t("remaining")}</span>
                      <b>
                        {Math.floor(seconds / 60)}:
                        {String(seconds % 60).padStart(2, "0")}
                      </b>
                    </div>
                  )}
                </section>
                <section className="card">
                  <h2>{t("destination")}</h2>
                  <select
                    className="country"
                    aria-label={t("destination")}
                    value={demo ? "AUTO" : country}
                    disabled={!!active || busy || demo}
                    onChange={(e) => setCountry(e.target.value)}
                  >
                    <option value="AUTO">{t("auto")}</option>
                    {state.countries.map((item) => (
                      <option
                        key={item.country_code}
                        value={item.country_code}
                        disabled={!item.available}
                      >
                        {new Intl.DisplayNames([language], {
                          type: "region",
                        }).of(item.country_code)}
                      </option>
                    ))}
                  </select>
                  {demo && (
                    <button className="text" disabled={busy} onClick={register}>
                      {t("locationRegistration")}
                    </button>
                  )}
                  <button
                    className="primary"
                    disabled={
                      (!active && demo && seconds === 0) ||
                      busy ||
                      state.phase === "DISCONNECTING" ||
                      state.cleanupPending
                    }
                    onClick={() =>
                      void action(() =>
                        send(active ? "disconnect" : "connect", {
                          country: demo ? "AUTO" : country,
                        }),
                      )
                    }
                  >
                    {t(active ? "disconnect" : "connect")}
                  </button>
                  <h2 className="status" role="status">
                    {t(state.phase)}
                  </h2>
                  <p>HTTPS proxy · {t("browser")}</p>
                  {connected && (
                    <div className="connection">
                      <span>{state.country}</span>
                      <span>IP: {state.ip}</span>
                    </div>
                  )}
                </section>
                <section className="card">
                  <h2>{t("scope")}</h2>
                  <strong className="purple">{t("browser")}</strong>
                  <p className="muted">{t("scopeDetail")}</p>
                </section>
              </>
            )}
            {page === "settings" && (
              <>
                <h1 className="white">{t("settings")}</h1>
                {(
                  [
                    ["subscription", "subscriptionDetail"],
                    ["devices", "devicesDetail"],
                  ] as const
                ).map(([next, detail]) => (
                  <button
                    className="setting card"
                    key={next}
                    onClick={() => navigate(next)}
                  >
                    <NavigationIcon name={next} />
                    <span>
                      <strong>{t(next)}</strong>
                      <small>{t(detail)}</small>
                    </span>
                    <span>→</span>
                  </button>
                ))}
                <button
                  className="setting danger"
                  disabled={busy}
                  onClick={() => {
                    if (confirm(t("logoutConfirm")))
                      void action(() => send("logout"));
                  }}
                >
                  <NavigationIcon name="logout" />
                  <span>
                    <strong>{t("logout")}</strong>
                    <small>{t("logoutDetail")}</small>
                  </span>
                </button>
              </>
            )}
            {page === "devices" && (
              <>
                <h1 className="white">{t("devices")}</h1>
                {devices.map((device) => (
                  <section className="card" key={device.id}>
                    <h2>{device.device_name}</h2>
                    {device.is_current && (
                      <span className="tag">{t("current")}</span>
                    )}
                    <p>
                      {device.status === "ACTIVE" || device.status === "REVOKED"
                        ? t(device.status)
                        : device.status}
                    </p>
                    <label>id</label>
                    <code>{device.id}</code>
                    <label>{t("added")}</label>
                    <strong>{date(device.created_at)}</strong>
                    <label>{t("lastLogin")}</label>
                    <strong>{date(device.last_login_at)}</strong>
                    <button
                      className="primary"
                      disabled={busy || device.status !== "ACTIVE"}
                      onClick={() => {
                        if (confirm(t("revokeConfirm")))
                          void action(async () => {
                            await send("revokeDevice", { id: device.id });
                            setDevices([]);
                            if (!device.is_current)
                              setDevices(await send<Device[]>("devices"));
                          });
                      }}
                    >
                      {t("revoke")}
                    </button>
                  </section>
                ))}
              </>
            )}
            {page === "subscription" && (
              <>
                <h1 className="white">{t("subscription")}</h1>
                <section className="card">
                  {billing && (
                    <>
                      <label>{t("plan")}</label>
                      <h2>{billing?.plan ?? "…"}</h2>
                      <label>{t("paidUntil")}</label>
                      <strong>{date(billing?.paid_until ?? null)}</strong>
                      {billing?.current_price && (
                        <>
                          <label>{t("contractPrice")}</label>
                          <strong>
                            {priceLabel(billing.current_price, language)} /{" "}
                            {t("monthly")}
                          </strong>
                        </>
                      )}
                      {billing?.current_price &&
                        !billing.new_contract_required && (
                          <p>{t("fixedPrice")}</p>
                        )}
                      {billing?.plan === "PREMIUM" &&
                        billing.new_contract_required && (
                          <p>{t("resubscribe")}</p>
                        )}
                      <label>{t("method")}</label>
                      <strong>
                        {billing?.methodKind === "SBP"
                          ? t("sbpAccount")
                          : (billing?.method ?? t("noMethod"))}
                      </strong>
                      {billing?.next_charge_at && billing.next_charge_price && (
                        <>
                          <label>{t("nextCharge")}</label>
                          <strong>
                            {date(billing.next_charge_at)} ·{" "}
                            {priceLabel(billing.next_charge_price, language)}
                          </strong>
                        </>
                      )}
                    </>
                  )}
                  {!billing && (
                    <div data-testid="billing-reference-prices">
                      <h2>Premium</h2>
                      <p className="reference-price">
                        <s>499 ₽</s> <strong>399 ₽</strong> · <s>$7</s>{" "}
                        <strong>$5</strong> / {t("monthly")}
                      </p>
                      <p>{t("referencePrices")}</p>
                    </div>
                  )}
                  {billing?.offers.map((offer) => (
                    <div key={offer.id}>
                      <h2>Premium</h2>
                      <p>
                        {priceLabel(offer.prices.RUB, language)} ·{" "}
                        {priceLabel(offer.prices.USD, language)} /{" "}
                        {t("monthly")}
                      </p>
                    </div>
                  ))}
                  <p>{t("billingPortalHint")}</p>
                  <button
                    className="primary"
                    disabled={busy}
                    onClick={() =>
                      void action(async () => {
                        await send("billingPortal");
                      })
                    }
                  >
                    {t("billingPortal")}
                  </button>
                  <a
                    href="https://prettylisavpn.com/#pricing"
                    target="_blank"
                    rel="noreferrer"
                  >
                    prettylisavpn.com ↗
                  </a>
                </section>
              </>
            )}
            {page === "about" && (
              <>
                <h1 className="white">{t("about")}</h1>
                <section className="card">
                  <h2>faq</h2>
                  {(
                    [
                      ["faqTitle", "faqText"],
                      ["faqFree", "freeText"],
                      ["scopeFAQ", "scopeFAQText"],
                    ] as const
                  ).map(([title, text]) => (
                    <details key={title}>
                      <summary>{t(title)}</summary>
                      <p>{t(text)}</p>
                    </details>
                  ))}
                </section>
                <section className="card">
                  <h2>{t("support")}</h2>
                  <p className="muted">{t("supportDetail")}</p>
                  <button
                    className="primary"
                    onClick={() => navigate("support")}
                  >
                    {t("writeSupport")}
                  </button>
                </section>
                <details className="card">
                  <summary>{t("privacy")}</summary>
                  <p>{t("privacyText")}</p>
                </details>
                <section className="card">
                  <h2>{t("documents")}</h2>
                  <PublicLinks language={language} />
                </section>
                <p className="credit">inspired by love of my life, Lisa</p>
              </>
            )}
            {page === "support" && (
              <>
                <h1 className="white">{t("support")}</h1>
                <section className="card">
                  {sent ? (
                    <p role="status">{t("accepted")}</p>
                  ) : (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        void action(async () => {
                          const receipt = await send<{ status: string }>(
                            "support",
                            { id: requestId, subject, description },
                          );
                          if (
                            ["ACCEPTED", "RETRYING", "SENT"].includes(
                              receipt.status,
                            )
                          )
                            setSent(true);
                          else throw new Error("SUPPORT_FAILED");
                        });
                      }}
                    >
                      <label>
                        {t("subject")}
                        <input
                          value={subject}
                          maxLength={120}
                          required
                          onChange={(e) => {
                            setSubject(e.target.value);
                            setRequestId(crypto.randomUUID());
                          }}
                        />
                      </label>
                      <label>
                        {t("description")}
                        <textarea
                          value={description}
                          rows={5}
                          maxLength={4000}
                          required
                          onChange={(e) => {
                            setDescription(e.target.value);
                            setRequestId(crypto.randomUUID());
                          }}
                        />
                      </label>
                      <p>{state.account?.email}</p>
                      <button className="primary" disabled={busy}>
                        {t("send")}
                      </button>
                    </form>
                  )}
                  <a href="mailto:help@prettylisavpn.com">
                    help@prettylisavpn.com
                  </a>
                </section>
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

function priceLabel(price: Money, language: Language): string {
  return new Intl.NumberFormat(language, {
    style: "currency",
    currency: price.currency,
    minimumFractionDigits: price.amount_minor % 100 ? 2 : 0,
    maximumFractionDigits: 2,
  }).format(price.amount_minor / 100);
}

function PublicLinks({ language }: { language: Language }) {
  return (
    <div className="public-links">
      {legalKeys.map((key) => (
        <a
          key={key}
          href={publicUrl(language, key)}
          target="_blank"
          rel="noreferrer"
        >
          {translate(key === "privacy" ? "privacyPolicy" : key, language)}
        </a>
      ))}
      <a
        className="product-name"
        href={publicUrl(language)}
        target="_blank"
        rel="noreferrer"
      >
        {translate("website", language)} ↗
      </a>
    </div>
  );
}
