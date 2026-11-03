export const languages = ["ru", "en", "de", "fr", "es", "zh"];
export const legalKeys = ["terms", "privacy", "refunds", "payments"];
export const platforms = [
  { id: "android", file: "android.apk", stores: ["google", "rustore"] },
  { id: "windows", file: "windows.exe", stores: ["microsoft"] },
  { id: "ios", stores: ["apple"] },
  { id: "macos", stores: ["apple"] },
  { id: "linux", stores: ["flathub"] },
  { id: "android-tv", stores: ["google"] },
  { id: "chrome", stores: ["chrome"] },
];
export function routeFor(language, route = "/") {
  if (!languages.includes(language)) throw new Error("Unknown language");
  return (language === "ru" ? "" : `/${language}`) + route;
}
