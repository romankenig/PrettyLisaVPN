import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Link } from "react-router-dom";
import { ApiError, type MeResponse } from "../api/client";
import { useApplication } from "../state/application";
import {
  DEFAULT_VPN_LOCATION_SELECTION,
  type VpnLocationSelection,
} from "../vpn/selection";
import { ConnectionLocationSelector } from "./ConnectionLocationSelector";

type ProfileState =
  | { phase: "loading" }
  | { phase: "ready" }
  | { phase: "error"; message: string };

export function Home() {
  const { api, session } = useApplication();
  const activeSession = useSyncExternalStore(
    session.subscribe,
    session.current,
    session.current,
  );
  const [profileState, setProfileState] = useState<ProfileState>(() =>
    activeSession?.profile ? { phase: "ready" } : { phase: "loading" },
  );
  const [profileAttempt, setProfileAttempt] = useState(0);
  const [logoutState, setLogoutState] = useState<
    "idle" | "submitting" | "error"
  >("idle");
  const logoutInFlight = useRef(false);
  const [locationSelection, setLocationSelection] =
    useState<VpnLocationSelection>(DEFAULT_VPN_LOCATION_SELECTION);

  useEffect(() => {
    if (activeSession === null || activeSession.profile !== null) return;
    const controller = new AbortController();
    setProfileState({ phase: "loading" });
    void api
      .me(activeSession.accessToken, controller.signal)
      .then((profile) => {
        session.updateProfile(activeSession.accessToken, profile);
        setProfileState({ phase: "ready" });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (isInvalidSession(error)) {
          void session.clear().catch(() => {
            setProfileState({
              phase: "error",
              message: "Не удалось очистить защищённую сессию.",
            });
          });
          return;
        }
        setProfileState({ phase: "error", message: profileError(error) });
      });
    return () => controller.abort();
  }, [activeSession, api, profileAttempt, session]);

  if (activeSession === null) return null;
  const profile = activeSession.profile;

  async function logout() {
    if (logoutInFlight.current || activeSession === null) return;
    logoutInFlight.current = true;
    setLogoutState("submitting");
    try {
      await api.logout(activeSession.accessToken);
      await session.clear();
    } catch (error) {
      if (isInvalidSession(error)) {
        try {
          await session.clear();
          return;
        } catch {
          // The generic state below does not expose native storage details.
        }
      }
      setLogoutState("error");
    } finally {
      logoutInFlight.current = false;
    }
  }

  return (
    <section className="account-home" aria-labelledby="home-title">
      <p className="eyebrow">аккаунт</p>
      <h1 id="home-title">PrettyLisaVPN</h1>

      {profileState.phase === "loading" ? (
        <p role="status">загружаем данные аккаунта…</p>
      ) : null}
      {profileState.phase === "error" ? (
        <div className="account-error" role="alert">
          <p>{profileState.message}</p>
          <button
            type="button"
            onClick={() => setProfileAttempt((value) => value + 1)}
          >
            повторить
          </button>
        </div>
      ) : null}
      {profile ? <AccountSummary profile={profile} /> : null}

      <ConnectionLocationSelector
        selection={locationSelection}
        onSelectionChange={setLocationSelection}
      />

      <div className="connection-card">
        <div>
          <p className="connection-card__label">VPN</p>
          <h2>Not connected</h2>
          <p>
            VPN-подключение появится на Stage 3 после реализации WireGuard
            control plane.
          </p>
        </div>
        <button
          type="button"
          disabled
          aria-describedby="connection-unavailable"
        >
          CONNECT
        </button>
        <p id="connection-unavailable" className="field-help">
          Сейчас подключение недоступно.
        </p>
      </div>

      <div className="home-actions">
        <Link className="secondary-link" to="/devices">
          устройства
        </Link>
        <button
          className="logout-button"
          type="button"
          disabled={logoutState === "submitting"}
          onClick={() => void logout()}
        >
          {logoutState === "submitting" ? "выходим…" : "выйти"}
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

function AccountSummary({ profile }: { readonly profile: MeResponse }) {
  return (
    <div className="account-summary">
      <div>
        <span>email</span>
        <strong>{profile.email}</strong>
      </div>
      <div>
        <span>план</span>
        <strong>{profile.plan}</strong>
      </div>
      <div>
        <span>активные устройства</span>
        <strong>{profile.active_device_count}</strong>
      </div>
      <div>
        <span>статус</span>
        <strong className="account-status">активен</strong>
      </div>
    </div>
  );
}

function isInvalidSession(error: unknown) {
  return (
    error instanceof ApiError &&
    (error.code === "AUTH_INVALID" || error.code === "AUTH_FORBIDDEN")
  );
}

function profileError(error: unknown) {
  if (
    error instanceof ApiError &&
    (error.code === "NETWORK_ERROR" || error.code === "TIMEOUT")
  ) {
    return "Не удалось подключиться. Проверьте сеть и попробуйте снова.";
  }
  return "Не удалось загрузить данные аккаунта. Попробуйте позже.";
}
