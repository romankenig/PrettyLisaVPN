import { useApplication } from "../state/application";
import { useRegistration } from "../auth/useRegistration";
import { t, useLanguage } from "../i18n";
import { Fragment, useState, useSyncExternalStore } from "react";
import { LegalDocuments } from "./LegalDocuments";
import { SupportDialog } from "./SupportDialog";
import { Link } from "react-router-dom";

const faq = [
  [
    "как подключиться?",
    "на [главной] выберите страну и нажмите «подключить». первый поиск соединения может занять пару минут.",
    "/",
  ],
  [
    "что входит в free?",
    "один час VPN в сутки на весь аккаунт. лимит обновляется в 00:00 UTC.",
    null,
  ],
  [
    "где управлять подпиской?",
    "в [подписке] можно посмотреть оплаченный срок, цену, способ оплаты и доступные действия.",
    "/settings/subscription",
  ],
  [
    "что будет после отмены продления?",
    "если автопродление включено, отключите его в [подписке]. дождитесь подтверждения отмены: оплаченный доступ сохранится до указанной даты.",
    "/settings/subscription",
  ],
  [
    "как выбрать сайты для VPN?",
    "разделение трафика позволяет выбрать, что открывать через VPN, а что — через обычное подключение. режим меняется на [главной] в блоке «что защищаем».\n\n«всё» — весь трафик идёт через VPN.\n\n«выбранное» — через VPN идут только сервисы из списка. например, YouTube и Telegram; остальные сайты и приложения используют обычное подключение.\n\n«кроме выбранного» — наоборот: сервисы из списка идут напрямую, а остальной трафик — через VPN. например, можно исключить Госуслуги и MAX.\n\nнажмите «выбрать сервисы», включите нужные или добавьте свою маску: youtube.com для этого домена, *.youtube.com — для его поддоменов. у одного сервиса может быть несколько доменов, поэтому удобнее выбрать готовый вариант.\n\nу двух режимов отдельные списки. сохранение изменений отключает VPN — подключитесь заново, чтобы применить выбор.",
    "/",
  ],
  [
    "как связаться с поддержкой?",
    "откройте [форму поддержки] в приложении или напишите на help@prettylisavpn.com. укажите проблему и время ошибки.",
    "support",
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
  const { session } = useApplication();
  const active = useSyncExternalStore(
    session.subscribe,
    session.current,
    session.current,
  );
  const registration = useRegistration();
  const openSupport = () => {
    if (active?.plan === "DEMO") void registration.register();
    else setSupportOpen(true);
  };
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
        <section className="about-card faq-card" aria-labelledby="faq-title">
          <h2 id="faq-title">FAQ</h2>
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
          <div
            className="faq-answer"
            aria-live="polite"
            aria-label={t(entry[0])}
            key={question}
            tabIndex={0}
          >
            {t(entry[1])
              .split("\n\n")
              .map((paragraph, paragraphIndex) => (
                <p key={paragraphIndex}>
                  {paragraph.split(/(\[[^\]]+\])/).map((part, index) => {
                    if (
                      !part.startsWith("[") ||
                      !part.endsWith("]") ||
                      !entry[2]
                    )
                      return <Fragment key={index}>{part}</Fragment>;
                    const label = part.slice(1, -1);
                    return entry[2] === "support" ? (
                      <button
                        className="faq-inline-link"
                        type="button"
                        key={index}
                        onClick={openSupport}
                      >
                        {label}
                      </button>
                    ) : (
                      <Link
                        className="faq-inline-link"
                        key={index}
                        to={entry[2]}
                      >
                        {label}
                      </Link>
                    );
                  })}
                </p>
              ))}
          </div>
        </section>
        <section className="about-card" aria-labelledby="support-title">
          <h2 id="support-title">{t("помощь и поддержка")}</h2>
          <p>{t("расскажите, с чем нужна помощь")}</p>
          <button type="button" onClick={openSupport}>
            {t("написать в поддержку")}
          </button>
        </section>
      </div>
      {registration.error && (
        <p role="alert">
          {t("не удалось завершить гостевую сессию. попробуйте снова")}
        </p>
      )}
      <LegalDocuments />
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
