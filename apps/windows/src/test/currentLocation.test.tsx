import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type {
  PublicLocation,
  PublicLocationProvider,
} from "../location/publicLocation";
import type { VpnConnectionState } from "../vpn/connection";
import { loadConfig } from "../config/config";
import { createApiClient } from "../api/client";
import type { InstallationId } from "../native/installationId";
import { ApplicationProvider } from "../state/application";
import { CurrentLocation, LOCATION_REFRESH_MS } from "../ui/CurrentLocation";
import {
  createTestAuthenticationSession,
  createTestSessionRestoration,
  createTestVpnConnection,
} from "./fakes";

const disconnected: VpnConnectionState = {
  phase: "DISCONNECTED",
  backend: "NONE",
  tunnel: "DOWN",
};
const connected: VpnConnectionState = {
  phase: "CONNECTED",
  backend: "ACTIVE",
  tunnel: "UP",
  session: {
    sessionId: "session",
    countryCode: "DE",
    expiresAt: null,
    remainingSeconds: null,
  },
};
const home: PublicLocation = {
  ip: "203.0.113.42",
  city: "Москва",
  countryCode: "RU",
};
const vpn: PublicLocation = {
  ip: "198.51.100.42",
  city: "Berlin",
  countryCode: "DE",
};
afterEach(() => vi.useRealTimers());

function mount(provider: PublicLocationProvider) {
  const value = {
    api: createApiClient("https://unused.invalid", vi.fn(), 5000),
    config: loadConfig({}),
    desktop: { getVersion: async () => "0.3.0" },
    installationId: {
      getInstallationId: async () => "installation" as InstallationId,
    },
    session: createTestAuthenticationSession(),
    sessionRestoration: createTestSessionRestoration(),
    vpnConnection: createTestVpnConnection(),
    publicLocation: provider,
  };
  const view = (connection: VpnConnectionState) => (
    <ApplicationProvider value={value}>
      <CurrentLocation connection={connection} />
    </ApplicationProvider>
  );
  const result = render(view(disconnected));
  return {
    ...result,
    change: (connection: VpnConnectionState) =>
      result.rerender(view(connection)),
  };
}

it("updates observed egress on connection and disconnect", async () => {
  const provider = {
    current: vi
      .fn<PublicLocationProvider["current"]>()
      .mockResolvedValueOnce(home)
      .mockResolvedValueOnce(vpn)
      .mockResolvedValueOnce(home),
  };
  const result = mount(provider);
  expect(await screen.findByText(home.ip)).toBeVisible();
  result.change({ phase: "CONNECTING", backend: "UNKNOWN", tunnel: "UNKNOWN" });
  expect(screen.queryByText(home.ip)).not.toBeInTheDocument();
  expect(provider.current).toHaveBeenCalledTimes(1);
  result.change(connected);
  expect(await screen.findByText(vpn.ip)).toBeVisible();
  expect(screen.getByText("Berlin, Германия")).toBeVisible();
  result.change(disconnected);
  expect(await screen.findByText(home.ip)).toBeVisible();
});

it("ignores late replies from the previous network and cancels on unmount", async () => {
  let finish!: (location: PublicLocation) => void;
  const provider = {
    current: vi
      .fn<PublicLocationProvider["current"]>()
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finish = resolve;
          }),
      )
      .mockResolvedValue(vpn),
  };
  const result = mount(provider);
  const oldSignal = provider.current.mock.calls[0][0];
  result.change(connected);
  expect(await screen.findByText(vpn.ip)).toBeVisible();
  expect(oldSignal.aborted).toBe(true);
  await act(async () => finish(home));
  expect(screen.queryByText(home.ip)).not.toBeInTheDocument();
  result.unmount();
  expect(provider.current.mock.calls[1][0].aborted).toBe(true);
});

it("refreshes every minute and after network recovery", async () => {
  vi.useFakeTimers();
  const provider = {
    current: vi.fn<PublicLocationProvider["current"]>().mockResolvedValue(home),
  };
  mount(provider);
  await act(async () => {
    await Promise.resolve();
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(LOCATION_REFRESH_MS);
  });
  expect(provider.current).toHaveBeenCalledTimes(2);
  await act(async () => {
    fireEvent(window, new Event("online"));
  });
  expect(provider.current).toHaveBeenCalledTimes(3);
});

it("clears old location after failures and retries", async () => {
  const provider = {
    current: vi
      .fn<PublicLocationProvider["current"]>()
      .mockResolvedValueOnce(home)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(vpn),
  };
  mount(provider);
  await screen.findByText(home.ip);
  fireEvent(window, new Event("online"));
  expect(await screen.findByText("не удалось определить")).toBeVisible();
  expect(screen.queryByText(home.ip)).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "обновить текущую локацию" }),
  );
  expect(await screen.findByText(vpn.ip)).toBeVisible();
});
