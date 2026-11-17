import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import fixtures from "../../scripts/ci/billing-fixtures.json";
import { ApiError, createApiClient } from "../api/client";
import { createBillingClient } from "../billing/client";
import {
  parseOverview,
  paymentMethodLabel,
  type BillingClient,
  type BillingOperation,
} from "../billing/model";
import {
  preferredCurrency,
  rememberHomeCountry,
  requestId,
  saveCurrency,
} from "../billing/preferences";
import { validatePaymentUrl } from "../native/paymentBrowser";
import { loadConfig } from "../config/config";
import { ApplicationProvider } from "../state/application";
import { Subscription } from "../ui/Subscription";
import { HomeCountryObserver } from "../ui/HomeCountryObserver";
import type { PublicLocation } from "../location/publicLocation";
import {
  createTestAuthenticationSession,
  createTestSessionRestoration,
  createTestVpnConnection,
} from "./fakes";

const portalUrl =
  "https://prettylisavpn.com/account/#handoff=" + "a".repeat(43);
const pending: BillingOperation = {
  id: "fixture-operation",
  status: "PENDING",
  redirect_url: "https://payments.example.test/confirm",
};
beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
});
function setup(
  scenario: "free" | "active" | "canceled" = "free",
  country?: () => Promise<PublicLocation>,
  overview: unknown = fixtures[scenario],
  portal: BillingClient["portal"] = vi.fn().mockResolvedValue(portalUrl),
) {
  const billing: BillingClient = {
    overview: vi.fn().mockResolvedValue(parseOverview(overview)),
    start: vi.fn().mockResolvedValue(pending),
    operation: vi.fn().mockResolvedValue(pending),
    portal,
  };
  const open = vi.fn().mockResolvedValue(undefined);
  const vpnConnection = createTestVpnConnection();
  const session = createTestAuthenticationSession();
  session.activateRestored({
    accessToken: "token",
    accessTokenExpiresIn: 900,
    sessionId: "123e4567-e89b-42d3-a456-426614174005",
    userId: "user",
    plan: "FREE",
    profile: {
      id: "user",
      email: "user@example.com",
      plan: "FREE",
      active_device_count: 1,
    },
  });
  const view = render(
    <ApplicationProvider
      value={{
        config: loadConfig({}),
        api: createApiClient("https://api.example.test", vi.fn(), 1000),
        billing,
        paymentBrowser: { open },
        desktop: { getVersion: async () => "0.6.0" },
        installationId: { getInstallationId: vi.fn() },
        session,
        sessionRestoration: createTestSessionRestoration(),
        vpnConnection,
        publicLocation: country ? { current: country } : undefined,
      }}
    >
      <MemoryRouter>
        {country ? <HomeCountryObserver /> : null}
        <Subscription />
      </MemoryRouter>
    </ApplicationProvider>,
  );
  return { billing, open, session, vpnConnection, ...view };
}

function overview(scenario: "free" | "active" | "canceled" = "free") {
  return {
    ...fixtures[scenario],
    payment_operations_available: false,
    actions: [],
    pending_operation_id: null,
    current_price: null,
    payment_method: null,
  };
}

describe("billing display and legacy wire contracts", () => {
  it("labels manual Platinum access even when the API retains an earlier contract price", async () => {
    setup("canceled", undefined, { ...fixtures.canceled, plan: "PLATINUM" });
    expect(await screen.findByText("тариф назначен вручную")).toBeVisible();
    expect(screen.getByRole("button", { name: "купить" })).toBeVisible();
    expect(
      screen.getByRole("region", { name: "тариф и стоимость" }),
    ).toHaveTextContent("299 ₽ / месяц");
  });
  it("ends an invalid native session instead of opening a billing portal", async () => {
    const { open, session } = setup(
      "free",
      undefined,
      { ...fixtures.free, provider_mode: "DISABLED", actions: [] },
      vi.fn().mockRejectedValue(new ApiError("AUTH_INVALID")),
    );
    fireEvent.click(
      await screen.findByRole("button", {
        name: "купить",
      }),
    );
    await waitFor(() => expect(session.current()).toBeNull());
    expect(open).not.toHaveBeenCalled();
  });
  it("reloads verified billing when returning from the external portal", async () => {
    const { billing, open } = setup(
      "free",
      undefined,
      { ...fixtures.free, provider_mode: "DISABLED", actions: [] },
      vi
        .fn()
        .mockResolvedValue(
          "https://prettylisavpn.com/account/#handoff=" + "a".repeat(43),
        ),
    );
    fireEvent.click(
      await screen.findByRole("button", {
        name: "купить",
      }),
    );
    await waitFor(() => expect(open).toHaveBeenCalled());
    vi.mocked(billing.overview).mockResolvedValue(
      parseOverview(fixtures.active),
    );
    fireEvent.focus(window);
    await waitFor(() => expect(billing.overview).toHaveBeenCalledTimes(2));
    fireEvent.focus(window);
    await waitFor(() => expect(billing.overview).toHaveBeenCalledTimes(3));
    expect(billing.start).not.toHaveBeenCalled();
  });
  it("offers a new purchase after cancellation while paid access remains", async () => {
    rememberHomeCountry("RU");
    setup("canceled", undefined, {
      ...fixtures.canceled,
      new_contract_required: true,
      actions: ["SUBSCRIBE"],
    });
    expect(await screen.findByRole("button", { name: "купить" })).toBeEnabled();
    expect(
      screen.queryByRole("button", { name: "продлить подписку" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/списаний больше не будет/)).toBeInTheDocument();
  });
  it("rejects raw card numbers and contradictory charge schedules", () => {
    expect(() =>
      parseOverview({
        ...fixtures.active,
        payment_method: { provider: "test", label: "4242 4242 4242 4242" },
      }),
    ).toThrow();
    expect(() =>
      parseOverview({
        ...fixtures.active,
        next_charge_at: "2026-12-06T10:00:00Z",
        next_charge_price: { amount_minor: 1, currency: "RUB" },
      }),
    ).toThrow();
    expect(
      paymentMethodLabel({
        provider: "test",
        label: "ignored",
        kind: "CARD",
        card_brand: "mir",
        card_last4: "1234",
      }),
    ).toBe("МИР •••• 1234");
  });
  it("loads backend prices, promotes RUB for the saved home country and preserves a manual choice", async () => {
    rememberHomeCountry("RU");
    const { billing } = setup();
    await screen.findByRole("button", { name: "купить" });
    expect(billing.overview).toHaveBeenCalledWith(
      "token",
      expect.any(AbortSignal),
    );
    expect(screen.getByRole("button", { name: "RUB" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(
      screen.getByLabelText("цена в рублях").querySelector("del"),
    ).toHaveTextContent("299");
    fireEvent.click(screen.getByRole("button", { name: "USD" }));
    expect(
      screen.getByLabelText("цена в долларах").querySelector("strong"),
    ).toHaveTextContent("2,99");
    fireEvent.click(screen.getByRole("button", { name: "USD" }));
    rememberHomeCountry("RU");
    expect(screen.getByRole("button", { name: "USD" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(preferredCurrency("user")).toBe("USD");
  });
  it("includes the payment route in the idempotent request fingerprint", () => {
    const a = requestId("user", "revision", "SUBSCRIBE", "offer", "RUB", "MIR");
    expect(
      requestId("user", "revision", "SUBSCRIBE", "offer", "RUB", "MIR"),
    ).toBe(a);
    expect(
      requestId("user", "revision", "SUBSCRIBE", "offer", "RUB", "CRYPTO"),
    ).not.toBe(a);
  });
  it("shows reference prices without checkout authority after a backend failure", async () => {
    const { billing } = setup();
    await screen.findByRole("button", { name: "купить" });
    vi.mocked(billing.overview).mockRejectedValue(new Error("offline"));
    fireEvent.click(screen.getByRole("button", { name: "обновить подписку" }));
    await screen.findByRole("alert");
    expect(screen.getByRole("button", { name: "купить" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "RUB" }));
    expect(screen.getByLabelText("цена в рублях")).toHaveTextContent("399");
    fireEvent.click(screen.getByRole("button", { name: "USD" }));
    expect(screen.getByLabelText("цена в долларах")).toHaveTextContent("5");
    fireEvent.click(screen.getByRole("button", { name: "купить" }));
    expect(billing.start).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it("reuses the same idempotency key after a timeout", () => {
    const a = requestId("user", "revision", "SUBSCRIBE", "offer", "RUB");
    expect(requestId("user", "revision", "SUBSCRIBE", "offer", "RUB")).toBe(a);
    expect(
      requestId("user", "next-revision", "SUBSCRIBE", "offer", "RUB"),
    ).not.toBe(a);
  });
  it("discards a country response if VPN state changed while it was in flight", async () => {
    let resolve!: (value: PublicLocation) => void;
    const { vpnConnection } = setup(
      "free",
      () =>
        new Promise((r) => {
          resolve = r;
        }),
    );
    vi.spyOn(vpnConnection, "current").mockReturnValue({
      phase: "CONNECTING",
      backend: "UNKNOWN",
      tunnel: "UNKNOWN",
    });
    resolve({ ip: "203.0.113.42", countryCode: "RU", city: null });
    await screen.findByRole("button", { name: "купить" });
    expect(preferredCurrency("user")).toBe("USD");
  });
  it("rejects invalid discounts, prices and inconsistent cancellation", () => {
    const free = structuredClone(fixtures.free);
    free.offers[0].prices.RUB.original_amount_minor = 100;
    expect(() => parseOverview(free)).toThrow();
    expect(() =>
      parseOverview({
        ...fixtures.active,
        current_price: { amount_minor: -1, currency: "RUB" },
      }),
    ).toThrow();
    expect(() =>
      parseOverview({ ...fixtures.canceled, auto_renew: true }),
    ).toThrow();
  });
  it("only permits exact configured HTTPS provider hosts", () => {
    const hosts = ["payments.example.test"];
    expect(validatePaymentUrl(pending.redirect_url!, hosts)).toBe(
      pending.redirect_url,
    );
    for (const raw of [
      "javascript:alert(1)",
      "file:///tmp/file",
      "https://payments.example.test.evil.test/",
      "https://user:pass@payments.example.test/",
      "https://payments.example.test:8443/",
      "http://payments.example.test/",
    ])
      expect(() => validatePaymentUrl(raw, hosts)).toThrow();
    expect(() => validatePaymentUrl(pending.redirect_url!, [])).toThrow();
  });
  it("uses an authenticated backend request and sends only command IDs and currency", async () => {
    const transport = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(fixtures.free)));
    const client = createBillingClient(
      "https://api.example.test",
      transport,
      1000,
    );
    await client.overview("token", new AbortController().signal);
    expect(transport).toHaveBeenCalledWith(
      "https://api.example.test/billing/overview",
      expect.objectContaining({
        credentials: "omit",
        headers: expect.objectContaining({ authorization: "Bearer token" }),
      }),
    );
  });
  it("uses USD for an unknown home country and remembers per-account choices", () => {
    expect(preferredCurrency("one")).toBe("USD");
    rememberHomeCountry("RU");
    expect(preferredCurrency("one")).toBe("RUB");
    saveCurrency("one", "USD");
    expect(preferredCurrency("one")).toBe("USD");
    expect(preferredCurrency("two")).toBe("RUB");
  });
  it("opens only the authenticated fixed portal and never accepts an arbitrary redirect", async () => {
    const url = "https://prettylisavpn.com/account/#handoff=" + "a".repeat(43);
    expect(validatePaymentUrl(url, [])).toBe(url);
    for (const invalid of [
      url.replace(".com", ".com.evil.test"),
      url.replace("#", "?"),
      url + "&redirect=evil",
    ])
      expect(() => validatePaymentUrl(invalid, [])).toThrow(
        "PAYMENT_URL_NOT_ALLOWED",
      );
    const transport = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ url })));
    const client = createBillingClient(
      "https://api.example.test",
      transport,
      1000,
    );
    expect(await client.portal!("token", new AbortController().signal)).toBe(
      url,
    );
    expect(transport).toHaveBeenCalledWith(
      "https://api.example.test/billing/portal",
      expect.objectContaining({ method: "POST", credentials: "omit" }),
    );
    transport.mockResolvedValue(
      new Response(
        JSON.stringify({ url: url.replace(".com", ".com.evil.test") }),
      ),
    );
    await expect(
      client.portal!("token", new AbortController().signal),
    ).rejects.toThrow("PAYMENT_URL_NOT_ALLOWED");
  });
  it("preserves an expired subscription's actual renewal flag without granting paid access", () => {
    expect(
      parseOverview({ ...overview("active"), plan: "FREE", status: "EXPIRED" })
        .auto_renew,
    ).toBe(true);
    expect(() =>
      parseOverview({ ...overview(), actions: ["SUBSCRIBE"] }),
    ).toThrow();
    expect(() =>
      parseOverview({ ...overview(), pending_operation_id: "old" }),
    ).toThrow();
  });
  it.each([
    { provider_mode: "UNKNOWN" },
    { provider_mode: ["LIVE"] },
    { payment_routes: [] },
    {
      payment_routes: [
        ...fixtures.free.payment_routes,
        fixtures.free.payment_routes[0],
      ],
    },
    {
      payment_routes: fixtures.free.payment_routes.map((cap) => ({
        ...cap,
        id: "MIR",
      })),
    },
    {
      payment_routes: fixtures.free.payment_routes.map((cap) => ({
        ...cap,
        currencies: ["EUR"],
      })),
    },
    {
      payment_routes: fixtures.free.payment_routes.map((cap) => ({
        ...cap,
        currencies: ["RUB"],
        recurring_currencies: ["USD"],
      })),
    },
    {
      payment_routes: fixtures.free.payment_routes.map((cap) => ({
        ...cap,
        recurring_currencies: ["USD"],
      })),
    },
  ])("rejects malformed or contradictory capability metadata %#", (change) => {
    expect(() => parseOverview({ ...fixtures.free, ...change })).toThrow();
  });
});

describe("website-owned payment flow", () => {
  it.each(["LIVE", "SANDBOX", "DISABLED"])(
    "opens the website for %s without a native charge or method selector",
    async (mode) => {
      const { billing, open } = setup("free", undefined, {
        ...fixtures.free,
        provider_mode: mode,
      });
      fireEvent.click(await screen.findByRole("button", { name: "купить" }));
      await waitFor(() => expect(open).toHaveBeenCalledWith(portalUrl));
      expect(billing.start).not.toHaveBeenCalled();
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    },
  );
  it("keeps website purchase available when operations and offers are absent", async () => {
    const { billing, open } = setup("free", undefined, {
      ...fixtures.free,
      provider_mode: "DISABLED",
      payment_operations_available: false,
      actions: [],
      offers: [],
    });
    fireEvent.click(await screen.findByRole("button", { name: "купить" }));
    await waitFor(() => expect(open).toHaveBeenCalledWith(portalUrl));
    expect(billing.start).not.toHaveBeenCalled();
  });
  it("opens the website for renewal and management even when no route supports the display currency", async () => {
    const { billing, open } = setup("active", undefined, {
      ...fixtures.sbp,
      provider_mode: "DISABLED",
      actions: [],
      payment_routes: fixtures.sbp.payment_routes.map((route) => ({
        ...route,
        currencies: [],
        recurring_currencies: [],
      })),
    });
    fireEvent.click(
      await screen.findByRole("button", { name: "продлить подписку" }),
    );
    await waitFor(() => expect(open).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "изменить подписку" }));
    await waitFor(() => expect(open).toHaveBeenCalledTimes(2));
    expect(open).toHaveBeenLastCalledWith(portalUrl);
    expect(billing.start).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("button", { name: "отменить подписку" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "изменить способ оплаты" }),
    ).not.toBeInTheDocument();
  });
  it("keeps an existing pending operation readable and opens its website without reissuing it", async () => {
    const { billing, open } = setup("free", undefined, {
      ...fixtures.free,
      pending_operation_id: pending.id,
    });
    await waitFor(() => expect(billing.operation).toHaveBeenCalled());
    fireEvent.click(
      screen.getByRole("button", { name: "управлять подпиской и оплатой" }),
    );
    await waitFor(() => expect(open).toHaveBeenCalledWith(portalUrl));
    expect(billing.start).not.toHaveBeenCalled();
    expect(open).not.toHaveBeenCalledWith(pending.redirect_url);
  });
  it("retries a failed portal request without falling back to a native payment", async () => {
    const portal = vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue(portalUrl);
    const { billing, open } = setup("free", undefined, fixtures.free, portal);
    fireEvent.click(await screen.findByRole("button", { name: "купить" }));
    await screen.findByRole("alert");
    expect(open).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "купить" }));
    await waitFor(() => expect(open).toHaveBeenCalledWith(portalUrl));
    expect(billing.start).not.toHaveBeenCalled();
  });
  it("does not open a stale account handoff after the user leaves", async () => {
    let finish!: (url: string) => void;
    const portal = vi.fn(
      () =>
        new Promise<string>((resolve) => {
          finish = resolve;
        }),
    );
    const { open, unmount } = setup("free", undefined, fixtures.free, portal);
    fireEvent.click(await screen.findByRole("button", { name: "купить" }));
    await waitFor(() => expect(portal).toHaveBeenCalledOnce());
    unmount();
    finish(portalUrl);
    await Promise.resolve();
    expect(open).not.toHaveBeenCalled();
  });
  it("allows only the exact public account entry for DEMO", () => {
    expect(validatePaymentUrl("https://prettylisavpn.com/account/", [])).toBe(
      "https://prettylisavpn.com/account/",
    );
    for (const url of [
      "http://prettylisavpn.com/account/",
      "https://prettylisavpn.com.evil.test/account/",
      "https://prettylisavpn.com/account/?next=https://evil.test",
      "https://prettylisavpn.com/account/#token=secret",
      "https://user@prettylisavpn.com/account/",
    ])
      expect(() => validatePaymentUrl(url, [])).toThrow();
  });
});
