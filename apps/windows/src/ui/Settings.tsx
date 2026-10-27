import { t, useLanguage } from "../i18n";
import { useRef, useState, useSyncExternalStore } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { ApiError } from "../api/client";
import { useApplication } from "../state/application";
import { Devices } from "./Devices";
import { Subscription } from "./Subscription";
import { NavigationIcon } from "./NavigationIcon";

export function Settings() {
  useLanguage();
  return (
    <Routes>
      <Route index element={<SettingsOverview />} />
      <Route path="subscription" element={<Subscription />} />
      <Route
        path="devices"
        element={
          <div className="settings-devices">
            <Link className="settings-back" to="/settings">
              {t("← настройки")}
            </Link>
            <Devices />
          </div>
        }
      />
    </Routes>
  );
}

function SettingsOverview() {
  useLanguage();
  const { api, session, vpnConnection } = useApplication();
  const activeSession = useSyncExternalStore(
    session.subscribe,
    session.current,
    session.current,
  );
  const [logoutState, setLogoutState] = useState<
    "idle" | "submitting" | "error"
  >("idle");
  const logoutInFlight = useRef(false);

  async function logout() {
    if (logoutInFlight.current || activeSession === null) return;
    logoutInFlight.current = true;
    setLogoutState("submitting");
    try {
      const token = await session.bearer(api);
      await vpnConnection.disconnect(token);
      await api.logout(token);
      await session.clear();
    } catch (error) {
      if (
        error instanceof ApiError &&
        (error.code === "AUTH_INVALID" || error.code === "AUTH_FORBIDDEN")
      ) {
        try {
          await session.clear();
          return;
        } catch {
          // Do not expose secure storage details.
        }
      }
      setLogoutState("error");
    } finally {
      logoutInFlight.current = false;
    }
  }

  if (activeSession === null) return null;
  return (
    <section className="settings-page" aria-labelledby="settings-title">
      <h1 id="settings-title">{t("настройки")}</h1>
      <div className="settings-options">
        <Link className="settings-option" to="/settings/subscription">
          <NavigationIcon name="subscription" />
          <span>
            <strong>{t("подписка")}</strong>
            <small>{t("управление подпиской и платежами")}</small>
          </span>
          <span aria-hidden="true">→</span>
        </Link>
        <Link className="settings-option" to="/settings/devices">
          <NavigationIcon name="devices" />
          <span>
            <strong>{t("устройства")}</strong>
            <small>{t("Управление доступом к аккаунту")}</small>
          </span>
          <span aria-hidden="true">→</span>
        </Link>
        <button
          className="settings-option settings-option--logout"
          type="button"
          disabled={logoutState === "submitting"}
          onClick={() => void logout()}
        >
          <NavigationIcon name="logout" />
          <span>
            <strong>
              {t(logoutState === "submitting" ? "выходим…" : "выйти")}
            </strong>
            <small>{t("Завершить сессию на этом устройстве")}</small>
          </span>
        </button>
      </div>
      {logoutState === "error" ? (
        <p className="logout-error" role="alert">
          {t("Не удалось завершить сессию. Проверьте сеть и попробуйте снова.")}
        </p>
      ) : null}
    </section>
  );
}
