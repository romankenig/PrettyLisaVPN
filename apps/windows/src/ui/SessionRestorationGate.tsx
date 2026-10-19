import { t, useLanguage } from "../i18n";
import {
  useEffect,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { Navigate, useLocation } from "react-router-dom";
import type {
  RestorationResult,
  SessionRestoration,
} from "../auth/restoration";
import type { AuthenticationSession } from "../auth/session";

export function SessionRestorationGate({
  restoration,
  session,
  children,
}: {
  readonly restoration: SessionRestoration;
  readonly session: AuthenticationSession;
  readonly children: ReactNode;
}) {
  useLanguage();
  const location = useLocation();
  const activeSession = useSyncExternalStore(
    session.subscribe,
    session.current,
    session.current,
  );
  const [result, setResult] = useState<RestorationResult | "checking">(
    "checking",
  );

  useEffect(() => {
    let active = true;
    void restoration.restore().then((next) => {
      if (active) setResult(next);
    });
    return () => {
      active = false;
    };
  }, [restoration]);

  if (result === "checking")
    return <StartupStatus message={t("восстанавливаем сессию…")} />;
  if (result === "temporarily-unavailable") {
    return (
      <StartupFailure
        message={t(
          "Backend временно недоступен. Сессия сохранена на этом устройстве.",
        )}
        onRetry={() => void retry(restoration, setResult)}
      />
    );
  }
  if (result === "storage-unavailable") {
    return (
      <StartupFailure
        message={t("Не удалось открыть защищённое хранилище Windows.")}
        onRetry={() => void retry(restoration, setResult)}
      />
    );
  }

  const authenticationRoute =
    location.pathname === "/login" || location.pathname === "/auth/verify-otp";
  if (activeSession === null && !authenticationRoute) {
    return <Navigate to="/login" replace />;
  }
  if (activeSession !== null && authenticationRoute) {
    return <Navigate to="/" replace />;
  }
  return children;
}

async function retry(
  restoration: SessionRestoration,
  setResult: (result: RestorationResult | "checking") => void,
) {
  setResult("checking");
  setResult(await restoration.retry());
}

function StartupStatus({ message }: { readonly message: string }) {
  useLanguage();
  return (
    <main className="startup-status" aria-live="polite">
      <p>{t(message)}</p>
    </main>
  );
}

function StartupFailure({
  message,
  onRetry,
}: {
  readonly message: string;
  readonly onRetry: () => void;
}) {
  useLanguage();
  return (
    <main className="startup-status" role="alert">
      <p>{t(message)}</p>
      <button type="button" onClick={onRetry}>
        {t("повторить")}
      </button>
    </main>
  );
}
