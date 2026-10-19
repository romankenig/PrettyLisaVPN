import { t, useLanguage } from "../i18n";
import { useEffect, useState } from "react";
import type { ConnectionDetails } from "../vpn/connectionDetails";
import { useApplication } from "../state/application";

export function ConnectionInfo({ sessionId }: { readonly sessionId: string }) {
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
    <div className="connection-info" aria-label={t("способ подключения")}>
      <p>
        {t(info.protocol)} · {t(info.transport)} · {t(info.server)}
      </p>
      <p>
        {t(info.encryption)}
        {t(info.mtu ? ` · mtu ${info.mtu}` : "")}
      </p>
      <details>
        <summary>{t("параметры подключения")}</summary>
        <dl>
          <div>
            <dt>{t("маскировка")}</dt>
            <dd>{t(info.obfuscation)}</dd>
          </div>
          {info.dns ? (
            <div>
              <dt>dns</dt>
              <dd>{t(info.dns.join(", "))}</dd>
            </div>
          ) : null}
          {info.clientAddress ? (
            <div>
              <dt>{t("адрес туннеля")}</dt>
              <dd>{t(info.clientAddress)}</dd>
            </div>
          ) : null}
          {info.allowedIps ? (
            <div>
              <dt>{t("маршруты")}</dt>
              <dd>{t(info.allowedIps.join(", "))}</dd>
            </div>
          ) : null}
          {info.keepalive !== undefined ? (
            <div>
              <dt>keepalive</dt>
              <dd>{t(info.keepalive)} s</dd>
            </div>
          ) : null}
          {info.maxDatagramSize !== undefined ? (
            <div>
              <dt>{t("размер пакета")}</dt>
              <dd>{t(info.maxDatagramSize)}</dd>
            </div>
          ) : null}
          {info.serverPublicKey ? (
            <div>
              <dt>{t("публичный ключ сервера")}</dt>
              <dd>{t(info.serverPublicKey)}</dd>
            </div>
          ) : null}
        </dl>
        <p>{t("для ручной настройки также нужен профиль с ключами")}</p>
      </details>
    </div>
  );
}
