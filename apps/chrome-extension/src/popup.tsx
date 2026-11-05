import React, { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { NavigationIcon } from "./NavigationIcon";
import type { Device, Snapshot } from "./model";
import "./style.css";

const labels = {
  home: ["главная", "home"],
  settings: ["настройки", "settings"],
  about: ["о приложении", "about"],
  account: ["аккаунт", "account"],
  plan: ["план", "plan"],
  devices: ["устройства", "devices"],
  activeDevices: ["активные устройства", "active devices"],
  destination: ["куда подключаемся", "where to connect"],
  auto: ["🌐 автопилот", "🌐 autopilot"],
  connect: ["подключить", "connect"],
  disconnect: ["отключить", "disconnect"],
  DISCONNECTED: ["не подключено", "not connected"],
  CONNECTING: ["подключаемся…", "connecting…"],
  VERIFYING: ["проверяем интернет…", "verifying internet…"],
  CONNECTED: ["подключено", "connected"],
  DISCONNECTING: ["отключаемся…", "disconnecting…"],
  FAILED: ["подключение не подтверждено", "connection not verified"],
  scope: ["что защищаем", "what we protect"],
  browser: ["сайты в Chrome", "websites in Chrome"],
  scopeDetail: [
    "Трафик других приложений и режим инкогнито не защищены этим расширением.",
    "Other apps and incognito traffic are not protected by this extension.",
  ],
  remaining: ["осталось сегодня", "remaining today"],
  subscription: ["подписка", "subscription"],
  subscriptionDetail: [
    "ваш план и оплаченный период",
    "your plan and paid period",
  ],
  devicesDetail: ["управление доступом к аккаунту", "manage account access"],
  logout: ["выйти", "sign out"],
  logoutDetail: [
    "завершить сессию в этом браузере",
    "end this browser session",
  ],
  back: ["назад", "back"],
  unavailable: ["недоступна", "unavailable"],
  refresh: ["обновить", "refresh"],
  login: ["вход в аккаунт", "sign in"],
  email: ["ваша почта", "your email"],
  sendCode: ["получить код", "get a code"],
  otp: ["код из письма", "email code"],
  enter: ["войти", "sign in"],
  otherEmail: ["другая почта", "another email"],
  loginDetail: [
    "Без пароля. Пришлём шестизначный код на вашу почту.",
    "No password. We will email you a six-digit code.",
  ],
  sessionDetail: [
    "Вход действует до закрытия браузера. Секреты сессии не сохраняются на диск расширением.",
    "Sign-in lasts until the browser closes. The extension does not persist session secrets to disk.",
  ],
  current: ["это устройство", "this device"],
  added: ["добавлено", "added"],
  lastLogin: ["последний вход", "last sign-in"],
  revoke: ["отозвать доступ", "revoke access"],
  revokeConfirm: [
    "Отозвать доступ у этого устройства? Его подключение будет завершено.",
    "Revoke this device? Its connection will end.",
  ],
  logoutConfirm: [
    "Отключить прокси и выйти из аккаунта?",
    "Disconnect the proxy and sign out?",
  ],
  support: ["помощь и поддержка", "help and support"],
  writeSupport: ["написать в поддержку", "contact support"],
  supportDetail: [
    "расскажите, с чем нужна помощь",
    "tell us what you need help with",
  ],
  subject: ["тема", "subject"],
  description: ["что случилось?", "what happened?"],
  send: ["отправить", "send"],
  accepted: [
    "Обращение принято. Ответ придёт на почту аккаунта.",
    "Request accepted. We will reply to your account email.",
  ],
  faqTitle: ["как подключиться?", "how do I connect?"],
  faqText: [
    "Выберите страну на главной и нажмите «подключить». Статус появится после проверки реального выхода в интернет через сервер.",
    "Choose a country on Home and connect. The connected status appears after verifying internet access through the server.",
  ],
  faqFree: ["что входит в free?", "what is included in free?"],
  freeText: [
    "Один общий час в сутки на аккаунт, без рекламы. Лимит обновляется в 00:00 UTC; неиспользованное время возвращается после подтверждённого отключения на сервере.",
    "One shared hour per account per UTC day, without ads. Unused time returns after confirmed server cleanup.",
  ],
  privacy: ["Конфиденциальность", "Privacy"],
  privacyText: [
    "Расширение не собирает историю посещений, DNS-запросы или содержимое страниц. Доступ ко всем сайтам нужен для авторизации у прокси. Настройки WebRTC ограничиваются на время подключения и восстанавливаются при отключении.",
    "The extension does not collect browsing history, DNS queries or page content. All-sites permission enables proxy authentication. WebRTC settings are restricted while connected and restored on disconnect.",
  ],
  scopeFAQ: ["что не входит в защиту?", "what is outside this protection?"],
  scopeFAQText: [
    "Расширение использует HTTPS-прокси для обычного веб-трафика. Системные службы Chrome, другие приложения и инкогнито находятся вне его действия. DNS сайтов разрешает сервер; IPv6 к назначениям блокируется. Локальные адреса и нестандартные порты, кроме 80, 443, 8080 и 8443, недоступны через прокси.",
    "The HTTPS proxy covers ordinary web traffic. Chrome internal services, other apps and incognito are outside its scope. Website DNS resolves on the server; IPv6 destinations are blocked. Local addresses and ports other than 80, 443, 8080 and 8443 are unavailable through the proxy.",
  ],
  paidUntil: ["оплачено до", "paid until"],
  billingReadOnly: [
    "Управление оплатой в расширении пока недоступно.",
    "Payment management is not yet available in the extension.",
  ],
  cleanup: [
    "Настройки браузера восстановлены. Ожидаем подтверждения удаления доступа на сервере.",
    "Browser settings restored. Waiting for confirmed server cleanup.",
  ],
  genericError: [
    "Не удалось выполнить действие. Повторите попытку.",
    "The action failed. Please retry.",
  ],
} as const;
type Label = keyof typeof labels;
type Page =
  "home" | "settings" | "about" | "devices" | "subscription" | "support";
type Billing = { plan: string; paid_until: string | null; status: string };

async function send<T>(
  type: string,
  fields: Record<string, unknown> = {},
): Promise<T> {
  const result = await chrome.runtime.sendMessage({ type, ...fields });
  if (!result?.ok) throw new Error(result?.code ?? "REQUEST_FAILED");
  return result.value as T;
}
function App() {
  const [language, setLanguage] = useState(0),
    [page, setPage] = useState<Page>("home");
  const [state, setState] = useState<Snapshot | null>(null),
    [error, setError] = useState<string | null>(null),
    [busy, setBusy] = useState(false);
  const [email, setEmail] = useState(""),
    [code, setCode] = useState(""),
    [otp, setOtp] = useState(false),
    [country, setCountry] = useState("AUTO");
  const [devices, setDevices] = useState<Device[]>([]),
    [billing, setBilling] = useState<Billing | null>(null);
  const [subject, setSubject] = useState(""),
    [description, setDescription] = useState(""),
    [requestId, setRequestId] = useState(() => crypto.randomUUID()),
    [sent, setSent] = useState(false);
  const t = (key: Label) => labels[key][language];
  const refresh = useCallback(async () => {
    setState(await send<Snapshot>("snapshot"));
  }, []);
  useEffect(() => {
    void chrome.storage.local
      .get("language")
      .then((v) => setLanguage(v.language === "en" ? 1 : 0));
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
    setPage(next);
    setError(null);
    if (next === "devices")
      void action(async () => {
        const value = await send<{ devices: Device[] }>("devices");
        setDevices(value.devices);
      });
    if (next === "subscription")
      void action(async () => setBilling(await send<Billing>("billing")));
  };
  const date = (value: string | null) =>
    value ? new Date(value).toLocaleString(language ? "en" : "ru") : "—";
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
  const errors: Record<string, string> = {
    NETWORK_ERROR: language
      ? "Network unavailable. Proxy protection is not verified."
      : "Сеть недоступна. Подключение через прокси не подтверждено.",
    EGRESS_MISMATCH: language
      ? "Server exit IP was not confirmed."
      : "Выход через выбранный сервер не подтверждён.",
    PROXY_CONTROL_LOST: language
      ? "Another extension or browser policy controls the proxy."
      : "Прокси контролирует другое расширение или политика браузера.",
    PRIVACY_CONTROL_LOST: language
      ? "Browser policy prevents safe WebRTC settings."
      : "Политика браузера не позволяет применить настройки WebRTC.",
    RATE_LIMITED: language
      ? "Too many requests. Please wait before retrying."
      : "Слишком много запросов. Подождите перед повторной попыткой.",
    FREE_QUOTA_EXHAUSTED: language
      ? "Today's free hour is exhausted."
      : "Бесплатный час на сегодня закончился.",
    FREE_QUOTA_RESERVED: language
      ? "Free time is reserved by another active device."
      : "Бесплатное время занято другим активным устройством.",
    SIGN_IN_REQUIRED: language
      ? "Sign in again to continue."
      : "Для продолжения войдите снова.",
    VPN_NO_AVAILABLE_NODE: language
      ? "No proxy servers are currently available."
      : "Сейчас нет доступных прокси-серверов.",
    INVALID_OTP: language
      ? "Check the code from your email."
      : "Проверьте код из письма.",
  };
  const shownError = error ?? state?.error;
  return (
    <div className="shell">
      <aside>
        <nav aria-label={language ? "Main navigation" : "Основная навигация"}>
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
          <select
            aria-label="Language"
            value={language}
            onChange={(e) => {
              const next = Number(e.target.value);
              setLanguage(next);
              void chrome.storage.local.set({ language: next ? "en" : "ru" });
            }}
          >
            <option value={0}>RU</option>
            <option value={1}>EN</option>
          </select>
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
          <span>Chrome Extension</span>
        </header>
        {shownError && shownError !== "VPN_CLEANUP_PENDING" && (
          <div className="error" role="alert">
            {errors[shownError] ?? t("genericError")}
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
                    setOtp(true);
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
                    setOtp(false);
                    setCode("");
                  }}
                >
                  {t("otherEmail")}
                </button>
              )}
            </form>
            <p className="muted">{t("sessionDetail")}</p>
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
                    {state.account?.email ?? "…"}
                  </strong>
                  <div className="columns">
                    <div>
                      <label>{t("plan")}</label>
                      <strong>
                        {state.account?.plan === "PLATINUM"
                          ? "Platinum 💎"
                          : state.account?.plan === "PREMIUM"
                            ? "Premium"
                            : "Free"}
                      </strong>
                    </div>
                    <div>
                      <label>{t("activeDevices")}</label>
                      <strong>
                        {state.account?.active_device_count ?? "…"} / 5
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
                    value={country}
                    disabled={!!active || busy}
                    onChange={(e) => setCountry(e.target.value)}
                  >
                    <option value="AUTO">{t("auto")}</option>
                    {state.countries.map((item) => (
                      <option
                        key={item.country_code}
                        value={item.country_code}
                        disabled={!item.available}
                      >
                        {new Intl.DisplayNames([language ? "en" : "ru"], {
                          type: "region",
                        }).of(item.country_code)}
                      </option>
                    ))}
                  </select>
                  <button
                    className="primary"
                    disabled={
                      busy ||
                      state.phase === "DISCONNECTING" ||
                      state.cleanupPending
                    }
                    onClick={() =>
                      void action(() =>
                        send(active ? "disconnect" : "connect", { country }),
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
                <section className="card">
                  <strong>HTTPS proxy</strong>
                  <p className="muted">{t("scopeDetail")}</p>
                  <button
                    className="text"
                    disabled={busy}
                    onClick={() => void action(() => send("refresh"))}
                  >
                    {t("refresh")}
                  </button>
                </section>
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
                    <p>{device.status}</p>
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
                            const next = await send<{ devices: Device[] }>(
                              "devices",
                            ).catch(() => ({ devices: [] }));
                            setDevices(next.devices);
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
                  <label>{t("plan")}</label>
                  <h2>{billing?.plan ?? "…"}</h2>
                  <label>{t("paidUntil")}</label>
                  <strong>{date(billing?.paid_until ?? null)}</strong>
                  <p>{t("billingReadOnly")}</p>
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
