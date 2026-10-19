import { useSyncExternalStore } from "react";
import catalog from "./catalog.json";
import { getLanguage, languagePreference, type Language } from "./language";
export { getLanguage, languagePreference, languages } from "./language";
export type { Language } from "./language";

export function useLanguage(): Language {
  return useSyncExternalStore(
    languagePreference.subscribe,
    getLanguage,
    getLanguage,
  );
}
const dictionaries: Record<Language, Record<string, string>> = catalog;
const templates = Object.keys(catalog.ru)
  .filter((key) => /\{\d+\}/.test(key))
  .map((key) => {
    const indices: string[] = [];
    const parts = key.split(/(\{\d+\})/g).map((part) => {
      if (/^\{\d+\}$/.test(part)) {
        indices.push(part);
        return "([\\s\\S]*?)";
      }
      return part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    });
    return { key, indices, pattern: new RegExp("^" + parts.join("") + "$") };
  });

// Presentation only: canonical error states stay intact, so already visible errors
// translate immediately. Technical names and unknown/user-authored data stay verbatim.
export function translate<T>(value: T, language: Language = getLanguage()): T {
  if (typeof value !== "string" || language === "ru") return value;
  const key = value.replace(/\s+/g, " ").trim();
  const dictionary = dictionaries[language];
  let result = Object.hasOwn(dictionary, key) ? dictionary[key] : undefined;
  if (!result) {
    for (const template of templates) {
      const match = template.pattern.exec(key);
      if (!match) continue;
      const replacements = new Map(
        template.indices.map((index, i) => [index, match[i + 1]]),
      );
      result = dictionary[template.key].replace(
        /\{\d+\}/g,
        (token) => replacements.get(token) ?? token,
      );
      break;
    }
  }
  if (!result) return value;
  return ((value.match(/^\s*/)?.[0] ?? "") +
    result +
    (value.match(/\s*$/)?.[0] ?? "")) as T;
}
export const t = translate;
