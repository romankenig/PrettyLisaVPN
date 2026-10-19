import { beforeEach, expect, it, vi } from "vitest";
import { createPublicLocationProvider } from "../location/publicLocation";
import { createPublicLocationTransport } from "../native/publicLocation";

const bridge = vi.hoisted(() => ({
  native: true,
  invoke: vi.fn(),
  fetch: vi.fn(),
}));
vi.mock("@tauri-apps/api/core", () => ({
  isTauri: () => bridge.native,
  invoke: bridge.invoke,
}));
vi.mock("../native/http", () => ({
  createHttpTransport: () => bridge.fetch,
}));

beforeEach(() => {
  bridge.native = true;
  vi.clearAllMocks();
});

it("uses the fixed native command without account data", async () => {
  bridge.invoke.mockResolvedValue({
    success: true,
    ip: "203.0.113.42",
    country_code: "DE",
  });
  const result = await createPublicLocationProvider(
    createPublicLocationTransport(),
  ).current(new AbortController().signal);
  expect(result).toEqual({
    ip: "203.0.113.42",
    countryCode: "DE",
    city: null,
  });
  expect(bridge.invoke).toHaveBeenCalledWith("get_public_location");
  expect(bridge.fetch).not.toHaveBeenCalled();
});

it("keeps loopback fixtures on the scoped transport", async () => {
  bridge.fetch.mockResolvedValue(
    new Response(JSON.stringify({ success: true, ip: "203.0.113.42" })),
  );
  await createPublicLocationProvider(
    createPublicLocationTransport(),
    "http://127.0.0.1:8000/public-location",
    true,
  ).current(new AbortController().signal);
  expect(bridge.fetch).toHaveBeenCalledTimes(1);
  expect(bridge.invoke).not.toHaveBeenCalled();
});

it("uses HTTP in browser previews", async () => {
  bridge.native = false;
  bridge.fetch.mockResolvedValue(
    new Response(JSON.stringify({ success: true, ip: "203.0.113.42" })),
  );
  await createPublicLocationProvider(createPublicLocationTransport()).current(
    new AbortController().signal,
  );
  expect(bridge.fetch).toHaveBeenCalledTimes(1);
  expect(bridge.invoke).not.toHaveBeenCalled();
});

it("does not dispatch an already cancelled native observation", async () => {
  const controller = new AbortController();
  controller.abort();
  await expect(
    createPublicLocationProvider(createPublicLocationTransport()).current(
      controller.signal,
    ),
  ).rejects.toThrow("PUBLIC_LOCATION_UNAVAILABLE");
  expect(bridge.invoke).not.toHaveBeenCalled();
});
