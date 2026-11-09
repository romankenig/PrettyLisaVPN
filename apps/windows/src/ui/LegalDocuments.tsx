import { invoke } from "@tauri-apps/api/core";
import { useState } from "react";
import { t, useLanguage } from "../i18n";

const documents = [
  ["terms", "пользовательское соглашение", "📄"],
  ["privacy", "политика конфиденциальности", "🔐"],
  ["refunds", "возвраты и претензии", "↩"],
  ["payments", "оплата, отмена и продление", "💳"],
] as const;

export function LegalDocuments({ compact = false }: { compact?: boolean }) {
  const language = useLanguage();
  const [failed, setFailed] = useState(false);
  return (
    <section
      className={compact ? "auth-documents" : "about-card legal-documents"}
      aria-label={t("документы")}
    >
      {!compact && <h2>{t("документы")}</h2>}
      <div className="legal-links">
        {documents.map(([document, label, icon]) => (
          <button
            key={document}
            type="button"
            onClick={() => {
              setFailed(false);
              void invoke("open_public_document", { document, language }).catch(
                () => setFailed(true),
              );
            }}
          >
            {!compact && <span aria-hidden="true">{icon}</span>}
            <span>{t(label)}</span>
            {!compact && <span aria-hidden="true">↗</span>}
          </button>
        ))}
      </div>
      {failed && <p role="alert">{t("не удалось открыть документ")}</p>}
    </section>
  );
}
