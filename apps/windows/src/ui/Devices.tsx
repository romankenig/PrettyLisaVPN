import { t, useLanguage, getLanguage } from "../i18n";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { ApiError, type DeviceResponse } from "../api/client";
import { useApplication } from "../state/application";

type ListState =
  | { readonly phase: "loading" }
  | { readonly phase: "ready"; readonly devices: DeviceResponse[] }
  | { readonly phase: "error"; readonly message: string };

export function Devices() {
  useLanguage();
  const { api, session } = useApplication();
  const activeSession = useSyncExternalStore(
    session.subscribe,
    session.current,
    session.current,
  );
  const [listState, setListState] = useState<ListState>({ phase: "loading" });
  const [listAttempt, setListAttempt] = useState(0);
  const [confirmation, setConfirmation] = useState<DeviceResponse | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const revokeInFlight = useRef(false);

  useEffect(() => {
    if (activeSession === null) return;
    const controller = new AbortController();
    setListState({ phase: "loading" });
    void api
      .listDevices(activeSession.accessToken, controller.signal)
      .then((devices) => setListState({ phase: "ready", devices }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (isUnauthorized(error)) {
          void clearUnauthorizedSession(session.clear, setListState);
          return;
        }
        setListState({ phase: "error", message: listError(error) });
      });
    return () => controller.abort();
  }, [activeSession, api, listAttempt, session]);

  if (activeSession === null) return null;
  const accessToken = activeSession.accessToken;

  async function revokeDevice() {
    if (
      confirmation === null ||
      confirmation.is_current ||
      confirmation.status !== "ACTIVE" ||
      revokeInFlight.current
    ) {
      return;
    }
    revokeInFlight.current = true;
    setRevokingId(confirmation.id);
    setActionError(null);
    setNotice(null);
    try {
      await api.revokeDevice(accessToken, confirmation.id);
      setConfirmation(null);
      setNotice(`Доступ устройства «${confirmation.device_name}» отозван.`);
      setListAttempt((value) => value + 1);
    } catch (error) {
      if (isUnauthorized(error)) {
        await clearUnauthorizedSession(session.clear, setListState);
        return;
      }
      setActionError(revokeError(error));
    } finally {
      revokeInFlight.current = false;
      setRevokingId(null);
    }
  }

  return (
    <section className="devices-page" aria-labelledby="devices-title">
      <h1 id="devices-title">{t("устройства")}</h1>
      <p className="devices-limit">
        {t("в аккаунте может быть не более 5 активных устройств.")}
        <br />
        {t(
          "отзовите доступ ненужного устройства, чтобы освободить место для нового.",
        )}
      </p>

      {listState.phase === "loading" ? (
        <p role="status">{t("загружаем устройства…")}</p>
      ) : null}
      {listState.phase === "error" ? (
        <div className="account-error" role="alert">
          <p>{t(listState.message)}</p>
          <button
            type="button"
            onClick={() => setListAttempt((value) => value + 1)}
          >
            {t("повторить")}
          </button>
        </div>
      ) : null}
      {listState.phase === "ready" ? (
        listState.devices.length === 0 ? (
          <p className="devices-empty">{t("Устройств пока нет.")}</p>
        ) : (
          <ul className="device-list">
            {listState.devices.map((device) => (
              <li className="device-card" key={device.id}>
                <div className="device-card__heading">
                  <div>
                    <h2>{device.device_name}</h2>
                    <p className="device-identity" title={device.id}>
                      id: {t(deviceIdentifier(device, listState.devices))}
                    </p>
                    <p className="device-dates">
                      {t("добавлено: ")}
                      <DeviceTime value={device.created_at} />
                      <br />
                      {t("последний вход:")}
                      {t(" ")}
                      <DeviceTime value={device.last_login_at} />
                    </p>
                  </div>
                  {device.is_current ? (
                    <span className="current-device">
                      {t("текущее устройство")}
                    </span>
                  ) : null}
                </div>
                <div className="device-card__footer">
                  <span
                    className={`device-status device-status--${device.status.toLowerCase()}`}
                  >
                    {t(device.status === "ACTIVE" ? "активно" : "отозвано")}
                  </span>
                  {!device.is_current && device.status === "ACTIVE" ? (
                    <button
                      className="revoke-button"
                      type="button"
                      disabled={revokingId !== null}
                      onClick={() => {
                        setConfirmation(device);
                        setActionError(null);
                      }}
                    >
                      {t("отозвать доступ")}
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )
      ) : null}

      {confirmation ? (
        <div
          className="revoke-confirmation"
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="revoke-confirmation-title"
          aria-describedby="revoke-confirmation-description"
        >
          <h2 id="revoke-confirmation-title">{t("Отозвать доступ?")}</h2>
          <p id="revoke-confirmation-description">
            {t("Устройство «")}
            {confirmation.device_name}
            {t(
              "» выйдет из аккаунта, а все его активные сессии будут завершены.",
            )}
          </p>
          <p className="device-identity">id: {t(confirmation.id)}</p>
          <div className="confirmation-actions">
            <button
              className="revoke-button"
              type="button"
              disabled={revokingId !== null}
              onClick={() => void revokeDevice()}
            >
              {t(revokingId ? "отзываем…" : "да, отозвать")}
            </button>
            <button
              className="text-button"
              type="button"
              disabled={revokingId !== null}
              onClick={() => setConfirmation(null)}
            >
              {t("отмена")}
            </button>
          </div>
        </div>
      ) : null}
      {notice ? (
        <p className="device-notice" role="status">
          {t(notice)}
        </p>
      ) : null}
      {actionError ? (
        <p className="logout-error" role="alert">
          {t(actionError)}
        </p>
      ) : null}
    </section>
  );
}

async function clearUnauthorizedSession(
  clear: () => Promise<void>,
  setListState: (state: ListState) => void,
) {
  try {
    await clear();
  } catch {
    setListState({
      phase: "error",
      message: "Не удалось очистить защищённую сессию.",
    });
  }
}

function isUnauthorized(error: unknown) {
  return (
    error instanceof ApiError &&
    (error.code === "AUTH_INVALID" || error.code === "AUTH_FORBIDDEN")
  );
}

function listError(error: unknown) {
  if (
    error instanceof ApiError &&
    (error.code === "NETWORK_ERROR" || error.code === "TIMEOUT")
  ) {
    return "Не удалось подключиться. Проверьте сеть и попробуйте снова.";
  }
  return "Не удалось загрузить устройства. Попробуйте позже.";
}

function revokeError(error: unknown) {
  if (error instanceof ApiError && error.code === "DEVICE_NOT_FOUND") {
    return "Устройство уже удалено или недоступно. Обновите список.";
  }
  if (
    error instanceof ApiError &&
    (error.code === "NETWORK_ERROR" || error.code === "TIMEOUT")
  ) {
    return "Не удалось отозвать доступ. Проверьте сеть и попробуйте снова.";
  }
  return "Не удалось отозвать доступ устройства. Попробуйте позже.";
}

function deviceIdentifier(device: DeviceResponse, devices: DeviceResponse[]) {
  const suffix = device.id.slice(-12);
  return devices.some(
    (other) => other.id !== device.id && other.id.endsWith(suffix),
  )
    ? device.id
    : suffix;
}

function DeviceTime({ value }: { readonly value?: string | null }) {
  useLanguage();
  if (!value || !Number.isFinite(Date.parse(value)))
    return <>{t("нет данных")}</>;
  return (
    <time dateTime={value} title={t("по времени этого устройства")}>
      {t(
        new Intl.DateTimeFormat(getLanguage(), {
          day: "2-digit",
          month: "2-digit",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        }).format(new Date(value)),
      )}
    </time>
  );
}
