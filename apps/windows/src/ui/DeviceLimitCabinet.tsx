import { useEffect, useState, useSyncExternalStore } from "react";
import { Link, useLocation } from "react-router-dom";
import { ApiError } from "../api/client";
import { t } from "../i18n";
import { useApplication } from "../state/application";
import { Devices } from "./Devices";

/** Separate cabinet keeps privileged screens and their background effects unmounted. */
export function DeviceLimitCabinet() {
  const { api, session } = useApplication();
  const active = useSyncExternalStore(session.subscribe, session.current);
  const { pathname } = useLocation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const token = active?.accessToken;
  useEffect(() => {
    if (!token) return;
    const abort = new AbortController();
    void api
      .me(token, abort.signal)
      .then((profile) => {
        if (!abort.signal.aborted) session.updateProfile(token, profile);
      })
      .catch(() => {
        if (!abort.signal.aborted) setError(true);
      });
    return () => abort.abort();
  }, [api, session, token]);

  async function logout(localOnly: boolean) {
    if (busy) return;
    setBusy(true);
    setError(false);
    try {
      if (!localOnly) {
        try {
          await api.logout(await session.bearer(api));
        } catch (failure) {
          if (!(failure instanceof ApiError && failure.code === "AUTH_INVALID"))
            throw failure;
        }
      }
      await session.clear();
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="device-limit-cabinet">
      <div className="account-error device-limit-banner" role="alert">
        <strong>{t("достигнут лимит устройств")}</strong>
        <p>
          {t(
            "удалите одно из устройств, чтобы пользоваться приложением на этом устройстве.",
          )}
        </p>
        <Link className="button" to="/settings/devices">
          {t("управлять устройствами")}
        </Link>
      </div>
      {pathname.endsWith("/devices") ? (
        <Devices />
      ) : (
        <div className="device-limit-overview">
          <div className="account-card">
            <h1>{t(pathname === "/settings" ? "настройки" : "аккаунт")}</h1>
            <strong className="verified-email">
              {active?.profile?.email ?? "…"}
            </strong>
            <p className="plan-name">
              {active?.plan}{" "}
              {active?.plan === "PLATINUM"
                ? "💎"
                : active?.plan === "PREMIUM"
                  ? "⭐"
                  : "🕊️"}
            </p>
            <p>
              <Link to="/settings/devices">
                {t("устройства")} · {active?.profile?.active_device_count ?? 5}{" "}
                / 5 →
              </Link>
            </p>
          </div>
          <fieldset
            disabled
            className="device-limit-features"
            aria-label={t("куда подключаемся")}
          >
            <h2>{t("куда подключаемся")}</h2>
            <button>{t("автопилот")}</button>
            <button>{t("подключиться")}</button>
            <button>{t("подписка")}</button>
            <button>{t("Расширенные настройки")}</button>
          </fieldset>
        </div>
      )}
      <div className="device-limit-actions">
        <button disabled={busy} onClick={() => void logout(false)}>
          {t("выйти")}
        </button>
        <button
          disabled={busy}
          onClick={() => {
            if (window.confirm(t("удалить данные входа с этого устройства")))
              void logout(true);
          }}
        >
          {t("удалить данные входа с этого устройства")}
        </button>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {t("Не удалось подключиться. Проверьте сеть и попробуйте снова.")}
        </p>
      )}
    </section>
  );
}
