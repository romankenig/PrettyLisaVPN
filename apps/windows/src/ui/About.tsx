import { t, useLanguage } from "../i18n";
import { useState } from "react";
import { SupportDialog } from "./SupportDialog";
import { Link } from "react-router-dom";

const faq = [
  [
    "как подключиться?",
    "выберите страну и нажмите «подключить». первый поиск соединения может занять пару минут.",
    "/",
    "главная",
  ],
  [
    "что входит в free?",
    "один час VPN в сутки на весь аккаунт. лимит обновляется в 00:00 UTC.",
    "/settings/subscription",
    "подписка",
  ],
  [
    "где управлять подпиской?",
    "в разделе подписки: оплаченный срок, цена, способ оплаты и доступные действия.",
    "/settings/subscription",
    "подписка",
  ],
  [
    "что будет после отмены продления?",
    "оплаченный доступ сохранится до указанной даты. отмена завершена после подтверждения в приложении.",
    "/settings/subscription",
    "подписка",
  ],
  [
    "как выбрать сайты для VPN?",
    "на главной выберите «выбранное» или «кроме выбранного» и нажмите «выбрать сервисы». изменения отключат VPN; затем подключитесь снова.",
    "/",
    "главная",
  ],
  [
    "как связаться с поддержкой?",
    "напишите из приложения или на help@prettylisavpn.com. укажите проблему и время ошибки.",
    "support",
    "написать в поддержку",
  ],
] as const;

export function About({
  frontend,
  backend,
}: {
  readonly frontend: string;
  readonly backend: string;
}) {
  useLanguage();
  const [supportOpen, setSupportOpen] = useState(false);
  const [question, setQuestion] = useState(0);
  const entry = faq[question];
  return (
    <section className="about-page" aria-labelledby="about-title">
      <h1 id="about-title">{t("о приложении")}</h1>
      <dl className="about-versions" aria-label={t("версии компонентов")}>
        <div>
          <dt>frontend</dt>
          <dd>{t(frontend)}</dd>
        </div>
        <div>
          <dt>backend</dt>
          <dd>{t(backend)}</dd>
        </div>
      </dl>
      <div className="about-sections">
        <section className="about-card" aria-labelledby="faq-title">
          <h2 id="faq-title">faq</h2>
          <select
            className="faq-select"
            aria-label={t("вопрос")}
            value={question}
            onChange={(event) => setQuestion(Number(event.target.value))}
          >
            {faq.map(([label], index) => (
              <option key={label} value={index}>
                {t(label)}
              </option>
            ))}
          </select>
          <div className="faq-answer" aria-live="polite">
            <p>{t(entry[1])}</p>
            {entry[2] === "support" ? (
              <button type="button" onClick={() => setSupportOpen(true)}>
                {t(entry[3])}
              </button>
            ) : (
              <Link to={entry[2]}>{t(entry[3])}</Link>
            )}
          </div>
        </section>
        <section className="about-card" aria-labelledby="support-title">
          <h2 id="support-title">{t("помощь и поддержка")}</h2>
          <p>{t("расскажите, с чем нужна помощь")}</p>
          <button type="button" onClick={() => setSupportOpen(true)}>
            {t("написать в поддержку")}
          </button>
        </section>
      </div>
      <p className="about-dedication">inspired by love of my life, Lisa</p>
      {supportOpen ? (
        <SupportDialog
          frontend={frontend}
          backend={backend}
          onClose={() => setSupportOpen(false)}
        />
      ) : null}
    </section>
  );
}
