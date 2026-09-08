import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { loadConfig } from "./config/config";
import { createApiClient } from "./api/client";
import { desktopAdapter } from "./native/desktop";
import { createHttpTransport } from "./native/http";
import { installationIdProvider } from "./native/installationId";
import { ApplicationProvider } from "./state/application";
import { App } from "./ui/App";
import "./ui/styles.css";
const root = createRoot(document.getElementById("root")!);
try {
  const config = loadConfig(import.meta.env);
  root.render(
    <StrictMode>
      <ApplicationProvider
        value={{
          config,
          api: createApiClient(
            config.backendBaseUrl,
            createHttpTransport(),
            config.backendTimeoutMs,
          ),
          desktop: desktopAdapter,
          installationId: installationIdProvider,
        }}
      >
        <HashRouter>
          <App />
        </HashRouter>
      </ApplicationProvider>
    </StrictMode>,
  );
} catch {
  root.render(
    <main role="alert">
      <h1>не удалось запустить PrettyLisaVPN</h1>
      <p>проверьте конфигурацию приложения.</p>
    </main>,
  );
}
