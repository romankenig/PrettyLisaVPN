import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiClient, BackendVersion } from "../api/client";

export type BackendStatus =
  | { phase: "checking" }
  | { phase: "offline" }
  | { phase: "online"; version?: BackendVersion };

export function useBackendStatus(api: ApiClient, healthIntervalMs: number) {
  const [status, setStatus] = useState<BackendStatus>({ phase: "checking" });
  const activeRequest = useRef<AbortController | null>(null);
  const requestId = useRef(0);

  const check = useCallback(
    async (showChecking = true) => {
      activeRequest.current?.abort();
      const controller = new AbortController();
      activeRequest.current = controller;
      const currentRequest = ++requestId.current;
      if (showChecking) setStatus({ phase: "checking" });

      try {
        await api.getHealth(controller.signal);
      } catch {
        if (
          !controller.signal.aborted &&
          currentRequest === requestId.current
        ) {
          setStatus({ phase: "offline" });
        }
        return;
      }

      if (controller.signal.aborted || currentRequest !== requestId.current)
        return;
      setStatus({ phase: "online" });

      try {
        const version = await api.getVersion(controller.signal);
        if (
          !controller.signal.aborted &&
          currentRequest === requestId.current
        ) {
          setStatus({ phase: "online", version });
        }
      } catch {
        // Liveness already succeeded. Version metadata is optional for online state.
      }
    },
    [api],
  );

  useEffect(() => {
    void check();
    const interval = globalThis.setInterval(
      () => void check(false),
      healthIntervalMs,
    );
    return () => {
      globalThis.clearInterval(interval);
      activeRequest.current?.abort();
    };
  }, [check, healthIntervalMs]);

  return { status, retry: () => void check(true) };
}
