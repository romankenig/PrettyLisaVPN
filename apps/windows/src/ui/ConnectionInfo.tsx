import { useEffect, useState } from "react";
import type { ConnectionDetails } from "../vpn/connectionDetails";
import { useApplication } from "../state/application";

export function ConnectionInfo({ sessionId }: { readonly sessionId: string }) {
  const { vpnConnection } = useApplication();
  const [state, setState] = useState<{ readonly sessionId: string; readonly data: ConnectionDetails | null } | null>(null);
  useEffect(() => {
    let disposed = false;
    const timer = globalThis.setTimeout(() => { if (!disposed) setState({ sessionId, data: null }); disposed = true; }, 5000);
    void Promise.resolve().then(() => vpnConnection.connectionDetails?.() ?? null).then((data) => {
      if (!disposed) setState({ sessionId, data });
    }).catch(() => { if (!disposed) setState({ sessionId, data: null }); }).finally(() => globalThis.clearTimeout(timer));
    return () => { disposed = true; globalThis.clearTimeout(timer); };
  }, [sessionId, vpnConnection]);
  if (state?.sessionId !== sessionId) return <p className="connection-info" role="status">получаем параметры соединения…</p>;
  const info = state.data;
  if (!info) return <p className="connection-info">параметры соединения недоступны</p>;
  return (
    <div className="connection-info" aria-label="способ подключения">
      <p>{info.protocol} · {info.transport} · {info.server}</p>
      <p>{info.encryption}{info.mtu ? ` · mtu ${info.mtu}` : ""}</p>
      <details>
        <summary>параметры подключения</summary>
        <dl>
          <div><dt>маскировка</dt><dd>{info.obfuscation}</dd></div>
          {info.dns ? <div><dt>dns</dt><dd>{info.dns.join(", ")}</dd></div> : null}
          {info.clientAddress ? <div><dt>адрес туннеля</dt><dd>{info.clientAddress}</dd></div> : null}
          {info.allowedIps ? <div><dt>маршруты</dt><dd>{info.allowedIps.join(", ")}</dd></div> : null}
          {info.keepalive !== undefined ? <div><dt>keepalive</dt><dd>{info.keepalive} s</dd></div> : null}
          {info.maxDatagramSize !== undefined ? <div><dt>размер пакета</dt><dd>{info.maxDatagramSize}</dd></div> : null}
          {info.serverPublicKey ? <div><dt>публичный ключ сервера</dt><dd>{info.serverPublicKey}</dd></div> : null}
        </dl>
        <p>для ручной настройки также нужен профиль с ключами</p>
      </details>
    </div>
  );
}
