import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useApplication } from "../state/application";
import { Devices } from "./Devices";
import { Home } from "./Home";
import { Login } from "./Login";
import { OtpVerification } from "./OtpVerification";
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
          <NavLink to="/devices">устройства</NavLink>
        </nav>
        <p className="sidebar-note">windows desktop</p>
      </aside>
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/about" element={<About />} />
          <Route path="/devices" element={<Devices />} />
          <Route path="/login" element={<Login />} />
          <Route path="/auth/verify-otp" element={<OtpVerification />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
