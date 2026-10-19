import { t, useLanguage } from "../i18n";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { ApiError, type VerifyOtpResponse } from "../api/client";
import { useApplication } from "../state/application";

interface OtpRouteState {
  readonly email: string;
}

type VerificationState =
  | { phase: "idle" }
  | { phase: "submitting" }
  | { phase: "error"; message: string }
  | { phase: "success" };

type ResendState =
  | { phase: "idle" }
  | { phase: "sending" }
  | { phase: "sent" }
  | { phase: "error"; message: string };

const CODE_PATTERN = /^\d{6}$/;
const RESEND_COOLDOWN_SECONDS = 60;
const WINDOWS_DEVICE_NAME = "Windows device";

export function OtpVerification() {
  useLanguage();
  const location = useLocation();
  const routeState = location.state as OtpRouteState | null;
  if (!routeState?.email) return <Navigate to="/login" replace />;
  return <OtpForm email={routeState.email} />;
}

function OtpForm({ email }: { readonly email: string }) {
  useLanguage();
  const { api, installationId, session } = useApplication();
  const verificationRequest = useRef<AbortController | null>(null);
  const resendRequest = useRef<AbortController | null>(null);
  const verificationInFlight = useRef(false);
  const resendInFlight = useRef(false);
  const [code, setCode] = useState("");
  const [state, setState] = useState<VerificationState>({ phase: "idle" });
  const [resendState, setResendState] = useState<ResendState>({
    phase: "idle",
  });
  const [cooldown, setCooldown] = useState(RESEND_COOLDOWN_SECONDS);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = globalThis.setTimeout(
      () => setCooldown((remaining) => Math.max(0, remaining - 1)),
      1000,
    );
    return () => globalThis.clearTimeout(timer);
  }, [cooldown]);

  useEffect(
    () => () => {
      verificationRequest.current?.abort();
      resendRequest.current?.abort();
    },
    [],
  );

  async function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (verificationInFlight.current) return;
    if (!CODE_PATTERN.test(code)) {
      setState({ phase: "error", message: "Введите шестизначный код." });
      return;
    }

    verificationInFlight.current = true;
    const controller = new AbortController();
    verificationRequest.current = controller;
    setState({ phase: "submitting" });
    try {
      const currentInstallationId = await installationId.getInstallationId();
      const result = await api.verifyOtp(
        {
          email,
          code,
          installation_id: currentInstallationId,
          platform: "WINDOWS",
          device_name: WINDOWS_DEVICE_NAME,
        },
        controller.signal,
      );
      await session.establish(toCredentials(result));
      setCode("");
      setState({ phase: "success" });
    } catch (error) {
      if (controller.signal.aborted) return;
      if (error instanceof ApiError && error.code === "OTP_INVALID")
        setCode("");
      setState({ phase: "error", message: verificationMessage(error) });
    } finally {
      verificationInFlight.current = false;
      if (verificationRequest.current === controller)
        verificationRequest.current = null;
    }
  }

  async function resend() {
    if (cooldown > 0 || resendInFlight.current) return;
    resendInFlight.current = true;
    const controller = new AbortController();
    resendRequest.current = controller;
    setResendState({ phase: "sending" });
    try {
      await api.requestOtp(email, controller.signal);
      setCooldown(RESEND_COOLDOWN_SECONDS);
      setResendState({ phase: "sent" });
    } catch (error) {
      if (controller.signal.aborted) return;
      if (error instanceof ApiError && error.code === "RATE_LIMITED") {
        setCooldown(RESEND_COOLDOWN_SECONDS);
      }
      setResendState({ phase: "error", message: resendMessage(error) });
    } finally {
      resendInFlight.current = false;
      if (resendRequest.current === controller) resendRequest.current = null;
    }
  }

  if (state.phase === "success") {
    return (
      <section className="auth-page" aria-labelledby="otp-success-title">
        <p className="eyebrow">{t("готово")}</p>
        <h1 id="otp-success-title">{t("вход выполнен")}</h1>
        <div className="auth-card" aria-live="polite">
          <p className="auth-success">{t("Сессия активна в памяти приложения. Домашний экран будет подключён следующим этапом.")}</p>
        </div>
      </section>
    );
  }

  const submitting = state.phase === "submitting";
  const resendDisabled = cooldown > 0 || resendState.phase === "sending";
  return (
    <section className="auth-page" aria-labelledby="otp-title">
      <p className="eyebrow">{t("проверьте почту")}</p>
      <h1 id="otp-title">{t("введите код")}</h1>
      <p className="auth-intro">{t("Код для ")}<strong className="verified-email">{email}</strong>
      </p>
      <form
        className="auth-card"
        onSubmit={(event) => void verify(event)}
        noValidate
      >
        <label htmlFor="otp-code">{t("Шестизначный код")}</label>
        <input
          id="otp-code"
          className="otp-input"
          name="code"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9]{6}"
          maxLength={6}
          value={code}
          disabled={submitting}
          aria-invalid={state.phase === "error"}
          aria-describedby={state.phase === "error" ? "otp-error" : "otp-help"}
          onChange={(event) => {
            setCode(event.target.value.replace(/\D/g, "").slice(0, 6));
            if (state.phase === "error") setState({ phase: "idle" });
          }}
        />
        <p id="otp-help" className="field-help">{t("Можно ввести код с клавиатуры или вставить его целиком.")}</p>
        {state.phase === "error" ? (
          <p id="otp-error" className="form-error" role="alert">
            {t(state.message)}
          </p>
        ) : null}
        <button className="primary-button" type="submit" disabled={submitting}>
          {t(submitting ? "проверяем…" : "подтвердить")}
        </button>
        <div className="resend-row">
          <button
            className="text-button"
            type="button"
            disabled={resendDisabled}
            onClick={() => void resend()}
          >
            {t(resendState.phase === "sending"
              ? "отправляем…"
              : cooldown > 0
                ? `отправить повторно через ${cooldown} с`
                : "отправить код повторно")}
          </button>
          {resendState.phase === "sent" ? (
            <p className="form-notice" role="status">{t("Новый код запрошен.")}</p>
          ) : null}
          {resendState.phase === "error" ? (
            <p className="form-error" role="alert">
              {t(resendState.message)}
            </p>
          ) : null}
        </div>
      </form>
    </section>
  );
}

function toCredentials(result: VerifyOtpResponse) {
  return {
    accessToken: result.access_token,
    accessTokenExpiresIn: result.access_token_expires_in,
    refreshToken: result.refresh_token,
    refreshTokenExpiresAt: result.refresh_token_expires_at,
    sessionId: result.session_id,
    userId: result.user.id,
    deviceId: result.device.id,
    plan: result.subscription.plan,
  } as const;
}

function verificationMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "OTP_INVALID")
      return "Код неверен, истёк или уже использован.";
    if (error.code === "RATE_LIMITED")
      return "Слишком много попыток. Попробуйте позже.";
    if (error.code === "DEVICE_LIMIT")
      return "Достигнут лимит активных устройств.";
    if (error.code === "AUTH_FORBIDDEN")
      return "Вход для этого аккаунта недоступен.";
    if (error.code === "NETWORK_ERROR" || error.code === "TIMEOUT") {
      return "Не удалось подключиться. Проверьте сеть и попробуйте снова.";
    }
  }
  if (
    error instanceof Error &&
    error.message === "INSTALLATION_ID_UNAVAILABLE"
  ) {
    return "Не удалось подготовить устройство. Перезапустите приложение.";
  }
  return "Сервис входа временно недоступен. Попробуйте позже.";
}

function resendMessage(error: unknown): string {
  if (error instanceof ApiError && error.code === "RATE_LIMITED") {
    return "Новый код пока нельзя запросить. Попробуйте позже.";
  }
  if (
    error instanceof ApiError &&
    (error.code === "NETWORK_ERROR" || error.code === "TIMEOUT")
  ) {
    return "Не удалось подключиться. Проверьте сеть и попробуйте снова.";
  }
  return "Не удалось запросить новый код. Попробуйте позже.";
}
