import { useSyncExternalStore } from "react";
import { Link } from "react-router-dom";
import { t, useLanguage } from "../i18n";
import { connectionMethods } from "../vpn/catalog";
import { getDeviceMethodSelection } from "../vpn/methodSelection";

export function AdvancedSettings({
  preference = getDeviceMethodSelection(),
}: {
  preference?: ReturnType<typeof getDeviceMethodSelection>;
}) {
  useLanguage();
  const selected = useSyncExternalStore(
    preference.subscribe,
    preference.current,
    preference.current,
  );
  const active = selected ?? connectionMethods.map((method) => method.id);
  return (
    <section
      className="settings-page advanced-settings"
      aria-labelledby="advanced-title"
    >
      <Link className="settings-back" to="/settings">
        {t("← настройки")}
      </Link>
      <h1 id="advanced-title">{t("Расширенные настройки")}</h1>
      <div
        className="method-options"
        role="group"
        aria-labelledby="method-options-title"
      >
        <h2 id="method-options-title">{t("Способы подключения")}</h2>
        <p>
          {t(
            "Изменения применятся при следующем подключении. Выберите хотя бы один способ.",
          )}
        </p>
        <label className="method-checkbox method-checkbox--all">
          <input
            type="checkbox"
            checked={selected === null}
            disabled={selected === null}
            onChange={() => preference.all()}
          />
          <span>{t("Все способы")}</span>
        </label>
        <div className="method-grid">
          {connectionMethods.map((method) => (
            <label key={method.id} className="method-checkbox">
              <input
                type="checkbox"
                checked={active.includes(method.id)}
                disabled={active.length === 1 && active.includes(method.id)}
                onChange={() => preference.toggle(method.id)}
              />
              <span>{method.name}</span>
            </label>
          ))}
        </div>
      </div>
    </section>
  );
}
