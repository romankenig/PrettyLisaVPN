import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useApplication } from "../state/application";
function Home() {
  const { config } = useApplication();
  return (
    <section>
      <p className="eyebrow">WINDOWS</p>
      <h1>{config.applicationName}</h1>
      <p className="intro">Ваше пространство. Ваше подключение.</p>
      <span className="badge">{config.environment}</span>
      <p className="note">Основа приложения готова к развитию.</p>
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
        if (active) setVersion("Недоступна");
      });
    return () => {
      active = false;
    };
  }, [desktop]);
  return (
    <section>
      <p className="eyebrow">ПРИЛОЖЕНИЕ</p>
      <h1>О приложении</h1>
      <dl>
        <dt>Версия клиента</dt>
        <dd>{version}</dd>
        <dt>Окружение</dt>
        <dd>{config.environment}</dd>
      </dl>
    </section>
  );
}
export function App() {
  return (
    <div className="shell">
      <aside>
        <div className="brand">
          PrettyLisa<span>VPN</span>
        </div>
        <nav aria-label="Основная навигация">
          <NavLink to="/" end>
            Главная
          </NavLink>
          <NavLink to="/about">О приложении</NavLink>
        </nav>
        <p className="sidebar-note">Windows desktop</p>
      </aside>
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/about" element={<About />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
