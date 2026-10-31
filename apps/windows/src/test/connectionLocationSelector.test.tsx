import { useState } from "react";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
  act,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
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
  };
}

function renderSelector(
  api = mockApi(),
  plan: "FREE" | "PREMIUM" = "FREE",
  initial: VpnLocationSelection = DEFAULT_VPN_LOCATION_SELECTION,
) {
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
    const [selection, setSelection] = useState<VpnLocationSelection>(initial);
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

afterEach(() => vi.useRealTimers());

describe("connection location dropdown", () => {
  it.each(["FREE", "PREMIUM"] as const)(
    "defaults %s users to Autopilot and selects an available country",
    async (plan) => {
      const api = renderSelector(mockApi(), plan);
      expect(screen.getByRole("combobox")).toBeDisabled();
      await waitFor(() => expect(screen.getByRole("combobox")).toBeEnabled());
      expect(screen.getByRole("combobox")).toHaveTextContent("автопилот");
      fireEvent.click(screen.getByRole("combobox"));
      const list = screen.getByRole("listbox");
      expect(
        within(list)
          .getAllByRole("group")
          .map((g) => g.getAttribute("aria-label")),
      ).toEqual(["автопилот", "топ", "все страны"]);
      expect(
        within(list).queryByRole("option", { name: /США/ }),
      ).not.toBeInTheDocument();
      fireEvent.click(
        within(
          within(list).getByRole("group", { name: "все страны" }),
        ).getByRole("option", { name: /Германия/ }),
      );
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
      expect(screen.getByRole("combobox")).toHaveTextContent("Германия");
      expect(screen.getByText(/"mode":"COUNTRY"/)).toHaveTextContent(
        '"country_code":"DE"',
      );
      expect(api.listVpnCountries).toHaveBeenCalledWith(
        "access-token",
        expect.any(AbortSignal),
      );
    },
  );

  it("ranks the top three by availability and sorts all available countries in Russian", async () => {
    const api = mockApi();
    vi.mocked(api.listVpnCountries).mockResolvedValue({
      autopilot: availability.autopilot,
      countries: [
        { country_code: "US", quality: 93, available: true },
        { country_code: "FR", quality: 90, available: true },
        { country_code: "DE", quality: 95, available: true },
        { country_code: "NL", quality: 94, available: true },
        { country_code: "GB", quality: 100, available: false },
      ],
    });
    renderSelector(api);
    await waitFor(() => expect(screen.getByRole("combobox")).toBeEnabled());
    fireEvent.click(screen.getByRole("combobox"));
    const names = (group: string) =>
      within(screen.getByRole("group", { name: group }))
        .getAllByRole("option")
        .map((o) => o.querySelector(".location-option__name")?.textContent);
    expect(names("топ")).toEqual([
      "Германия",
      "Нидерланды",
      "Соединенные Штаты",
    ]);
    expect(names("все страны")).toEqual([
      "Германия",
      "Нидерланды",
      "Соединенные Штаты",
      "Франция",
    ]);
    expect(
      screen
        .getAllByRole("option")
        .filter(
          (o) =>
            o.querySelector(".location-option__name")?.textContent !==
            "автопилот",
        )
        .every(
          (o) =>
            o.querySelector("svg") &&
            o.querySelector(".location-option__quality"),
        ),
    ).toBe(true);
    expect(
      within(screen.getByRole("group", { name: "автопилот" }))
        .getByRole("option")
        .querySelector(".location-option__quality"),
    ).toBeNull();
    expect(
      screen.getByRole("combobox").querySelector(".quality-bars"),
    ).toBeNull();
    expect(
      within(screen.getByRole("group", { name: "все страны" }))
        .getAllByRole("option")[0]
        .querySelectorAll(".quality-bars i.filled"),
    ).toHaveLength(3);
  });

  it("restores a country and falls back to Autopilot when it is unavailable", async () => {
    renderSelector(mockApi(), "PREMIUM", {
      mode: "COUNTRY",
      country_code: "US",
    });
    await waitFor(() => expect(screen.getByRole("combobox")).toBeEnabled());
    await waitFor(() =>
      expect(screen.getByText(/"mode":"AUTO"/)).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("combobox"));
    expect(
      within(screen.getByRole("group", { name: "топ" })).getAllByRole("option"),
    ).toHaveLength(1);
  });

  it("preserves a valid previous country and supports keyboard selection and Escape", async () => {
    renderSelector(mockApi(), "PREMIUM", {
      mode: "COUNTRY",
      country_code: "DE",
    });
    await waitFor(() => expect(screen.getByRole("combobox")).toBeEnabled());
    const combo = screen.getByRole("combobox");
    expect(combo).toHaveTextContent("Германия");
    fireEvent.keyDown(combo, { key: "Home" });
    expect(combo).toHaveAttribute("aria-expanded", "true");
    fireEvent.keyDown(combo, { key: "Enter" });
    expect(combo).toHaveTextContent("автопилот");
    fireEvent.keyDown(combo, { key: "ArrowDown" });
    fireEvent.keyDown(combo, { key: "Escape" });
    expect(combo).toHaveAttribute("aria-expanded", "false");
  });

  it("disables stale data after refresh failure and recovers", async () => {
    const api = mockApi();
    vi.mocked(api.listVpnCountries)
      .mockResolvedValueOnce(availability)
      .mockRejectedValueOnce(new ApiError("NETWORK_ERROR"))
      .mockResolvedValueOnce(availability);
    renderSelector(api);
    await waitFor(() => expect(screen.getByRole("combobox")).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "обновить страны" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Проверьте сеть",
    );
    expect(screen.getByRole("combobox")).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "повторить" }));
    await waitFor(() => expect(screen.getByRole("combobox")).toBeEnabled());
  });

  it("handles an empty list and unavailable Autopilot without selectable countries", async () => {
    const api = mockApi();
    vi.mocked(api.listVpnCountries).mockResolvedValue({
      autopilot: { quality: 0, available: false },
      countries: [],
    });
    renderSelector(api);
    await waitFor(() => expect(screen.getByRole("combobox")).toBeEnabled());
    fireEvent.click(screen.getByRole("combobox"));
    expect(screen.getByRole("option")).toBeDisabled();
    expect(screen.getAllByText("нет доступных стран")).toHaveLength(2);
  });

  it("retries an initial backend error", async () => {
    const api = mockApi();
    vi.mocked(api.listVpnCountries)
      .mockRejectedValueOnce(new ApiError("SERVER_ERROR"))
      .mockResolvedValueOnce(availability);
    renderSelector(api);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Попробуйте позже",
    );
    fireEvent.click(screen.getByRole("button", { name: "повторить" }));
    await waitFor(() => expect(screen.getByRole("combobox")).toBeEnabled());
  });

  it("refreshes availability automatically after a minute", async () => {
    vi.useFakeTimers();
    const api = renderSelector();
    await act(async () => {
      await Promise.resolve();
    });
    expect(api.listVpnCountries).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(api.listVpnCountries).toHaveBeenCalledTimes(2);
  });
});
