import { afterEach, expect, it, vi } from "vitest";
import { readCountryCache, saveCountryCache } from "../vpn/countryCache";

afterEach(() => vi.restoreAllMocks());

it("treats invalid and oversized cached catalogs as missing", () => {
  for (const raw of [
    "{",
    "null",
    JSON.stringify({ countries: [] }),
    " ".repeat(100_001),
  ]) {
    vi.spyOn(Storage.prototype, "getItem").mockReturnValue(raw);
    expect(readCountryCache("test")).toBeNull();
  }
});

it("does not fail when catalog storage is unavailable", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw Error();
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw Error();
  });
  expect(readCountryCache("test")).toBeNull();
  expect(() =>
    saveCountryCache("test", {
      autopilot: { quality: 0, available: false },
      countries: [],
    }),
  ).not.toThrow();
});
