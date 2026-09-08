import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import logoUrl from "../assets/prettylisavpn-logo.svg";
import { useBackendStatus } from "../state/backendStatus";
import { useApplication } from "../state/application";
import { Login } from "./Login";
import { OtpVerification } from "./OtpVerification";
function Home() {
  const { config, api } = useApplication();
  const { status, retry } = useBackendStatus(
    api,
    config.backendHealthIntervalMs,
  );
  return (
    <section className="home">
      <p className="eyebrow">windows</p>
      <h1 className="visually-hidden">{config.applicationName}</h1>
      <div className="logo-panel">
        <img className="main-logo" src={logoUrl} alt="PrettyLisaVPN" />
      </div>
      <p className="intro">ваше пространство. ваше подключение.</p>
      <div
        className={`backend-card backend-card--${status.phase}`}
        aria-live="polite"
      >
        <div className="backend-card__header">
          <span className="status-dot" aria-hidden="true" />
          <strong>backend: {status.phase}</strong>
        </div>
        {status.phase === "online" && status.version ? (
          <dl className="backend-details">
            <div>
              <dt>api version</dt>
              <dd>{status.version.application_version}</dd>
            </div>
            <div>
              <dt>backend environment</dt>
              <dd>{status.version.environment}</dd>
            </div>
          </dl>
        ) : null}
        {status.phase === "offline" ? (
          <button type="button" onClick={() => void retry()}>
            retry
          </button>
        ) : null}
      </div>
      <span className="badge">client environment: {config.environment}</span>
    </section>
  );
}
function About() {
  const { desktop, config } = useApplication();
  const [version, setVersion] = useState("…");
  useEffect(() => {
    let active = true;
    desktop
      .getVersion()
      .then((value) => {
        if (active) setVersion(value);
      })
      .catch(() => {
        if (active) setVersion("недоступна");
      });
    return () => {
      active = false;
    };
  }, [desktop]);
  return (
    <section>
      <p className="eyebrow">приложение</p>
      <h1>о приложении</h1>
      <dl>
        <dt>версия клиента</dt>
        <dd>{version}</dd>
        <dt>окружение</dt>
        <dd>{config.environment}</dd>
      </dl>
    </section>
  );
}
export function App() {
  return (
    <div className="shell">
      <aside>
        <p className="brand">PrettyLisaVPN</p>
        <nav aria-label="основная навигация">
          <NavLink to="/" end>
            главная
          </NavLink>
          <NavLink to="/about">о приложении</NavLink>
          <NavLink to="/login">войти</NavLink>
        </nav>
        <p className="sidebar-note">windows desktop</p>
      </aside>
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/about" element={<About />} />
          <Route path="/login" element={<Login />} />
          <Route path="/auth/verify-otp" element={<OtpVerification />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
