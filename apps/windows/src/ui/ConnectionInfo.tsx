import { t, useLanguage } from "../i18n";
import { useEffect, useState } from "react";
import type { ConnectionDetails } from "../vpn/connectionDetails";
import { useApplication } from "../state/application";
import { ActionConfirmation } from "./ActionConfirmation";

export function ConnectionInfo({
  sessionId,
  onReset,
  resetting = false,
}: {
  readonly sessionId: string;
  readonly onReset?: () => void;
  readonly resetting?: boolean;
}) {
  useLanguage();
  const { vpnConnection } = useApplication();
  const [confirmReset, setConfirmReset] = useState(false);
  const [state, setState] = useState<{
    readonly sessionId: string;
    readonly data: ConnectionDetails | null;
  } | null>(null);
  useEffect(() => {
    let disposed = false;
    const timer = globalThis.setTimeout(() => {
      if (!disposed) setState({ sessionId, data: null });
      disposed = true;
    }, 5000);
    void Promise.resolve()
      .then(() => vpnConnection.connectionDetails?.() ?? null)
      .then((data) => {
        if (!disposed) setState({ sessionId, data });
      })
      .catch(() => {
        if (!disposed) setState({ sessionId, data: null });
      })
      .finally(() => globalThis.clearTimeout(timer));
    return () => {
      disposed = true;
      globalThis.clearTimeout(timer);
    };
  }, [sessionId, vpnConnection]);
  if (state?.sessionId !== sessionId)
    return (
      <p className="connection-info" role="status">
        {t("получаем параметры соединения…")}
      </p>
    );
  const info = state.data;
  if (!info)
    return (
      <p className="connection-info">{t("параметры соединения недоступны")}</p>
    );
  return (
    <>
      <p className="connection-info" aria-label={t("способ подключения")}>
        {t(info.protocol)}
        {onReset && (
          <button
            type="button"
            className="connection-reset"
            disabled={resetting}
            title={t("изменить способ подключения")}
            aria-label={t("изменить способ подключения")}
            onClick={() => setConfirmReset(true)}
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
        )}
      </p>
      {confirmReset && onReset && !resetting ? (
        <ActionConfirmation
          title="Изменить способ подключения?"
          description="Забудем запомненный способ и заново проверим доступные варианты. VPN ненадолго отключится. Страна и выбранные сервисы сохранятся."
          confirmLabel="да, переподключиться"
          onCancel={() => setConfirmReset(false)}
          onConfirm={() => {
            setConfirmReset(false);
            onReset();
          }}
        />
      ) : null}
    </>
  );
}
