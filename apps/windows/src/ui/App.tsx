import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useApplication } from "../state/application";
import { Home } from "./Home";
import { Login } from "./Login";
import { NavigationIcon } from "./NavigationIcon";
import { OtpVerification } from "./OtpVerification";
import { Settings } from "./Settings";
import { useVersions } from "./useVersions";

function About({ version }: { readonly version: string }) {
  const { config } = useApplication();
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
  const versions = useVersions();
  return (
    <div className="shell">
      <aside className="sidebar">
        <nav aria-label="основная навигация">
          <NavLink to="/" end aria-label="главная" title="главная">
            <NavigationIcon name="home" />
          </NavLink>
          <NavLink to="/settings" aria-label="настройки" title="настройки">
            <NavigationIcon name="settings" />
          </NavLink>
          <NavLink to="/about" aria-label="о приложении" title="о приложении">
            <NavigationIcon name="about" />
          </NavLink>
        </nav>
        <dl className="sidebar-versions" aria-label="версии приложения">
          <div>
            <dt>Frontend</dt>
            <dd title={versions.frontend}>{versions.frontend}</dd>
          </div>
          <div>
            <dt>Backend</dt>
            <dd title={versions.backend}>{versions.backend}</dd>
          </div>
        </dl>
      </aside>
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route
            path="/about"
            element={<About version={versions.frontend} />}
          />
          <Route path="/settings/*" element={<Settings />} />
          <Route
            path="/devices"
            element={<Navigate to="/settings/devices" replace />}
          />
          <Route path="/login" element={<Login />} />
          <Route path="/auth/verify-otp" element={<OtpVerification />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
