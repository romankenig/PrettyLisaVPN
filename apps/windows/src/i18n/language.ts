export const languages = [
  { code: "zh", country: "CN", english: "Chinese", native: "中文" },
  { code: "en", country: "GB", english: "English", native: "English" },
  { code: "fr", country: "FR", english: "French", native: "Français" },
  { code: "de", country: "DE", english: "German", native: "Deutsch" },
  { code: "ru", country: "RU", english: "Russian", native: "Русский" },
  { code: "es", country: "ES", english: "Spanish", native: "Español" },
] as const;
export type Language = (typeof languages)[number]["code"];
export const LANGUAGE_KEY = "prettylisavpn:language";
export function isLanguage(value: unknown): value is Language {
  return languages.some((language) => language.code === value);
}

// Only an explicit choice is persisted. Egress location is never a language preference.
export function createLanguagePreference(
  storage: Pick<Storage, "getItem" | "setItem"> | null,
) {
  let manual = false;
  let language: Language = "en";
  try {
    const saved = storage?.getItem(LANGUAGE_KEY);
    if (isLanguage(saved)) {
      language = saved;
      manual = true;
    }
  } catch {
    /* Optional local preference; English still works offline. */
  }
  const listeners = new Set<() => void>();
  const update = (next: Language) => {
    if (next === language) return;
    language = next;
    listeners.forEach((listener) => listener());
  };
  return {
    current: () => language,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    choose(next: Language) {
      manual = true;
      try {
        storage?.setItem(LANGUAGE_KEY, next);
      } catch {
        /* Keep the choice in memory. */
      }
      update(next);
    },
    suggestCountry(country: string | null) {
      if (!manual) update(country === "RU" ? "ru" : "en");
    },
  };
}
function preferenceStorage(): Storage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}
export const languagePreference = createLanguagePreference(preferenceStorage());
export const getLanguage = languagePreference.current;
