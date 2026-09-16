import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { loadConfig } from "./config/config";
import { createApiClient } from "./api/client";
import { createAuthenticationSession } from "./auth/session";
import { createSessionRestoration } from "./auth/restoration";
import { desktopAdapter } from "./native/desktop";
import { createCredentialStorage } from "./native/credentialStorage";
import { createHttpTransport } from "./native/http";
import { installationIdProvider } from "./native/installationId";
import { createWireGuardKeyManager } from "./native/wireguardKeys";
import { createWireGuardTunnelController } from "./native/wireguardTransport";
import { createVpnConnectionManager } from "./vpn/connection";
import { ApplicationProvider } from "./state/application";
import { App } from "./ui/App";
import { SessionRestorationGate } from "./ui/SessionRestorationGate";
import "./ui/styles.css";
const root = createRoot(document.getElementById("root")!);
try {
  const config = loadConfig(import.meta.env);
  const api = createApiClient(
    config.backendBaseUrl,
    createHttpTransport(),
    config.backendTimeoutMs,
  );
  const credentialStorage = createCredentialStorage();
  const session = createAuthenticationSession(credentialStorage);
  const sessionRestoration = createSessionRestoration(
    api,
    credentialStorage,
    session,
  );
  const vpnConnection = createVpnConnectionManager(
    api,
    createWireGuardKeyManager(),
    createWireGuardTunnelController(),
  );
  root.render(
    <StrictMode>
      <ApplicationProvider
        value={{
          config,
          api,
          desktop: desktopAdapter,
          installationId: installationIdProvider,
          session,
          sessionRestoration,
          vpnConnection,
        }}
      >
        <HashRouter>
          <SessionRestorationGate
            restoration={sessionRestoration}
            session={session}
          >
            <App />
          </SessionRestorationGate>
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
