import { LanguageSelector } from "./LanguageSelector";
import { t, useLanguage } from "../i18n";
import {
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { About } from "./About";
import { AccountMessages } from "./AccountMessages";
import { Home } from "./Home";
import { HomeCountryObserver } from "./HomeCountryObserver";
import { Login } from "./Login";
import { NavigationIcon } from "./NavigationIcon";
import { OtpVerification } from "./OtpVerification";
import { Settings } from "./Settings";
import { useVersions } from "./useVersions";

export function App() {
  useLanguage();
  const versions = useVersions();
  const { pathname } = useLocation();
  const authenticating =
    pathname === "/login" || pathname === "/auth/verify-otp";
  const items = [
    { to: "/", label: "главная", icon: "home" },
    { to: "/settings", label: "настройки", icon: "settings" },
    { to: "/about", label: "о приложении", icon: "about" },
  ] as const;
  return (
    <div className="shell">
      <HomeCountryObserver />
      <AccountMessages version={versions.frontend} />
      <aside className="sidebar">
        <nav aria-label={t("основная навигация")}>
          {items.map((item) =>
            authenticating ? (
              <span
                key={item.to}
                className="nav-disabled"
                role="link"
                aria-disabled="true"
                aria-label={t(item.label)}
                title={t(item.label)}
              >
                <NavigationIcon name={item.icon} />
              </span>
            ) : (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                aria-label={t(item.label)}
                title={t(item.label)}
              >
                <NavigationIcon name={item.icon} />
              </NavLink>
            ),
          )}
        </nav>
        <div className="sidebar-footer">
          <LanguageSelector />
          <dl className="sidebar-versions" aria-label={t("версии приложения")}>
            <div>
              <dt>Frontend</dt>
              <dd title={t(versions.frontend)}>{t(versions.frontend)}</dd>
            </div>
            <div>
              <dt>Backend</dt>
              <dd title={t(versions.backend)}>{t(versions.backend)}</dd>
            </div>
          </dl>
        </div>
      </aside>
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route
            path="/about"
            element={
              <About frontend={versions.frontend} backend={versions.backend} />
            }
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
