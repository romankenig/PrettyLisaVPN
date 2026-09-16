import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ApiError, type ApiClient, type DeviceResponse } from "../api/client";
import { createAuthenticationSession } from "../auth/session";
import { loadConfig } from "../config/config";
import type { InstallationId } from "../native/installationId";
import { ApplicationProvider } from "../state/application";
import { App } from "../ui/App";
import {
  createTestCredentialStorage,
  createTestSessionRestoration,
  createTestVpnConnection,
} from "./fakes";

const currentDevice: DeviceResponse = {
  id: "123e4567-e89b-42d3-a456-426614174001",
  installation_id: "123e4567-e89b-42d3-a456-426614174002",
  device_name: "Этот компьютер",
  platform: "WINDOWS",
  status: "ACTIVE",
  created_at: "2026-09-01T10:00:00Z",
  updated_at: "2026-09-01T10:00:00Z",
  revoked_at: null,
  is_current: true,
};

const otherDevice: DeviceResponse = {
  id: "123e4567-e89b-42d3-a456-426614174003",
  installation_id: "123e4567-e89b-42d3-a456-426614174004",
  device_name: "Pixel",
  platform: "ANDROID",
  status: "ACTIVE",
  created_at: "2026-09-02T10:00:00Z",
  updated_at: "2026-09-02T10:00:00Z",
  revoked_at: null,
  is_current: false,
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
    listDevices: vi.fn().mockResolvedValue([currentDevice, otherDevice]),
    revokeDevice: vi.fn().mockResolvedValue({
      status: "revoked",
      device: { ...otherDevice, status: "REVOKED" },
    }),
    listVpnCountries: vi.fn(),
    createVpnSession: vi.fn(),
    getCurrentVpnSession: vi.fn().mockResolvedValue({ session: null }),
    disconnectVpnSession: vi.fn(),
  };
}

function renderDevices(api = mockApi()) {
  const storage = createTestCredentialStorage();
  storage.delete = vi.fn(storage.delete);
  const session = createAuthenticationSession(storage);
  session.activateRestored({
    accessToken: "access-token",
    accessTokenExpiresIn: 900,
    sessionId: "123e4567-e89b-42d3-a456-426614174005",
    userId: "123e4567-e89b-42d3-a456-426614174006",
    plan: "FREE",
    profile: {
      id: "123e4567-e89b-42d3-a456-426614174006",
      email: "user@example.com",
      plan: "FREE",
      active_device_count: 2,
    },
  });
  const result = render(
    <ApplicationProvider
      value={{
        config: loadConfig({}),
        api,
        desktop: { getVersion: async () => "0.1.0" },
        installationId: {
          getInstallationId: async () =>
            "123e4567-e89b-42d3-a456-426614174002" as InstallationId,
        },
        session,
        sessionRestoration: createTestSessionRestoration(),
        vpnConnection: createTestVpnConnection(),
      }}
    >
      <MemoryRouter initialEntries={["/devices"]}>
        <App />
      </MemoryRouter>
    </ApplicationProvider>,
  );
  return { ...result, api, session, storage };
}

describe("Devices screen", () => {
  it("loads device metadata and marks the current device", async () => {
    const { api } = renderDevices();

    expect(screen.getByRole("status")).toHaveTextContent(
      "загружаем устройства",
    );
    expect(await screen.findByText("Этот компьютер")).toBeInTheDocument();
    expect(screen.getByText("Windows")).toBeInTheDocument();
    expect(screen.getByText("Pixel")).toBeInTheDocument();
    expect(screen.getByText("Android")).toBeInTheDocument();
    expect(screen.getByText("текущее устройство")).toBeInTheDocument();
    expect(screen.getAllByText("активно")).toHaveLength(2);
    expect(
      screen.getByText(/не более 5 активных устройств/),
    ).toBeInTheDocument();
    expect(api.listDevices).toHaveBeenCalledWith(
      "access-token",
      expect.any(AbortSignal),
    );
    expect(
      screen.getAllByRole("button", { name: "отозвать доступ" }),
    ).toHaveLength(1);
  });

  it("requires confirmation, revokes another device, and refreshes the list", async () => {
    const api = mockApi();
    vi.mocked(api.listDevices)
      .mockResolvedValueOnce([currentDevice, otherDevice])
      .mockResolvedValueOnce([currentDevice]);
    renderDevices(api);
    await screen.findByText("Pixel");

    fireEvent.click(screen.getByRole("button", { name: "отозвать доступ" }));
    expect(api.revokeDevice).not.toHaveBeenCalled();
    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      "все его активные сессии будут завершены",
    );

    fireEvent.click(screen.getByRole("button", { name: "да, отозвать" }));

    await waitFor(() =>
      expect(api.revokeDevice).toHaveBeenCalledWith(
        "access-token",
        otherDevice.id,
      ),
    );
    await waitFor(() => expect(api.listDevices).toHaveBeenCalledTimes(2));
    expect(
      await screen.findByText(/Доступ устройства «Pixel» отозван/),
    ).toBeInTheDocument();
    expect(screen.queryByText("Pixel")).not.toBeInTheDocument();
  });

  it("can cancel revocation without changing the device", async () => {
    const { api } = renderDevices();
    await screen.findByText("Pixel");
    fireEvent.click(screen.getByRole("button", { name: "отозвать доступ" }));
    fireEvent.click(screen.getByRole("button", { name: "отмена" }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(api.revokeDevice).not.toHaveBeenCalled();
  });

  it("keeps the device and reports a revocation failure", async () => {
    const api = mockApi();
    vi.mocked(api.revokeDevice).mockRejectedValue(
      new ApiError("DEVICE_NOT_FOUND"),
    );
    renderDevices(api);
    await screen.findByText("Pixel");
    fireEvent.click(screen.getByRole("button", { name: "отозвать доступ" }));
    fireEvent.click(screen.getByRole("button", { name: "да, отозвать" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Устройство уже удалено или недоступно",
    );
    expect(screen.getByText("Pixel")).toBeInTheDocument();
    expect(api.listDevices).toHaveBeenCalledOnce();
  });

  it("shows load errors and retries", async () => {
    const api = mockApi();
    vi.mocked(api.listDevices)
      .mockRejectedValueOnce(new ApiError("NETWORK_ERROR"))
      .mockResolvedValueOnce([currentDevice]);
    renderDevices(api);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Не удалось подключиться",
    );
    fireEvent.click(screen.getByRole("button", { name: "повторить" }));

    expect(await screen.findByText("Этот компьютер")).toBeInTheDocument();
    expect(api.listDevices).toHaveBeenCalledTimes(2);
  });

  it("clears secure credentials after an unauthorized response", async () => {
    const api = mockApi();
    vi.mocked(api.listDevices).mockRejectedValue(new ApiError("AUTH_INVALID"));
    const { session, storage } = renderDevices(api);

    await waitFor(() => expect(storage.delete).toHaveBeenCalledOnce());
    expect(session.current()).toBeNull();
  });
});
