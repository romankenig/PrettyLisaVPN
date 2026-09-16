import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Link } from "react-router-dom";
import { ApiError, type MeResponse } from "../api/client";
import { useApplication } from "../state/application";
import {
  DEFAULT_VPN_LOCATION_SELECTION,
  type VpnLocationSelection,
} from "../vpn/selection";
import { ConnectionLocationSelector } from "./ConnectionLocationSelector";
import { countryName } from "./ConnectionLocationSelector";
import { VpnConnectionError, type VpnConnectionState } from "../vpn/connection";

type ProfileState =
  | { phase: "loading" }
  | { phase: "ready" }
  | { phase: "error"; message: string };

export function Home() {
  const { api, session, vpnConnection } = useApplication();
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
  const [locationConnectable, setLocationConnectable] = useState(false);
  const connectionState = useSyncExternalStore(
    vpnConnection.subscribe,
    vpnConnection.current,
    vpnConnection.current,
  );
  const [connectionErrorMessage, setConnectionErrorMessage] = useState<
    string | null
  >(null);

  useEffect(() => {
    if (activeSession === null) return;
    void vpnConnection.reconcile(activeSession.accessToken);
  }, [activeSession, vpnConnection]);

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
  const accessToken = activeSession.accessToken;

  async function logout() {
    if (logoutInFlight.current || activeSession === null) return;
    logoutInFlight.current = true;
    setLogoutState("submitting");
    try {
      await api.logout(accessToken);
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

  async function connect() {
    if (
      !locationConnectable ||
      connectionState.phase === "CONNECTED" ||
      connectionState.phase === "CONNECTING" ||
      connectionState.phase === "RECONCILING"
    ) {
      return;
    }
    setConnectionErrorMessage(null);
    try {
      await vpnConnection.connect(accessToken, locationSelection);
    } catch (error) {
      setConnectionErrorMessage(connectionError(error));
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
        onConnectabilityChange={setLocationConnectable}
      />

      <div className="connection-card">
        <div>
          <p className="connection-card__label">VPN</p>
          <h2>
            {connectionState.phase === "CONNECTED"
              ? "Connected"
              : connectionState.phase === "CONNECTING" ||
                  connectionState.phase === "RECONCILING"
                ? "CONNECTING"
                : "Not connected"}
          </h2>
          <p>
            {connectionState.phase === "CONNECTED"
              ? `Локация: ${countryName(connectionState.session.countryCode)}`
              : "Выберите локацию и установите защищённое соединение."}
          </p>
        </div>
        <button
          type="button"
          disabled={
            !locationConnectable ||
            connectionState.phase === "CONNECTING" ||
            connectionState.phase === "RECONCILING" ||
            connectionState.phase === "CONNECTED"
          }
          aria-describedby="connection-unavailable"
          onClick={() => void connect()}
        >
          {connectionState.phase === "CONNECTING" ||
          connectionState.phase === "RECONCILING"
            ? "CONNECTING"
            : connectionState.phase === "CONNECTED"
              ? "CONNECTED"
              : "CONNECT"}
        </button>
        <p id="connection-unavailable" className="field-help">
          {!locationConnectable
            ? "Сейчас подключение недоступно."
            : "Подключение использует выбранный режим без выбора конкретного сервера."}
        </p>
        {connectionErrorMessage !== null ||
        connectionState.phase === "UNAVAILABLE" ? (
          <p className="connection-error" role="alert">
            {connectionErrorMessage ??
              connectionUnavailableMessage(connectionState)}
          </p>
        ) : null}
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

function connectionError(error: unknown) {
  if (error instanceof VpnConnectionError) {
    if (error.code === "COUNTRY_UNAVAILABLE") {
      return "Выбранная страна сейчас недоступна. Обновите список локаций.";
    }
    if (error.code === "VPN_UNAVAILABLE") {
      return "Сейчас нет доступного VPN-соединения. Попробуйте позже.";
    }
    if (error.code === "LOCAL_TUNNEL_FAILED") {
      return "Не удалось запустить VPN на этом компьютере. Подключение отменено.";
    }
  }
  return "Не удалось установить VPN-соединение. Попробуйте снова.";
}

function unavailableMessage(
  reason: "BACKEND_UNAVAILABLE" | "TUNNEL_UNAVAILABLE" | "CONNECTION_FAILED",
) {
  if (reason === "BACKEND_UNAVAILABLE")
    return "VPN-туннель и серверная сессия не могут быть сверены: backend недоступен.";
  if (reason === "TUNNEL_UNAVAILABLE")
    return "Локальный VPN-туннель недоступен. Состояние Connected снято.";
  return "Не удалось установить VPN-соединение. Попробуйте снова.";
}

function connectionUnavailableMessage(state: VpnConnectionState) {
  return state.phase === "UNAVAILABLE" ? unavailableMessage(state.reason) : "";
}
