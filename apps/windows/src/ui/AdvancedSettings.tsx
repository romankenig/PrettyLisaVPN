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
  const displayed = [...connectionMethods].sort((a, b) => {
    const rank = (id: string) =>
      active.includes(id)
        ? active.indexOf(id)
        : active.length +
          connectionMethods.findIndex((method) => method.id === id);
    return rank(a.id) - rank(b.id);
  });
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
        <div className="method-options-heading">
          <h2 id="method-options-title">{t("Способы подключения")}</h2>
          <button
            type="button"
            className="method-randomize"
            title={t("Случайный набор и порядок способов")}
            aria-label={t("Случайный набор и порядок способов")}
            onClick={() => preference.randomize()}
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              aria-hidden="true"
            >
              <path d="M20 11a8 8 0 1 0-2.3 6.7M20 4v7h-7" />
            </svg>
          </button>
        </div>
        <p>
          {t(
            "Изменения применятся при следующем подключении. Выберите хотя бы один способ.",
          )}
        </p>
        <p className="method-order-hint">
          {t(
            "Выбранные способы показаны в порядке попыток. Последний успешный может проверяться первым.",
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
          {displayed.map((method) => (
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
