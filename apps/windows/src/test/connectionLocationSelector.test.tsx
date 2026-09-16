import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import {
  ApiError,
  type ApiClient,
  type VpnCountriesResponse,
} from "../api/client";
import { loadConfig } from "../config/config";
import type { InstallationId } from "../native/installationId";
import { ApplicationProvider } from "../state/application";
import { ConnectionLocationSelector } from "../ui/ConnectionLocationSelector";
import {
  DEFAULT_VPN_LOCATION_SELECTION,
  type VpnLocationSelection,
} from "../vpn/selection";
import {
  createTestAuthenticationSession,
  createTestSessionRestoration,
  createTestVpnConnection,
} from "./fakes";

const availability: VpnCountriesResponse = {
  autopilot: { quality: 92, available: true },
  countries: [
    { country_code: "DE", quality: 81, available: true },
    { country_code: "US", quality: 0, available: false },
  ],
};

function mockApi(): ApiClient {
  return {
    getHealth: vi.fn(),
    getVersion: vi.fn(),
    requestOtp: vi.fn(),
    verifyOtp: vi.fn(),
    refresh: vi.fn(),
    me: vi.fn(),
    logout: vi.fn(),
    listDevices: vi.fn(),
    revokeDevice: vi.fn(),
    listVpnCountries: vi.fn().mockResolvedValue(availability),
    createVpnSession: vi.fn(),
    disconnectVpnSession: vi.fn(),
  };
}

function renderSelector(api = mockApi(), plan: "FREE" | "PREMIUM" = "FREE") {
  const session = createTestAuthenticationSession();
  session.activateRestored({
    accessToken: "access-token",
    accessTokenExpiresIn: 900,
    sessionId: "123e4567-e89b-42d3-a456-426614174001",
    userId: "123e4567-e89b-42d3-a456-426614174002",
    plan,
    profile: {
      id: "123e4567-e89b-42d3-a456-426614174002",
      email: "user@example.com",
      plan,
      active_device_count: 1,
    },
  });

  function Harness() {
    const [selection, setSelection] = useState<VpnLocationSelection>(
      DEFAULT_VPN_LOCATION_SELECTION,
    );
    return (
      <>
        <ConnectionLocationSelector
          selection={selection}
          onSelectionChange={setSelection}
          onConnectabilityChange={() => undefined}
        />
        <output>{JSON.stringify(selection)}</output>
      </>
    );
  }

  render(
    <ApplicationProvider
      value={{
        config: loadConfig({}),
        api,
        desktop: { getVersion: async () => "0.1.0" },
        installationId: {
          getInstallationId: async () =>
            "123e4567-e89b-42d3-a456-426614174000" as InstallationId,
        },
        session,
        sessionRestoration: createTestSessionRestoration(),
        vpnConnection: createTestVpnConnection(),
      }}
    >
      <MemoryRouter>
        <Harness />
      </MemoryRouter>
    </ApplicationProvider>,
  );
  return api;
}

describe("connection location selector", () => {
  it.each(["FREE", "PREMIUM"] as const)(
    "defaults %s users to Autopilot and permits an available country",
    async (plan) => {
      const api = renderSelector(mockApi(), plan);

      expect(
        screen.getByText("загружаем доступные локации…"),
      ).toBeInTheDocument();
      expect(await screen.findByText("Автопилот")).toBeInTheDocument();
      expect(screen.getByLabelText("Качество 92 из 100")).toBeInTheDocument();
      expect(screen.getByRole("radio", { name: /Автопилот/ })).toBeChecked();
      expect(screen.getByRole("radio", { name: /US/ })).toBeDisabled();

      fireEvent.click(screen.getByRole("radio", { name: /Германия/ }));
      expect(screen.getByText(/"mode":"COUNTRY"/)).toHaveTextContent(
        '"mode":"COUNTRY","country_code":"DE"',
      );
      expect(api.listVpnCountries).toHaveBeenCalledWith(
        "access-token",
        expect.any(AbortSignal),
      );
    },
  );

  it("keeps old data visibly stale and disables it after refresh failure", async () => {
    const api = mockApi();
    vi.mocked(api.listVpnCountries)
      .mockResolvedValueOnce(availability)
      .mockRejectedValueOnce(new ApiError("NETWORK_ERROR"))
      .mockResolvedValueOnce({
        autopilot: { quality: 75, available: true },
        countries: [{ country_code: "DE", quality: 64, available: true }],
      });
    renderSelector(api);
    await screen.findByText("Автопилот");

    fireEvent.click(screen.getByRole("button", { name: "обновить" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Проверьте сеть",
    );
    expect(screen.getByRole("radio", { name: /Германия/ })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "обновить" }));
    expect(
      await screen.findByLabelText("Качество 75 из 100"),
    ).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Германия/ })).toBeEnabled();
  });

  it("shows an initial backend error and retries", async () => {
    const api = mockApi();
    vi.mocked(api.listVpnCountries)
      .mockRejectedValueOnce(new ApiError("SERVER_ERROR"))
      .mockResolvedValueOnce(availability);
    renderSelector(api);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Попробуйте позже",
    );
    fireEvent.click(screen.getByRole("button", { name: "повторить" }));
    expect(await screen.findByText("Автопилот")).toBeInTheDocument();
    await waitFor(() => expect(api.listVpnCountries).toHaveBeenCalledTimes(2));
  });
});
