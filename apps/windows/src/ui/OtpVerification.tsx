import { Navigate, useLocation } from "react-router-dom";

interface OtpRouteState {
  readonly email: string;
}

export function OtpVerification() {
  const location = useLocation();
  const state = location.state as OtpRouteState | null;
  if (!state?.email) return <Navigate to="/login" replace />;

  return (
    <section className="auth-page" aria-labelledby="otp-title">
      <p className="eyebrow">проверьте почту</p>
      <h1 id="otp-title">введите код</h1>
      <div className="auth-card" aria-live="polite">
        <p className="auth-success">
          Если адрес может получать письма, код уже отправлен. Он действует
          ограниченное время.
        </p>
        <p className="field-help">
          Экран ввода и проверки кода будет подключён следующим этапом.
        </p>
      </div>
    </section>
  );
}
