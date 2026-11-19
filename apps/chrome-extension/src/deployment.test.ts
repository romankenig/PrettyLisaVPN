import { expect, it } from "vitest";
import { deployment } from "./deployment";

it("pairs only the two supported API and website origins", () => {
  expect(deployment("https://api.test.prettylisavpn.com").website).toBe(
    "https://test.prettylisavpn.com",
  );
  expect(deployment("https://api.prettylisavpn.com").website).toBe(
    "https://prettylisavpn.com",
  );
  for (const value of [
    "http://api.test.prettylisavpn.com",
    "https://api.prettylisavpn.com.evil.test",
    "https://api.test.prettylisavpn.com/other",
  ]) {
    expect(() => deployment(value)).toThrow();
  }
});
