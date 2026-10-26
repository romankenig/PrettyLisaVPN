import { afterEach, expect, it, vi } from "vitest";
import {
  createPublicLocationProvider,
  parsePublicLocation,
} from "../location/publicLocation";
import type { HttpTransport } from "../native/http";

afterEach(() => vi.useRealTimers());
const observation = {
  success: true,
  ip: "203.0.113.42",
  country_code: "DE",
  city: "Berlin",
};

it("observes egress without sending account credentials or caching", async () => {
  const transport = vi
    .fn<HttpTransport>()
    .mockResolvedValue(new Response(JSON.stringify(observation)));
  const location = await createPublicLocationProvider(transport).current(
    new AbortController().signal,
  );
  expect(location).toEqual({
    ip: "203.0.113.42",
    countryCode: "DE",
    city: "Berlin",
  });
  expect(transport).toHaveBeenCalledWith(
    new URL("https://ipwho.is/"),
    expect.objectContaining({
      credentials: "omit",
      cache: "no-store",
      signal: expect.any(AbortSignal),
    }),
  );
  expect(transport.mock.calls[0][1]?.headers).toBeUndefined();
});

it("accepts IPv6 and missing city/country without inventing data", () => {
  expect(parsePublicLocation({ success: true, ip: "2001:db8::42" })).toEqual({
    ip: "2001:db8::42",
    countryCode: null,
    city: null,
  });
});

it.each([
  null,
  { ...observation, success: false },
  { ...observation, ip: "999.1.1.1" },
  { ...observation, ip: "not-an-ip" },
])("rejects invalid observations", (value) => {
  expect(() => parsePublicLocation(value)).toThrow("INVALID_PUBLIC_LOCATION");
});

it("bounds a provider that ignores AbortSignal", async () => {
  vi.useFakeTimers();
  const transport = vi.fn<HttpTransport>(() => new Promise(() => undefined));
  const result = createPublicLocationProvider(transport).current(
    new AbortController().signal,
  );
  const assertion = expect(result).rejects.toThrow(
    "PUBLIC_LOCATION_UNAVAILABLE",
  );
  await vi.advanceTimersByTimeAsync(17000);
  await assertion;
  expect(transport.mock.calls[0][1]?.signal?.aborted).toBe(true);
});

it("cancels requests and rejects HTTP failures", async () => {
  const transport = vi.fn<HttpTransport>(() => new Promise(() => undefined));
  const controller = new AbortController();
  const result = createPublicLocationProvider(transport).current(
    controller.signal,
  );
  const assertion = expect(result).rejects.toThrow(
    "PUBLIC_LOCATION_UNAVAILABLE",
  );
  controller.abort();
  await assertion;
  const failed = vi
    .fn<HttpTransport>()
    .mockResolvedValue(new Response("rate limited", { status: 429 }));
  await expect(
    createPublicLocationProvider(failed).current(new AbortController().signal),
  ).rejects.toThrow("PUBLIC_LOCATION_UNAVAILABLE");
});

it("permits loopback fixtures only when explicitly enabled", () => {
  const transport = vi.fn<HttpTransport>();
  expect(() =>
    createPublicLocationProvider(
      transport,
      "http://127.0.0.1:8000/public-location",
    ),
  ).toThrow();
  expect(() =>
    createPublicLocationProvider(
      transport,
      "http://127.0.0.1:8000/public-location",
      true,
    ),
  ).not.toThrow();
  expect(() =>
    createPublicLocationProvider(
      transport,
      "https://user:password@example.com",
    ),
  ).toThrow();
});
