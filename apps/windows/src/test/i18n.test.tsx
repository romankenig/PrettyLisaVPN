import { act, fireEvent, render, screen, within, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import catalog from "../i18n/catalog.json";
import { t, translate, languagePreference, languages } from "../i18n";
import { createLanguagePreference, LANGUAGE_KEY } from "../i18n/language";
import { LanguageSelector } from "../ui/LanguageSelector";
import { Login } from "../ui/Login";
import { MemoryRouter } from "react-router-dom";
import { ApplicationProvider } from "../state/application";
import { loadConfig } from "../config/config";
import { createApiClient } from "../api/client";
import { createTestAuthenticationSession, createTestSessionRestoration, createTestVpnConnection } from "./fakes";

function storage(initial: string | null = null) {
  let value = initial;
  return { getItem: () => value, setItem: (_key: string, next: string) => { value = next; } };
}
describe("language preferences and catalogs", () => {
  it("starts English offline, detects Russia, and restores explicit choices", () => {
    const disk = storage();
    const preference = createLanguagePreference(disk);
    expect(preference.current()).toBe("en");
    preference.suggestCountry(null); expect(preference.current()).toBe("en");
    preference.suggestCountry("RU"); expect(preference.current()).toBe("ru");
    preference.choose("en"); preference.suggestCountry("RU");
    expect(preference.current()).toBe("en");
    expect(createLanguagePreference(disk).current()).toBe("en");
    expect(createLanguagePreference(storage("invalid")).current()).toBe("en");
    expect(createLanguagePreference(storage("zh")).current()).toBe("zh");
  });
  it("keeps manual choice when storage fails or a late country result arrives", () => {
    const preference = createLanguagePreference({getItem: () => {throw new Error();},setItem: () => {throw new Error();}});
    preference.choose("fr"); preference.suggestCountry("RU");
    expect(preference.current()).toBe("fr");
  });
  it("has complete translations and identical interpolation parameters", () => {
    const keys = Object.keys(catalog.ru).sort();
    for (const dictionary of Object.values(catalog)) {
      expect(Object.keys(dictionary).sort()).toEqual(keys);
      for (const [source, target] of Object.entries(dictionary)) {
        expect(target.trim()).not.toBe("");
        expect(target.match(/\{\d+\}/g) ?? []).toEqual(source.match(/\{\d+\}/g) ?? []);
      }
    }
    for (const language of languages) {
      expect(translate("PrettyLisaVPN", language.code)).toBe("PrettyLisaVPN");
      expect(translate("WireGuard · UDP · Connected", language.code)).toBe("WireGuard · UDP · Connected");
      expect(translate("constructor", language.code)).toBe("constructor");
    }
    expect(translate("отправить повторно через 23 с", "en")).toBe("resend in 23 s");
    expect(translate("Доступ устройства «My device» отозван.", "fr")).toContain("My device");
  });
  it("orders English names and supports keyboard selection, Escape and click-away", () => {
    render(<LanguageSelector />);
    const trigger = screen.getByRole("combobox");
    fireEvent.keyDown(trigger, {key:"Home"});
    expect(within(screen.getByRole("listbox")).getAllByRole("option").map(x=>x.textContent?.replace("✓", ""))).toEqual(languages.map(x=>x.english+x.native));
    fireEvent.keyDown(trigger, {key:"Enter"});
    expect(languagePreference.current()).toBe("zh");
    expect(localStorage.getItem(LANGUAGE_KEY)).toBe("zh");
    expect(document.documentElement.lang).toBe("zh");
    fireEvent.click(trigger); fireEvent.keyDown(trigger, {key:"Escape"});
    expect(screen.queryByRole("listbox")).toBeNull();
    fireEvent.click(trigger); fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("listbox")).toBeNull();
  });
  it("updates an already visible validation error without losing input", () => {
    render(<ApplicationProvider value={{config:loadConfig({}),api:createApiClient("https://example.invalid", async () => new Response("{}", {status:500}), 1000),desktop:{getVersion:async()=>"0.12.0"},installationId:{getInstallationId:async()=>{throw new Error();}},session:createTestAuthenticationSession(),sessionRestoration:createTestSessionRestoration(),vpnConnection:createTestVpnConnection()}}><MemoryRouter><Login /></MemoryRouter></ApplicationProvider>);
    fireEvent.change(screen.getByLabelText("Email"),{target:{value:"bad-address"}});
    fireEvent.click(screen.getByRole("button",{name:"продолжить"}));
    expect(screen.getByRole("alert")).toHaveTextContent("Введите корректный email.");
    act(()=>languagePreference.choose("de"));
    expect(screen.getByRole("alert")).toHaveTextContent("Gib eine gültige email ein.");
    expect(screen.getByLabelText("Email")).toHaveValue("bad-address");
    expect(t("продолжить")).toBe("weiter");
  });
});

it("uses fresh DOWN probes and ignores a location reply after VPN starts", async () => {
  const { HomeCountryObserver } = await import("../ui/HomeCountryObserver");
  const { languagePreference } = await import("../i18n/language");
  const suggest = vi.spyOn(languagePreference, "suggestCountry");
  let state: import("../vpn/connection").VpnConnectionState = {phase:"RECONCILING",backend:"UNKNOWN",tunnel:"UNKNOWN"};
  const listeners = new Set<() => void>();
  const probe = vi.fn().mockResolvedValue("UP");
  let finish!: (data: import("../location/publicLocation").PublicLocation) => void;
  const location = vi.fn().mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const manager: import("../vpn/connection").VpnConnectionManager = {
    ...createTestVpnConnection(), current: () => state, localTunnelStatus: probe,
    subscribe: listener => {listeners.add(listener);return () => {listeners.delete(listener);};},
  };
  render(<ApplicationProvider value={{config:loadConfig({}),api:createApiClient("https://example.invalid",async()=>new Response("{}"),1000),desktop:{getVersion:async()=>"0.12.0"},installationId:{getInstallationId:async()=>{throw new Error();}},session:createTestAuthenticationSession(),sessionRestoration:createTestSessionRestoration(),vpnConnection:manager,publicLocation:{current:location}}}><HomeCountryObserver /></ApplicationProvider>);
  await waitFor(() => expect(probe).toHaveBeenCalled());
  expect(location).not.toHaveBeenCalled();
  probe.mockResolvedValue("DOWN");
  fireEvent.focus(window);
  await waitFor(() => expect(location).toHaveBeenCalledOnce());
  act(() => {state={phase:"CONNECTING",backend:"UNKNOWN",tunnel:"UNKNOWN"};listeners.forEach(fn=>fn());});
  await act(async()=>finish({ip:"203.0.113.1",countryCode:"RU",city:null}));
  expect(suggest).not.toHaveBeenCalled();
  location.mockResolvedValue({ip:"203.0.113.1",countryCode:"RU",city:null});
  act(() => {state={phase:"DISCONNECTED",backend:"NONE",tunnel:"DOWN"};listeners.forEach(fn=>fn());});
  await waitFor(() => expect(suggest).toHaveBeenCalledWith("RU"));
  suggest.mockRestore();
});
