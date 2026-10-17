import { useRef, useState, useSyncExternalStore } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { ApiError } from "../api/client";
import { useApplication } from "../state/application";
import { Devices } from "./Devices";
import { NavigationIcon } from "./NavigationIcon";

export function Settings() {
  return (
    <Routes>
      <Route index element={<SettingsOverview />} />
      <Route
        path="subscription"
        element={
          <section
            className="settings-page"
            aria-labelledby="subscription-title"
          >
            <Link className="settings-back" to="/settings">
              ← настройки
            </Link>
            <h1 id="subscription-title">подписка</h1>
          </section>
        }
      />
      <Route
        path="devices"
        element={
          <div className="settings-devices">
            <Link className="settings-back" to="/settings">
              ← настройки
            </Link>
            <Devices />
          </div>
        }
      />
    </Routes>
  );
}

function SettingsOverview() {
  const { api, session } = useApplication();
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
      await api.logout(activeSession.accessToken);
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
      <p className="eyebrow">приложение</p>
      <h1 id="settings-title">настройки</h1>
      <div className="settings-options">
        <Link className="settings-option" to="/settings/devices">
          <NavigationIcon name="devices" />
          <span>
            <strong>устройства</strong>
            <small>Управление доступом к аккаунту</small>
          </span>
          <span aria-hidden="true">→</span>
        </Link>
        <Link className="settings-option" to="/settings/subscription">
          <NavigationIcon name="subscription" />
          <span>
            <strong>подписка</strong>
            <small>управление подпиской</small>
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
              {logoutState === "submitting" ? "выходим…" : "выйти"}
            </strong>
            <small>Завершить сессию на этом компьютере</small>
          </span>
        </button>
      </div>
      {logoutState === "error" ? (
        <p className="logout-error" role="alert">
          Не удалось завершить сессию. Проверьте сеть и попробуйте снова.
        </p>
      ) : null}
    </section>
  );
}
