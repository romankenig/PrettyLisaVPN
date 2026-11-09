import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { createApiClient } from "../api/client";
import { createAuthenticationSession } from "../auth/session";
import { loadConfig } from "../config/config";
import { ApplicationProvider } from "../state/application";
import { App } from "../ui/App";
import { SessionRestorationGate } from "../ui/SessionRestorationGate";
import {
  createTestCredentialStorage,
  createTestSessionRestoration,
  createTestVpnConnection,
} from "./fakes";
const id = "11111111-1111-4111-8111-111111111111";
const key = "a".repeat(64);
const response = {
  token_type: "bearer",
  access_token: "guest-access",
  access_token_expires_in: 900,
  refresh_token: "guest-refresh",
  refresh_token_expires_at: "2030-01-01T00:00:00Z",
  session_id: id,
  user: { id },
  device: { id, installation_id: id, status: "ACTIVE" },
  subscription: { plan: "DEMO", status: "ACTIVE" },
};
function setup() {
  const requests: { url: string; init?: RequestInit }[] = [];
  const transport = vi.fn(
    async (url: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ url: String(url), init });
      if (String(url).endsWith("/version"))
        return Response.json({ application_version: "0.40.0" });
      if (String(url).endsWith("/auth/demo")) return Response.json(response);
      if (String(url).endsWith("/me"))
        return Response.json({
          id,
          email: null,
          plan: "DEMO",
          active_device_count: 1,
          entitlements: {
            daily_vpn_limit_seconds: 900,
            free_seconds_usable: 900,
          },
        });
      if (String(url).endsWith("/vpn/countries"))
        return Response.json({
          autopilot: { available: true, quality: 90 },
          countries: [{ country_code: "DE", available: true, quality: 90 }],
        });
      if (String(url).endsWith("/auth/logout"))
        return Response.json({ status: "logged_out" });
      return Response.json({}, { status: 404 });
    },
  );
  const api = createApiClient("https://api.example.test", transport, 1000);
  const storage = createTestCredentialStorage(),
    session = createAuthenticationSession(storage);
  const restoration = createTestSessionRestoration(),
    vpn = createTestVpnConnection();
  vi.spyOn(vpn, "disconnect");
  render(
    <ApplicationProvider
      value={{
        config: loadConfig({}),
        api,
        session,
        sessionRestoration: restoration,
        vpnConnection: vpn,
        desktop: { getVersion: async () => "0.27.0" },
        installationId: { getInstallationId: vi.fn() },
        demoDeviceKey: async () => key,
      }}
    >
      <MemoryRouter initialEntries={["/login"]}>
        <SessionRestorationGate session={session} restoration={restoration}>
          <App />
        </SessionRestorationGate>
      </MemoryRouter>
    </ApplicationProvider>,
  );
  return { requests, storage, session, vpn };
}
it("enters a guest session without email, retains the credential and offers all plans", async () => {
  const { requests, storage, session, vpn } = setup();
  fireEvent.click(
    await screen.findByRole("button", { name: /попробовать без регистрации/ }),
  );
  await screen.findByText("гость на этом устройстве");
  expect(session.current()?.plan).toBe("DEMO");
  expect(await storage.retrieve()).not.toBeNull();
  expect(
    JSON.parse(
      requests.find((r) => r.url.endsWith("/auth/demo"))!.init!.body as string,
    ),
  ).toEqual({ device_key: key, platform: "WINDOWS" });
  expect(requests.some((r) => r.url.includes("/auth/request-otp"))).toBe(false);
  fireEvent.click(screen.getByRole("link", { name: "улучшить" }));
  const premium = screen.getByRole("region", { name: "PREMIUM" });
  expect(within(premium).getByText("399 ₽")).toBeVisible();
  expect(within(premium).getByRole("button", { name: "купить" })).toBeEnabled();
  expect(screen.getByRole("region", { name: "FREE" })).toBeVisible();
  expect(screen.getByRole("region", { name: "DEMO" })).toHaveTextContent(
    "ваш тариф",
  );
  fireEvent.click(within(premium).getByRole("button", { name: "купить" }));
  await screen.findByRole("textbox", { name: "Email" });
  expect(vpn.disconnect).toHaveBeenCalledOnce();
  expect(session.current()).toBeNull();
  expect(requests.some((r) => r.url.includes("/billing/operations"))).toBe(
    false,
  );
});
it("rejects malformed guest credentials without establishing a session", async () => {
  const transport = vi.fn(async (url: RequestInfo | URL) =>
    Response.json(
      String(url).endsWith("/version")
        ? { application_version: "0.40.0" }
        : {
            ...response,
            subscription: { plan: "FREE", status: "ACTIVE" },
          },
    ),
  );
  const api = createApiClient("https://api.example.test", transport, 1000);
  await expect(api.demo(key)).rejects.toThrow();
  await expect(api.demo("raw-machine-id")).rejects.toThrow();
  expect(transport).toHaveBeenCalledTimes(2);
});

it.each(["0.39.0", "0.39.9-dev.12+g123", "dev-123", "invalid", ""])(
  "does not send a Windows device identity to an incompatible API (%s)",
  async (version) => {
    const transport = vi.fn<typeof fetch>(async () =>
      Response.json({ application_version: version }),
    );
    const api = createApiClient("https://api.example.test", transport, 1000);
    await expect(api.demo(key)).rejects.toMatchObject({
      code: "DEMO_UNAVAILABLE",
    });
    expect(transport).toHaveBeenCalledTimes(1);
    expect(String(transport.mock.calls[0]?.[0])).toContain("/version");
  },
);

it.each(["0.40.0-dev.12+g123", "0.41.0", "1.0.0"])(
  "admits Windows DEMO with a compatible API (%s)",
  async (version) => {
    const transport = vi.fn(async (url: RequestInfo | URL) =>
      Response.json(
        String(url).endsWith("/version")
          ? { application_version: version }
          : response,
      ),
    );
    const api = createApiClient("https://api.example.test", transport, 1000);
    await expect(api.demo(key)).resolves.toEqual(response);
  },
);
