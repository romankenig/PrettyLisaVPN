import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { ApiError, type DeviceResponse } from "../api/client";
import { useApplication } from "../state/application";

type ListState =
  | { readonly phase: "loading" }
  | { readonly phase: "ready"; readonly devices: DeviceResponse[] }
  | { readonly phase: "error"; readonly message: string };

export function Devices() {
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
      <p className="eyebrow">аккаунт</p>
      <h1 id="devices-title">устройства</h1>
      <p className="devices-limit">
        В аккаунте может быть не более 5 активных устройств. Отзовите доступ
        ненужного устройства, чтобы освободить место для нового.
      </p>

      {listState.phase === "loading" ? (
        <p role="status">загружаем устройства…</p>
      ) : null}
      {listState.phase === "error" ? (
        <div className="account-error" role="alert">
          <p>{listState.message}</p>
          <button
            type="button"
            onClick={() => setListAttempt((value) => value + 1)}
          >
            повторить
          </button>
        </div>
      ) : null}
      {listState.phase === "ready" ? (
        listState.devices.length === 0 ? (
          <p className="devices-empty">Устройств пока нет.</p>
        ) : (
          <ul className="device-list">
            {listState.devices.map((device) => (
              <li className="device-card" key={device.id}>
                <div className="device-card__heading">
                  <div>
                    <h2>{device.device_name}</h2>
                    <p>{platformLabel(device.platform)}</p>
                  </div>
                  {device.is_current ? (
                    <span className="current-device">текущее устройство</span>
                  ) : null}
                </div>
                <div className="device-card__footer">
                  <span
                    className={`device-status device-status--${device.status.toLowerCase()}`}
                  >
                    {device.status === "ACTIVE" ? "активно" : "отозвано"}
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
                      отозвать доступ
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
          <h2 id="revoke-confirmation-title">Отозвать доступ?</h2>
          <p id="revoke-confirmation-description">
            Устройство «{confirmation.device_name}» выйдет из аккаунта, а все
            его активные сессии будут завершены.
          </p>
          <div className="confirmation-actions">
            <button
              className="revoke-button"
              type="button"
              disabled={revokingId !== null}
              onClick={() => void revokeDevice()}
            >
              {revokingId ? "отзываем…" : "да, отозвать"}
            </button>
            <button
              className="text-button"
              type="button"
              disabled={revokingId !== null}
              onClick={() => setConfirmation(null)}
            >
              отмена
            </button>
          </div>
        </div>
      ) : null}
      {notice ? (
        <p className="device-notice" role="status">
          {notice}
        </p>
      ) : null}
      {actionError ? (
        <p className="logout-error" role="alert">
          {actionError}
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

function platformLabel(platform: DeviceResponse["platform"]) {
  const labels: Record<DeviceResponse["platform"], string> = {
    WINDOWS: "Windows",
    MACOS: "macOS",
    LINUX: "Linux",
    ANDROID: "Android",
    IOS: "iOS",
    ANDROID_TV: "Android TV",
    CHROME_EXTENSION: "Chrome Extension",
  };
  return labels[platform];
}
