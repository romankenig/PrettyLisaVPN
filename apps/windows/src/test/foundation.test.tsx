import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { loadConfig } from "../config/config";
import { createApiClient } from "../api/client";
import { ApplicationProvider } from "../state/application";
import { App } from "../ui/App";
describe("configuration", () => {
  it("loads development defaults", () => {
    expect(loadConfig({})).toMatchObject({
      environment: "development",
      backendBaseUrl: "http://127.0.0.1:8000",
    });
  });
  it("normalizes a configured backend path", () => {
    expect(
      loadConfig({ VITE_BACKEND_BASE_URL: "https://api.example.invalid/api/" })
        .backendBaseUrl,
    ).toBe("https://api.example.invalid/api");
  });
  it.each([
    "file:///tmp",
    "https://user:secret@example.invalid",
    "bad",
    "https://example.invalid?key=x",
  ])("rejects invalid URL %s", (url) => {
    expect(() => loadConfig({ VITE_BACKEND_BASE_URL: url })).toThrow(
      "INVALID_BACKEND_BASE_URL",
    );
  });
  it("requires production HTTPS and a known environment", () => {
    expect(() => loadConfig({ VITE_APP_ENVIRONMENT: "production" })).toThrow(
      "BACKEND_HTTPS_REQUIRED",
    );
    expect(() => loadConfig({ VITE_APP_ENVIRONMENT: "unknown" })).toThrow(
      "INVALID_APP_ENVIRONMENT",
    );
  });
});
describe("API boundary", () => {
  it("uses the configured base URL", async () => {
    const data = {
      application_name: "PrettyLisaVPN",
      application_version: "0.1.0",
      environment: "development",
    };
    const transport = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(JSON.stringify(data)));
    await expect(
      createApiClient("https://api.example.invalid", transport).getVersion(),
    ).resolves.toEqual(data);
    expect(transport).toHaveBeenCalledWith(
      "https://api.example.invalid/version",
      { signal: undefined, credentials: "omit" },
    );
  });
  it("returns safe errors for transport, HTTP and schema failures", async () => {
    const transport = vi.fn<typeof fetch>();
    const api = createApiClient("https://api.example.invalid", transport);
    transport.mockRejectedValueOnce(new Error("sensitive detail"));
    await expect(api.getVersion()).rejects.toThrow("NETWORK_ERROR");
    transport.mockResolvedValueOnce(new Response("", { status: 503 }));
    await expect(api.getVersion()).rejects.toThrow("HTTP_ERROR");
    transport.mockResolvedValueOnce(new Response("{}"));
    await expect(api.getVersion()).rejects.toThrow("INVALID_RESPONSE");
  });
});
it("navigates without contacting the backend and reads native version through the adapter", async () => {
  const config = loadConfig({});
  const transport = vi.fn<typeof fetch>();
  render(
    <ApplicationProvider
      value={{
        config,
        api: createApiClient(config.backendBaseUrl, transport),
        desktop: { getVersion: async () => "0.1.0" },
      }}
    >
      <MemoryRouter>
        <App />
      </MemoryRouter>
    </ApplicationProvider>,
  );
  expect(
    screen.getByRole("heading", { name: "PrettyLisaVPN" }),
  ).toBeInTheDocument();
  expect(screen.getByText("development")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("link", { name: "О приложении" }));
  expect(await screen.findByText("0.1.0")).toBeInTheDocument();
  expect(transport).not.toHaveBeenCalled();
});
