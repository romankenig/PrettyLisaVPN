import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import fixtures from "../../scripts/ci/billing-fixtures.json";
import { createApiClient } from "../api/client";
import { createBillingClient } from "../billing/client";
import { parseOverview, type BillingClient, type BillingOperation } from "../billing/model";
import { preferredCurrency, rememberHomeCountry, requestId, saveCurrency } from "../billing/preferences";
import { validatePaymentUrl } from "../native/paymentBrowser";
import { loadConfig } from "../config/config";
import { ApplicationProvider } from "../state/application";
import { Subscription } from "../ui/Subscription";
import { HomeCountryObserver } from "../ui/HomeCountryObserver";
import type { PublicLocation } from "../location/publicLocation";
import { createTestAuthenticationSession, createTestSessionRestoration, createTestVpnConnection } from "./fakes";

const pending: BillingOperation = { id: "fixture-operation", status: "PENDING", redirect_url: "https://payments.example.test/confirm" };
beforeEach(() => {
  localStorage.clear(); sessionStorage.clear();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
});
function setup(scenario: "free" | "active" | "canceled" = "free", country?: () => Promise<PublicLocation>) {
  const billing: BillingClient = {
    overview: vi.fn().mockResolvedValue(parseOverview(fixtures[scenario])),
    start: vi.fn().mockResolvedValue(pending),
    operation: vi.fn().mockResolvedValue(pending),
  };
  const open = vi.fn().mockResolvedValue(undefined);
  const vpnConnection = createTestVpnConnection();
  const session = createTestAuthenticationSession();
  session.activateRestored({ accessToken: "token", accessTokenExpiresIn: 900,
    sessionId: "123e4567-e89b-42d3-a456-426614174005", userId: "user",
    plan: "FREE", profile: null });
  const view = render(<ApplicationProvider value={{
    config: loadConfig({}), api: createApiClient("https://api.example.test", vi.fn(), 1000),
    billing, paymentBrowser: { open }, desktop: { getVersion: async () => "0.5.0" },
    installationId: { getInstallationId: vi.fn() }, session,
    sessionRestoration: createTestSessionRestoration(), vpnConnection,
    publicLocation: country ? { current: country } : undefined,
  }}><MemoryRouter>{country ? <HomeCountryObserver /> : null}<Subscription /></MemoryRouter></ApplicationProvider>);
  return { billing, open, session, vpnConnection, ...view };
}

describe("subscription screen", () => {
  it("loads backend prices, promotes RUB for the saved home country and preserves a manual choice", async () => {
    rememberHomeCountry("RU");
    const { billing } = setup();
    await screen.findByRole("button", { name: "оформить подписку" });
    expect(billing.overview).toHaveBeenCalledWith("token", expect.any(AbortSignal));
    expect(screen.getByRole("button", { name: "₽" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("цена в рублях").querySelector("del")).toHaveTextContent("299");
    expect(screen.getByLabelText("цена в долларах").querySelector("strong")).toHaveTextContent("2,99");
    fireEvent.click(screen.getByRole("button", { name: "$", exact: true }));
    rememberHomeCountry("RU");
    expect(screen.getByRole("button", { name: "$", exact: true })).toHaveAttribute("aria-pressed", "true");
    expect(preferredCurrency("user")).toBe("USD");
  });
  it("requires cancellation confirmation and keeps access until the backend confirms the result", async () => {
    const { billing } = setup("active");
    await screen.findByText("автопродление включено");
    fireEvent.click(screen.getByRole("button", { name: "отменить подписку" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("способ оплаты отвяжется");
    expect(billing.start).not.toHaveBeenCalled();
    vi.mocked(billing.overview).mockResolvedValue(parseOverview(fixtures.canceled));
    vi.mocked(billing.operation).mockResolvedValue({ ...pending, status: "SUCCEEDED", redirect_url: null });
    fireEvent.click(within(dialog).getByRole("button", { name: "да, отменить" }));
    await screen.findByText("автопродление отключено");
    expect(billing.start).toHaveBeenCalledWith("token", expect.objectContaining({ action: "CANCEL", offer_id: null }), expect.any(AbortSignal));
    expect(screen.getByText(/доступ до/)).toBeVisible();
    expect(screen.queryByText("тестовый способ •••• 4242")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "отменить подписку" })).not.toBeInTheDocument();
  });
  it("opens the provider once and does not treat redirect as payment success", async () => {
    const { billing, open } = setup();
    const button = await screen.findByRole("button", { name: "оформить подписку" });
    fireEvent.click(button); fireEvent.click(button);
    await waitFor(() => expect(open).toHaveBeenCalledWith(pending.redirect_url));
    expect(billing.start).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "оформить подписку" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("ожидаем подтверждения");
    expect(screen.queryByText("автопродление включено")).not.toBeInTheDocument();
  });
  it("shows unavailable data rather than invented prices after a backend failure", async () => {
    const { billing } = setup();
    await screen.findByRole("button", { name: "оформить подписку" });
    vi.mocked(billing.overview).mockRejectedValue(new Error("offline"));
    fireEvent.click(screen.getByRole("button", { name: "обновить" }));
    await screen.findByRole("alert");
    expect(screen.queryByLabelText("цена в рублях")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "оформить подписку" })).not.toBeInTheDocument();
  });
  it("reuses the same idempotency key after a timeout", () => {
    const a = requestId("user", "revision", "SUBSCRIBE", "offer", "RUB");
    expect(requestId("user", "revision", "SUBSCRIBE", "offer", "RUB")).toBe(a);
    expect(requestId("user", "next-revision", "SUBSCRIBE", "offer", "RUB")).not.toBe(a);
  });
  it("discards a country response if VPN state changed while it was in flight", async () => {
    let resolve!: (value: PublicLocation) => void;
    const { vpnConnection } = setup("free", () => new Promise(r => { resolve = r; }));
    vi.spyOn(vpnConnection, "current").mockReturnValue({ phase: "CONNECTING", backend: "UNKNOWN", tunnel: "UNKNOWN" });
    resolve({ ip: "203.0.113.42", countryCode: "RU", city: null });
    await screen.findByRole("button", { name: "оформить подписку" });
    expect(preferredCurrency("user")).toBe("USD");
  });
});

describe("billing contract and provider navigation", () => {
  it("rejects invalid discounts, prices and inconsistent cancellation", () => {
    const free = structuredClone(fixtures.free);
    free.offers[0].prices.RUB.original_amount_minor = 100;
    expect(() => parseOverview(free)).toThrow();
    expect(() => parseOverview({ ...fixtures.active, current_price: { amount_minor: -1, currency: "RUB" } })).toThrow();
    expect(() => parseOverview({ ...fixtures.canceled, auto_renew: true })).toThrow();
  });
  it("only permits exact configured HTTPS provider hosts", () => {
    const hosts = ["payments.example.test"];
    expect(validatePaymentUrl(pending.redirect_url!, hosts)).toBe(pending.redirect_url);
    for (const raw of ["javascript:alert(1)", "file:///tmp/file", "https://payments.example.test.evil.test/", "https://user:pass@payments.example.test/", "https://payments.example.test:8443/", "http://payments.example.test/"]) expect(() => validatePaymentUrl(raw, hosts)).toThrow();
    expect(() => validatePaymentUrl(pending.redirect_url!, [])).toThrow();
  });
  it("uses an authenticated backend request and sends only command IDs and currency", async () => {
    const transport = vi.fn().mockResolvedValue(new Response(JSON.stringify(fixtures.free)));
    const client = createBillingClient("https://api.example.test", transport, 1000);
    await client.overview("token", new AbortController().signal);
    expect(transport).toHaveBeenCalledWith("https://api.example.test/billing/overview", expect.objectContaining({ credentials: "omit", headers: expect.objectContaining({ authorization: "Bearer token" }) }));
  });
  it("uses USD for an unknown home country and remembers per-account choices", () => {
    expect(preferredCurrency("one")).toBe("USD");
    rememberHomeCountry("RU"); expect(preferredCurrency("one")).toBe("RUB");
    saveCurrency("one", "USD"); expect(preferredCurrency("one")).toBe("USD");
    expect(preferredCurrency("two")).toBe("RUB");
  });
});
