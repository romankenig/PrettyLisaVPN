import { createContext, useContext, type ReactNode } from "react";
import type { AppConfig } from "../config/config";
import type { createApiClient } from "../api/client";
import type { AuthenticationSession } from "../auth/session";
import type { SessionRestoration } from "../auth/restoration";
import type { DesktopAdapter } from "../native/desktop";
import type { InstallationIdProvider } from "../native/installationId";
import type { VpnConnectionManager } from "../vpn/connection";
import type { PublicLocationProvider } from "../location/publicLocation";
export interface ApplicationState {
  config: AppConfig;
  api: ReturnType<typeof createApiClient>;
  desktop: DesktopAdapter;
  installationId: InstallationIdProvider;
  session: AuthenticationSession;
  sessionRestoration: SessionRestoration;
  vpnConnection: VpnConnectionManager;
  publicLocation?: PublicLocationProvider;
}
const ApplicationContext = createContext<ApplicationState | null>(null);
export function ApplicationProvider({
  value,
  children,
}: {
  value: ApplicationState;
  children: ReactNode;
}) {
  return (
    <ApplicationContext.Provider value={value}>
      {children}
    </ApplicationContext.Provider>
  );
}
export function useApplication(): ApplicationState {
  const application = useContext(ApplicationContext);
  if (!application) throw new Error("APPLICATION_PROVIDER_REQUIRED");
  return application;
}
