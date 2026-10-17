import {
  useEffect,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
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
  const [locationSelection, setLocationSelection] =
    useState<VpnLocationSelection>(DEFAULT_VPN_LOCATION_SELECTION);
  const [locationConnectable, setLocationConnectable] = useState(false);
  const connectionState = useSyncExternalStore(
    vpnConnection.subscribe,
    vpnConnection.current,
    vpnConnection.current,
  );
  const [connectionErrorMessage, setConnectionErrorMessage] =
    useState<ReactNode>(null);

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

  async function connect() {
    if (
      !locationConnectable ||
      connectionState.phase === "CONNECTED" ||
      connectionState.phase === "CONNECTING" ||
      connectionState.phase === "TUNNEL_ESTABLISHED" ||
      connectionState.phase === "VERIFYING_INTERNET" ||
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

  async function disconnect() {
    setConnectionErrorMessage(null);
    try {
      await vpnConnection.disconnect(accessToken);
    } catch (error) {
      setConnectionErrorMessage(connectionError(error));
    }
  }

  return (
    <section className="account-home" aria-labelledby="home-title">
      <p className="eyebrow">аккаунт</p>
      <h1 id="home-title" className="product-name">
        PrettyLisaVPN
      </h1>

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

      <div className="home-workspace">
        <ConnectionLocationSelector
          selection={locationSelection}
          onSelectionChange={setLocationSelection}
          onConnectabilityChange={setLocationConnectable}
        />

        <div className="connection-card">
          <div>
            <p className="connection-card__label">VPN</p>
            <h2>{connectionHeading(connectionState)}</h2>
            <p>
              {connectionState.phase === "CONNECTED"
                ? `Локация: ${countryName(connectionState.session.countryCode)}`
                : "Выберите локацию для подключения."}
            </p>
            {profile?.plan === "FREE" &&
            connectionState.phase === "CONNECTED" &&
            connectionState.session.remainingSeconds !== null ? (
              <p role="timer">
                Осталось:{" "}
                {formatRemaining(connectionState.session.remainingSeconds)}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            disabled={
              connectionState.phase === "CONNECTING" ||
              connectionState.phase === "TUNNEL_ESTABLISHED" ||
              connectionState.phase === "VERIFYING_INTERNET" ||
              connectionState.phase === "RECONCILING" ||
              connectionState.phase === "DISCONNECTING" ||
              (!canDisconnect(connectionState) && !locationConnectable)
            }
            aria-describedby="connection-unavailable"
            onClick={() =>
              void (canDisconnect(connectionState) ? disconnect() : connect())
            }
          >
            {connectionState.phase === "DISCONNECTING"
              ? "DISCONNECTING"
              : connectionState.phase === "CONNECTING" ||
                  connectionState.phase === "TUNNEL_ESTABLISHED" ||
                  connectionState.phase === "VERIFYING_INTERNET" ||
                  connectionState.phase === "RECONCILING"
                ? "CONNECTING"
                : canDisconnect(connectionState)
                  ? "DISCONNECT"
                  : "CONNECT"}
          </button>
          <p id="connection-unavailable" className="field-help">
            {!locationConnectable
              ? "Сейчас подключение недоступно."
              : "Готово к подключению."}
          </p>
          {connectionErrorMessage !== null ||
          ["UNAVAILABLE", "FAILED", "DEGRADED"].includes(
            connectionState.phase,
          ) ? (
            <p className="connection-error" role="alert">
              {connectionErrorMessage ??
                connectionUnavailableMessage(connectionState)}
            </p>
          ) : null}
          {connectionState.phase === "DISCONNECTED" &&
          connectionState.backend === "UNAVAILABLE" ? (
            <p className="connection-error" role="status">
              VPN на компьютере остановлен. Сервер завершит сессию после
              восстановления связи.
            </p>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function AccountSummary({ profile }: { readonly profile: MeResponse }) {
  return (
    <div className="account-summary">
      <div>
        <span>email</span>
        <strong title={profile.email}>{profile.email}</strong>
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
    if (error.code === "VPN_TRAFFIC_INTERCEPTED") {
      return (
        <>
          Другой VPN или сетевой фильтр не пропускает интернет через{" "}
          <span className="product-name">PrettyLisaVPN</span>. Отключите другой
          VPN и повторите подключение.
        </>
      );
    }
    if (error.code === "LOCAL_TUNNEL_STOP_FAILED") {
      return "Не удалось подтвердить остановку VPN на этом компьютере. Повторите отключение.";
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
  if (state.phase === "FAILED" || state.phase === "DEGRADED")
    return `Доступ в Интернет через VPN не подтверждён (${state.failure_code ?? "UNKNOWN"}).`;
  return state.phase === "UNAVAILABLE" ? unavailableMessage(state.reason) : "";
}

function canDisconnect(state: VpnConnectionState) {
  return (
    state.phase === "CONNECTED" ||
    state.phase === "DEGRADED" ||
    (state.phase === "FAILED" &&
      (state.tunnel !== "DOWN" || state.backend !== "NONE")) ||
    (state.phase === "UNAVAILABLE" && state.tunnel !== "DOWN") ||
    (state.phase === "UNAVAILABLE" && state.backend === "ACTIVE")
  );
}

function connectionHeading(state: VpnConnectionState) {
  if (state.phase === "CONNECTED") return "Connected";
  if (state.phase === "TUNNEL_ESTABLISHED") return "TUNNEL ESTABLISHED";
  if (state.phase === "VERIFYING_INTERNET") return "VERIFYING INTERNET";
  if (state.phase === "DEGRADED") return "DEGRADED";
  if (state.phase === "FAILED") return "FAILED";
  if (state.phase === "CONNECTING" || state.phase === "RECONCILING")
    return "CONNECTING";
  if (state.phase === "DISCONNECTING" && state.tunnel === "UP")
    return "DISCONNECTING";
  if (state.tunnel === "DOWN") return "Not connected";
  return "Connection status unavailable";
}

function formatRemaining(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}
