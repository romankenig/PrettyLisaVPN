import { t, useLanguage } from "../i18n";
import { useEffect, useState } from "react";
import type { PublicLocation } from "../location/publicLocation";
import type { VpnConnectionState } from "../vpn/connection";
import { useApplication } from "../state/application";
import { countryName } from "./ConnectionLocationSelector";
import { CountryIcon } from "./CountryIcon";

export const LOCATION_REFRESH_MS = 60_000;
type LocationState =
  | { readonly key: string; readonly phase: "loading" | "error" }
  | {
      readonly key: string;
      readonly phase: "ready";
      readonly data: PublicLocation;
    };

export function CurrentLocation({
  connection,
  vpn = false,
}: {
  readonly connection: VpnConnectionState;
  readonly vpn?: boolean;
}) {
  useLanguage();
  const application = useApplication();
  const publicLocation = vpn
    ? application.vpnLocation
    : application.publicLocation;
  const inactive = vpn && connection.phase !== "CONNECTED";
  const pending = [
    "RECONCILING",
    "CONNECTING",
    "TUNNEL_ESTABLISHED",
    "VERIFYING_INTERNET",
    "DISCONNECTING",
  ].includes(connection.phase);
  const key = `${connection.phase}:${connection.tunnel}:${"session" in connection ? (connection.session?.countryCode ?? "") : ""}`;
  const [state, setState] = useState<LocationState>({ key, phase: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    setState({ key, phase: "loading" });
    if (pending || inactive) return;
    if (!publicLocation) {
      setState({ key, phase: "error" });
      return;
    }
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let request: AbortController | undefined;
    let generation = 0;
    const refresh = async () => {
      globalThis.clearTimeout(timer);
      request?.abort();
      const controller = new AbortController();
      request = controller;
      const current = ++generation;
      setState({ key, phase: "loading" });
      try {
        const data = await publicLocation.current(controller.signal);
        if (!disposed && !controller.signal.aborted && current === generation)
          setState({ key, phase: "ready", data });
      } catch {
        if (!disposed && !controller.signal.aborted && current === generation)
          setState({ key, phase: "error" });
      } finally {
        if (!disposed && current === generation)
          timer = globalThis.setTimeout(
            () => void refresh(),
            LOCATION_REFRESH_MS,
          );
      }
    };
    const onNetwork = () => void refresh();
    void refresh();
    window.addEventListener("online", onNetwork);
    window.addEventListener("focus", onNetwork);
    return () => {
      disposed = true;
      request?.abort();
      globalThis.clearTimeout(timer);
      window.removeEventListener("online", onNetwork);
      window.removeEventListener("focus", onNetwork);
    };
  }, [attempt, key, pending, inactive, publicLocation]);
  const visible =
    state.key === key && !pending ? state : { phase: "loading" as const };
  return (
    <div
      className="current-location"
      aria-label={t(vpn ? "локация VPN" : "текущая локация")}
      aria-live="polite"
    >
      <span className="current-location__label">
        {t(vpn ? "локация VPN:" : "текущая локация:")}
      </span>
      {inactive ? (
        <span className="current-location__notice">
          {t("VPN не подключён")}
        </span>
      ) : visible.phase === "ready" ? (
        <div className="current-location__details">
          <CountryIcon code={visible.data.countryCode} />
          <div>
            <span>
              {t(visible.data.city ?? "город неизвестен")},{t(" ")}
              {t(
                visible.data.countryCode
                  ? countryName(visible.data.countryCode)
                  : "страна неизвестна",
              )}
            </span>
            <span className="current-location__ip">{t(visible.data.ip)}</span>
          </div>
        </div>
      ) : (
        <span className="current-location__notice">
          {t(
            visible.phase === "error" ? "не удалось определить" : "определяем…",
          )}
        </span>
      )}
      {!inactive && visible.phase === "error" ? (
        <button
          type="button"
          className="location-refresh"
          aria-label={t(
            vpn ? "обновить локацию VPN" : "обновить текущую локацию",
          )}
          onClick={() => setAttempt((value) => value + 1)}
        >
          ↻
        </button>
      ) : null}
    </div>
  );
}
