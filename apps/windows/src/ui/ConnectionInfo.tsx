import { t, useLanguage } from "../i18n";
import { useEffect, useState } from "react";
import type { ConnectionDetails } from "../vpn/connectionDetails";
import { useApplication } from "../state/application";

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
    <p className="connection-info" aria-label={t("способ подключения")}>
      {t(info.protocol)}
      {onReset && (
        <button
          type="button"
          className="connection-reset"
          disabled={resetting}
          title={t("забыть успешный способ и подключиться заново")}
          onClick={onReset}
        >
          {t("сброс настроек")}
        </button>
      )}
    </p>
  );
}
