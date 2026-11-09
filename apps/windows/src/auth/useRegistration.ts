import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApplication } from "../state/application";

export function useRegistration() {
  const { api, session, vpnConnection } = useApplication();
  const navigate = useNavigate();
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  async function register(returnTo = "/") {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(false);
    try {
      if (session.current()) {
        const token = await session.bearer(api);
        await vpnConnection.disconnect(token);
        await api.logout(token);
        await session.clear();
      }
      navigate("/login", { replace: true, state: { returnTo } });
    } catch {
      setError(true);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  return { register, busy, error };
}
