import { useApplication } from "../state/application";
import { useRegistration } from "../auth/useRegistration";
import { t, useLanguage } from "../i18n";
import { Fragment, useState, useSyncExternalStore } from "react";
import { LegalDocuments } from "./LegalDocuments";
import { SupportDialog } from "./SupportDialog";
import { invoke } from "@tauri-apps/api/core";
import catalog from "../faq.json";

export function About({
  frontend,
  backend,
}: {
  readonly frontend: string;
  readonly backend: string;
}) {
  const language = useLanguage();
  const faq = catalog[language];
  const [linkFailed, setLinkFailed] = useState(false);
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
  let linkIndex = 0;
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
            {faq.map(({ id, q }, index) => (
              <option key={id} value={index}>
                {q}
              </option>
            ))}
          </select>
          <div
            className="faq-answer"
            aria-live="polite"
            aria-label={entry.q}
            key={question}
            tabIndex={0}
          >
            {entry.a.split("\n\n").map((paragraph, paragraphIndex) => (
              <p key={paragraphIndex}>
                {paragraph.split(/(\[[^\]]+\])/).map((part, index) => {
                  if (!part.startsWith("[") || !part.endsWith("]"))
                    return <Fragment key={index}>{part}</Fragment>;
                  const label = part.slice(1, -1);
                  const target = entry.links[linkIndex++];
                  return (
                    <button
                      className="faq-inline-link"
                      type="button"
                      key={index}
                      onClick={() => {
                        if (target === "support") openSupport();
                        else {
                          setLinkFailed(false);
                          void invoke("open_public_document", {
                            document: "payments",
                            language,
                          }).catch(() => setLinkFailed(true));
                        }
                      }}
                    >
                      {label}
                    </button>
                  );
                })}
              </p>
            ))}
          </div>
          {linkFailed && <p role="alert">{t("не удалось открыть документ")}</p>}
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
