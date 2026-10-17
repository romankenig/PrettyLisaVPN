import { beforeEach, expect, it, vi } from "vitest";
import { readLocationSelection, saveLocationSelection } from "../vpn/selection";

beforeEach(() => localStorage.clear());

it("persists choices across sessions and isolates accounts", () => {
  saveLocationSelection("user-a", { mode: "COUNTRY", country_code: "DE" });
  expect(readLocationSelection("user-a")).toEqual({ mode: "COUNTRY", country_code: "DE" });
  expect(readLocationSelection("user-b")).toEqual({ mode: "AUTO" });
  saveLocationSelection("user-a", { mode: "AUTO" });
  expect(readLocationSelection("user-a")).toEqual({ mode: "AUTO" });
});

it.each(["invalid-json", '{"mode":"COUNTRY","country_code":"../../xx"}', '{"mode":"COUNTRY","country_code":1}', 'null'])("ignores malformed stored choices: %s", (value) => {
  localStorage.setItem("prettylisavpn.location.user-a", value);
  expect(readLocationSelection("user-a")).toEqual({ mode: "AUTO" });
});

it("keeps the application usable when storage is blocked", () => {
  const get = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  const set = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
  expect(readLocationSelection("user-a")).toEqual({ mode: "AUTO" });
  expect(() => saveLocationSelection("user-a", { mode: "AUTO" })).not.toThrow();
  get.mockRestore(); set.mockRestore();
});
