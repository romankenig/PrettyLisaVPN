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
        <nav aria-label="основная навигация">
          {items.map((item) =>
            authenticating ? (
              <span
                key={item.to}
                className="nav-disabled"
                role="link"
                aria-disabled="true"
                aria-label={item.label}
                title={item.label}
              >
                <NavigationIcon name={item.icon} />
              </span>
            ) : (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                aria-label={item.label}
                title={item.label}
              >
                <NavigationIcon name={item.icon} />
              </NavLink>
            ),
          )}
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
