import { describe, expect, it } from "vitest";
import { websiteOrigin } from "../config/config";
import { validatePaymentUrl } from "../native/paymentBrowser";

describe("test environment", () => {
  it("keeps native web handoffs in the selected environment", () => {
    const origin = websiteOrigin("https://api.test.prettylisavpn.com");
    const url = `${origin}/account/#handoff=${"a".repeat(43)}`;
    expect(validatePaymentUrl(url, [], origin)).toBe(url);
    expect(() => validatePaymentUrl(url, [])).toThrow();
    expect(() =>
      validatePaymentUrl(url.replace("test.", ""), [], origin),
    ).toThrow();
    expect(() =>
      validatePaymentUrl(`${url}&redirect=evil`, [], origin),
    ).toThrow();
    expect(validatePaymentUrl(`${origin}/account/`, [], origin)).toBe(
      `${origin}/account/`,
    );
  });
});
