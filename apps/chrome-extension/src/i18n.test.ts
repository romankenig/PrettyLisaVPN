import { describe, expect, it } from "vitest";
import {
  labels,
  languages,
  translate,
  publicUrl,
  legalKeys,
  languageCode,
} from "./i18n";

describe("six complete client languages", () => {
  it("keeps every screen/error translated and preserves the brand", () => {
    expect(languages.map((item) => item.code).sort()).toEqual([
      "de",
      "en",
      "es",
      "fr",
      "ru",
      "zh",
    ]);
    for (const values of Object.values(labels)) {
      expect(values).toHaveLength(languages.length);
      expect(values.every((value) => value.trim().length > 0)).toBe(true);
    }
    for (const language of languages)
      expect(translate("website", language.code)).toContain("PrettyLisaVPN");
    expect(languageCode("en")).toBe("en");
    expect(languageCode("bad")).toBe("ru");
  });
  it("opens only localized public documents without account data", () => {
    for (const { code } of languages)
      for (const key of legalKeys) {
        const url = new URL(publicUrl(code, key));
        expect(url.origin).toBe("https://prettylisavpn.com");
        expect(url.pathname).toBe(
          (code === "ru" ? "" : "/" + code) + "/legal/" + key + "/",
        );
        expect(url.search + url.hash).toBe("");
      }
  });
});
