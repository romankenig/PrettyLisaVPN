import { useEffect, useState } from "react";
import { useApplication } from "../state/application";

export function useVersions() {
  const { api, desktop } = useApplication();
  const [frontend, setFrontend] = useState("…");
  const [backend, setBackend] = useState("…");
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setFrontend("…");
    setBackend("…");
    void Promise.resolve()
      .then(() => desktop.getVersion())
      .then((value) => {
        if (active) setFrontend(value.trim() || "недоступна");
      })
      .catch(() => {
        if (active) setFrontend("недоступна");
      });
    // Existing /version contract; failure must never block navigation or login.
    void Promise.resolve()
      .then(() => api.getVersion(controller.signal))
      .then((value) => {
        if (active)
          setBackend(value.application_version.trim() || "недоступна");
      })
      .catch(() => {
        if (active) setBackend("недоступна");
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [api, desktop]);
  return { frontend, backend };
}
