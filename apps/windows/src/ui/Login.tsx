import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useApplication } from "../state/application";

type FormState =
  | { phase: "idle" }
  | { phase: "submitting" }
  | { phase: "error"; message: string };

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function Login() {
  const { api } = useApplication();
  const navigate = useNavigate();
  const request = useRef<AbortController | null>(null);
  const [email, setEmail] = useState("");
  const [state, setState] = useState<FormState>({ phase: "idle" });

  useEffect(
    () => () => {
      request.current?.abort();
    },
    [],
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedEmail = email.trim().toLowerCase();
    if (!EMAIL_PATTERN.test(normalizedEmail)) {
      setState({ phase: "error", message: "Введите корректный email." });
      return;
    }

    const controller = new AbortController();
    request.current = controller;
    setState({ phase: "submitting" });
    try {
      await api.requestOtp(normalizedEmail, controller.signal);
      navigate("/auth/verify-otp", { state: { email: normalizedEmail } });
    } catch (error) {
      if (controller.signal.aborted) return;
      setState({ phase: "error", message: messageFor(error) });
    } finally {
      if (request.current === controller) request.current = null;
    }
  }

  const submitting = state.phase === "submitting";
  return (
    <section className="auth-page" aria-labelledby="login-title">
      <h1 id="login-title">войти по email</h1>
      <p className="auth-intro">отправим одноразовый код</p>
      <form
        className="auth-card"
        onSubmit={(event) => void submit(event)}
        noValidate
      >
        <label htmlFor="login-email">Email</label>
        <input
          id="login-email"
          name="email"
          type="email"
          placeholder="example@email.com"
          inputMode="email"
          autoComplete="email"
          spellCheck={false}
          value={email}
          disabled={submitting}
          aria-describedby={
            state.phase === "error" ? "login-error" : "login-help"
          }
          aria-invalid={state.phase === "error"}
          onChange={(event) => {
            setEmail(event.target.value);
            if (state.phase === "error") setState({ phase: "idle" });
          }}
        />
        <p id="login-help" className="field-help">
          Используйте адрес, к которому у вас есть доступ.
        </p>
        {state.phase === "error" ? (
          <p id="login-error" className="form-error" role="alert">
            {state.message}
          </p>
        ) : null}
        <button className="primary-button" type="submit" disabled={submitting}>
          {submitting ? "отправляем…" : "продолжить"}
        </button>
      </form>
    </section>
  );
}

function messageFor(error: unknown): string {
  if (error instanceof ApiError && error.code === "RATE_LIMITED") {
    return "Слишком много запросов. Попробуйте позже.";
  }
  if (error instanceof ApiError && error.code === "NETWORK_ERROR") {
    return "Не удалось подключиться. Проверьте сеть и попробуйте снова.";
  }
  if (error instanceof ApiError && error.code === "TIMEOUT") {
    return "Сервис входа отвечает слишком долго. Попробуйте ещё раз позже.";
  }
  return "Сервис входа временно недоступен. Попробуйте позже.";
}
