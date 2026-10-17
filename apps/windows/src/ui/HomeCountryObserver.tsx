import { useEffect, useSyncExternalStore } from "react";
import { rememberHomeCountry } from "../billing/preferences";
import { useApplication } from "../state/application";

export function HomeCountryObserver() {
  const { publicLocation, vpnConnection } = useApplication();
  const state = useSyncExternalStore(vpnConnection.subscribe, vpnConnection.current, vpnConnection.current);
  useEffect(() => {
    if (!publicLocation || state.phase !== "DISCONNECTED" || state.backend !== "NONE" || state.tunnel !== "DOWN") return;
    let controller: AbortController | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let disposed = false;
    const refresh = async () => {
      controller?.abort();
      clearTimeout(timer);
      const current = new AbortController();
      controller = current;
      try {
        const data = await publicLocation.current(current.signal);
        if (!disposed && !current.signal.aborted && vpnConnection.current() === state) rememberHomeCountry(data.countryCode);
      } catch { /* Keep the last known country. Never disconnect VPN for a price. */ }
      if (!disposed && controller === current) timer = setTimeout(() => void refresh(), 60_000);
    };
    void refresh();
    const onNetwork = () => void refresh();
    window.addEventListener("focus", onNetwork);
    window.addEventListener("online", onNetwork);
    return () => {
      disposed = true;
      controller?.abort();
      clearTimeout(timer);
      window.removeEventListener("focus", onNetwork);
      window.removeEventListener("online", onNetwork);
    };
  }, [publicLocation, state, vpnConnection]);
  return null;
}
