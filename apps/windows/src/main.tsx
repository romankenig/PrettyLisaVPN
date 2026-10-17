import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { loadConfig } from "./config/config";
import { createApiClient } from "./api/client";
import { createBillingClient } from "./billing/client";
import {
  createPaymentBrowser,
  validatePaymentUrl,
} from "./native/paymentBrowser";
import { createAuthenticationSession } from "./auth/session";
import { createSessionRestoration } from "./auth/restoration";
import { desktopAdapter } from "./native/desktop";
import { createCredentialStorage } from "./native/credentialStorage";
import { createHttpTransport } from "./native/http";
import { installationIdProvider } from "./native/installationId";
import { createDefaultVpnConnection } from "./vpn/defaultConnection";
import { ApplicationProvider } from "./state/application";
import { App } from "./ui/App";
import { SessionRestorationGate } from "./ui/SessionRestorationGate";
import { WindowFrame } from "./ui/WindowFrame";
import { createPublicLocationProvider } from "./location/publicLocation";
import { createReviewVpnConnection } from "./review/vpnFixture";
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
  const reviewVpn =
    config.environment === "test" && import.meta.env.VITE_UI_REVIEW_VPN === "1";
  const vpnConnection = reviewVpn
    ? createReviewVpnConnection(api)
    : createDefaultVpnConnection(api);
  if (reviewVpn) document.documentElement.dataset.vpnReview = "synthetic";
  root.render(
    <StrictMode>
      <ApplicationProvider
        value={{
          config,
          api,
          billing: createBillingClient(
            config.backendBaseUrl,
            createHttpTransport(),
            config.backendTimeoutMs,
          ),
          paymentBrowser: reviewVpn
            ? {
                async open(url) {
                  validatePaymentUrl(url, ["payments.example.test"]);
                  document.documentElement.dataset.paymentReviewUrl = "opened";
                },
              }
            : createPaymentBrowser(
                String(import.meta.env.VITE_PAYMENT_ALLOWED_HOSTS ?? "")
                  .split(",")
                  .map((host) => host.trim())
                  .filter(Boolean),
              ),
          desktop: desktopAdapter,
          installationId: installationIdProvider,
          session,
          sessionRestoration,
          vpnConnection,
          publicLocation: createPublicLocationProvider(
            createHttpTransport(),
            import.meta.env.VITE_PUBLIC_LOCATION_URL,
            config.environment === "test",
          ),
        }}
      >
        <HashRouter>
          <WindowFrame>
            <SessionRestorationGate
              restoration={sessionRestoration}
              session={session}
            >
              <App />
            </SessionRestorationGate>
          </WindowFrame>
        </HashRouter>
      </ApplicationProvider>
    </StrictMode>,
  );
} catch {
  root.render(
    <WindowFrame>
      <main role="alert">
        <h1>
          не удалось запустить{" "}
          <span className="product-name">PrettyLisaVPN</span>
        </h1>
        <p>проверьте конфигурацию приложения.</p>
      </main>
    </WindowFrame>,
  );
}
