import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import fixtures from "../../scripts/ci/billing-fixtures.json";
import { ApiError, createApiClient } from "../api/client";
import { createBillingClient } from "../billing/client";
import {
  parseOverview,
  paymentsEnabled,
  paymentMethodLabel,
  type BillingClient,
  type BillingOperation,
} from "../billing/model";
import {
  preferredCurrency,
  rememberHomeCountry,
  requestId,
  saveCurrency,
  savePendingOperation,
  pendingOperation,
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
  portal?: BillingClient["portal"],
) {
  const billing: BillingClient = {
    overview: vi.fn().mockResolvedValue(parseOverview(overview)),
    start: vi.fn().mockResolvedValue(pending),
    operation: vi.fn().mockResolvedValue(pending),
    ...(portal ? { portal } : {}),
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

async function openPaymentChoice(name = "купить") {
  fireEvent.click(await screen.findByRole("button", { name }));
  return screen.getByRole("dialog");
}

describe("subscription screen", () => {
  it("labels manual Platinum access even when the API retains an earlier contract price", async () => {
    setup("canceled", undefined, { ...fixtures.canceled, plan: "PLATINUM" });
    expect(await screen.findByText("тариф назначен вручную")).toBeVisible();
    expect(
      screen.getByRole("region", { name: "тариф и стоимость" }),
    ).toHaveTextContent("299 ₽ / месяц");
  });
  it("shows the SBP schedule without unsupported manual renewal", async () => {
    setup("active", undefined, fixtures.sbp);
    expect(
      await screen.findByText("СБП · привязанный банковский счёт"),
    ).toBeVisible();
    expect(screen.getByText(/следующее списание/)).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "продлить подписку" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "изменить способ оплаты" }),
    ).not.toBeInTheDocument();
  });
  it("opens the account portal without starting a charge in the client", async () => {
    const url = "https://prettylisavpn.com/account/#handoff=" + "a".repeat(43);
    const portal = vi.fn().mockResolvedValue(url);
    const { open, billing } = setup(
      "free",
      undefined,
      { ...fixtures.free, provider_mode: "DISABLED", actions: [] },
      portal,
    );
    fireEvent.click(
      await screen.findByRole("button", {
        name: "купить",
      }),
    );
    await waitFor(() => expect(open).toHaveBeenCalledWith(url));
    expect(portal).toHaveBeenCalledWith("token", expect.any(AbortSignal));
    expect(billing.start).not.toHaveBeenCalled();
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
  it("shows verified card summary and the authoritative next payment", async () => {
    const value = {
      ...fixtures.active,
      next_charge_at: "2026-12-06T10:00:00Z",
      next_charge_price: fixtures.active.current_price,
      new_contract_required: false,
      payment_method: {
        provider: "test",
        label: "Visa •••• 4242",
        kind: "CARD",
        card_brand: "visa",
        card_last4: "4242",
      },
    };
    setup("active", undefined, value);
    await screen.findByText("Visa •••• 4242");
    expect(
      screen.getByText(/следующее списание/).parentElement,
    ).toHaveTextContent("6 декабря 2026");
    expect(screen.getByText(/цена закреплена/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "отменить подписку" }));
    expect(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "заменить карту",
      }),
    ).toBeInTheDocument();
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
  it("requires cancellation confirmation and keeps access until the backend confirms the result", async () => {
    const { billing } = setup("active");
    await screen.findByText("автопродление включено");
    fireEvent.click(screen.getByRole("button", { name: "отменить подписку" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("способ оплаты отвяжется");
    expect(billing.start).not.toHaveBeenCalled();
    vi.mocked(billing.overview).mockResolvedValue(
      parseOverview(fixtures.canceled),
    );
    vi.mocked(billing.operation).mockResolvedValue({
      ...pending,
      status: "SUCCEEDED",
      redirect_url: null,
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "да, отменить" }),
    );
    await screen.findByText("автопродление отключено");
    expect(billing.start).toHaveBeenCalledWith(
      "token",
      expect.objectContaining({ action: "CANCEL", offer_id: null }),
      expect.any(AbortSignal),
    );
    expect(screen.getByText(/доступ до/)).toBeVisible();
    expect(
      screen.queryByText("тестовый способ •••• 4242"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "отменить подписку" }),
    ).not.toBeInTheDocument();
  });
  it("opens the provider once and does not treat redirect as payment success", async () => {
    const { billing, open } = setup();
    const button = await screen.findByRole("button", {
      name: "купить",
    });
    fireEvent.click(button);
    expect(billing.start).not.toHaveBeenCalled();
    const confirm = screen.getByRole("button", { name: "перейти к оплате" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    await waitFor(() =>
      expect(open).toHaveBeenCalledWith(pending.redirect_url),
    );
    expect(billing.start).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "купить" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "ожидаем подтверждения",
    );
    expect(
      screen.queryByText("автопродление включено"),
    ).not.toBeInTheDocument();
  });

  it("preselects MIR for RUB and can go back without a request", async () => {
    rememberHomeCountry("RU");
    const { billing, open } = setup();
    const dialog = await openPaymentChoice();
    const options = within(dialog).getAllByRole("radio");
    expect(options).toHaveLength(4);
    expect(options[0]).toHaveAttribute("value", "MIR");
    expect(options[0]).toBeChecked();
    expect(dialog.querySelectorAll("svg")).toHaveLength(4);
    expect(dialog).toHaveTextContent(
      "Visa · Mastercard · UnionPay · American Express",
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "назад" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(billing.start).not.toHaveBeenCalled();
    expect(open).not.toHaveBeenCalled();
  });
  it("prefers bank cards for manually selected USD even in Russia", async () => {
    rememberHomeCountry("RU");
    saveCurrency("user", "USD");
    const { billing } = setup("active", undefined, {
      ...fixtures.active,
      current_price: { amount_minor: 399, currency: "USD" },
      payment_routes: fixtures.free.payment_routes.map((cap) => ({
        ...cap,
        currencies: cap.currencies.filter((code) => code === "USD"),
        recurring_currencies: cap.recurring_currencies.filter(
          (code) => code === "USD",
        ),
      })),
    });
    await openPaymentChoice("продлить подписку");
    const options = screen.getAllByRole("radio");
    expect(options[0]).toHaveAttribute("value", "BANK_CARD");
    expect(options[0]).toBeChecked();
    expect(billing.start).not.toHaveBeenCalled();
    fireEvent.click(screen.getByDisplayValue("ALIPAY_WECHAT"));
    fireEvent.click(screen.getByRole("button", { name: "перейти к оплате" }));
    await waitFor(() =>
      expect(billing.start).toHaveBeenCalledWith(
        "token",
        expect.objectContaining({
          action: "RENEW",
          payment_route: "ALIPAY_WECHAT",
          currency: "USD",
        }),
        expect.any(AbortSignal),
      ),
    );
  });
  const routes = ["MIR", "BANK_CARD", "ALIPAY_WECHAT", "CRYPTO"] as const;
  for (const route of routes) {
    it(`submits ${route} only after explicit confirmation`, async () => {
      saveCurrency("user", route === "MIR" ? "RUB" : "USD");
      const { billing, open } = setup();
      await openPaymentChoice();
      fireEvent.click(screen.getByDisplayValue(route));
      expect(billing.start).not.toHaveBeenCalled();
      expect(open).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole("button", { name: "перейти к оплате" }));
      await waitFor(() =>
        expect(billing.start).toHaveBeenCalledWith(
          "token",
          expect.objectContaining({
            action: "SUBSCRIBE",
            payment_route: route,
          }),
          expect.any(AbortSignal),
        ),
      );
    });
  }
  it("preserves the quoted currency while the choice is open", async () => {
    const { billing } = setup();
    await openPaymentChoice();
    act(() => rememberHomeCountry("RU"));
    fireEvent.click(screen.getByRole("button", { name: "перейти к оплате" }));
    await waitFor(() =>
      expect(billing.start).toHaveBeenCalledWith(
        "token",
        expect.objectContaining({
          currency: "USD",
          payment_route: "BANK_CARD",
        }),
        expect.any(AbortSignal),
      ),
    );
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
});

describe("billing contract and provider navigation", () => {
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
});

describe("read-only server billing", () => {
  it("keeps an expired contract on renewal and offers a new contract to manual Platinum", async () => {
    const view = setup("free", undefined, {
      ...fixtures.active,
      plan: "FREE",
      status: "EXPIRED",
      actions: [],
      payment_operations_available: false,
      provider_mode: "DISABLED",
      new_contract_required: false,
    });
    await screen.findByText(/оплата пока недоступна/);
    fireEvent.click(screen.getByRole("button", { name: "продлить подписку" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "купить" }),
    ).not.toBeInTheDocument();
    view.unmount();
    setup("free", undefined, {
      ...fixtures.free,
      plan: "PLATINUM",
      status: "ACTIVE",
      paid_until: fixtures.active.paid_until,
      actions: [],
      payment_operations_available: false,
      provider_mode: "DISABLED",
      new_contract_required: true,
    });
    await screen.findByText(/оплата пока недоступна/);
    expect(screen.getByRole("button", { name: "купить" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "RUB" }));
    expect(screen.getByLabelText("цена в рублях")).toHaveTextContent("199");
  });
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
  it("displays server prices but never starts payment, polls a stale operation or opens a provider", async () => {
    savePendingOperation("user", "legacy-operation");
    const { billing, open } = setup("free", undefined, overview());
    await screen.findByText(/оплата пока недоступна/);
    const subscribe = screen.getByRole("button", { name: "купить" });
    expect(subscribe).toBeEnabled();
    fireEvent.click(subscribe);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(billing.start).not.toHaveBeenCalled();
    expect(billing.operation).not.toHaveBeenCalled();
    expect(open).not.toHaveBeenCalled();
    expect(pendingOperation("user")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "RUB" }));
    expect(screen.getByLabelText("цена в рублях")).toHaveTextContent("199");
    fireEvent.click(screen.getByRole("button", { name: "USD" }));
    expect(screen.getByLabelText("цена в долларах")).toHaveTextContent("2,99");
  });
  it("does not invent a historical price or payment method for an active legacy subscription", async () => {
    setup("active", undefined, overview("active"));
    await screen.findByText(/оплата пока недоступна/);
    expect(
      screen.getByText("сведения о способе оплаты недоступны"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("автоматических списаний нет"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "отменить подписку" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "продлить подписку" }),
    ).not.toBeInTheDocument();
  });
  it("shows an independently fixed current contract price alongside a different new offer", async () => {
    setup("active", undefined, {
      ...overview("active"),
      current_price: { amount_minor: 12345, currency: "RUB" },
    });
    await screen.findByText(/оплата пока недоступна/);
    expect(screen.getByText(/123,45/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "RUB" }));
    expect(screen.getByLabelText("цена в рублях")).toHaveTextContent("299");
  });
  it("keeps display fallback without checkout authority when no offer exists", async () => {
    setup("free", undefined, { ...overview(), offers: [] });
    await screen.findByText(/оплата пока недоступна/);
    fireEvent.click(screen.getByRole("button", { name: "RUB" }));
    expect(screen.getByLabelText("цена в рублях")).toHaveTextContent("399");
    fireEvent.click(screen.getByRole("button", { name: "купить" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it("distinguishes manually assigned Platinum from a new Premium offer", async () => {
    setup("active", undefined, {
      ...overview("active"),
      plan: "PLATINUM",
      offers: [],
    });
    await screen.findByText(/тариф назначен вручную/);
    expect(
      screen.queryByRole("button", { name: "продлить подписку" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "купить" })).toBeVisible();
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
});

describe("server payment route capabilities", () => {
  it.each(["SANDBOX", "DISABLED"])(
    "blocks all mutation and browser actions for %s even with advertised actions",
    async (mode) => {
      const { billing, open } = setup("active", undefined, {
        ...fixtures.active,
        provider_mode: mode,
      });
      await screen.findByText(/оплата пока недоступна/);
      expect(
        screen.queryByRole("button", { name: "продлить подписку" }),
      ).not.toBeInTheDocument();
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "отменить подписку" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "изменить способ оплаты" }),
      ).not.toBeInTheDocument();
      expect(billing.start).not.toHaveBeenCalled();
      expect(open).not.toHaveBeenCalled();
    },
  );
  it("treats a legacy response without capability fields as read-only", async () => {
    const {
      provider_mode: _mode,
      payment_routes: _routes,
      ...legacy
    } = fixtures.free;
    void _mode;
    void _routes;
    expect(paymentsEnabled(parseOverview(legacy))).toBe(false);
    const { billing, open } = setup("free", undefined, legacy);
    await screen.findByText(/оплата пока недоступна/);
    fireEvent.click(screen.getByRole("button", { name: "купить" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(billing.start).not.toHaveBeenCalled();
    expect(open).not.toHaveBeenCalled();
  });
  it("keeps four visible routes, disables unsupported currencies and describes one-time payment", async () => {
    const { billing } = setup();
    const dialog = await openPaymentChoice();
    expect(within(dialog).getAllByRole("radio")).toHaveLength(4);
    expect(screen.getByDisplayValue("MIR")).toBeDisabled();
    expect(screen.getByDisplayValue("BANK_CARD")).toBeChecked();
    fireEvent.click(screen.getByDisplayValue("MIR"));
    expect(screen.getByDisplayValue("BANK_CARD")).toBeChecked();
    fireEvent.click(screen.getByDisplayValue("CRYPTO"));
    expect(dialog).toHaveTextContent(
      "разовая оплата. автоматических списаний не будет",
    );
    expect(billing.start).not.toHaveBeenCalled();
  });
  it("uses the first available server route when the preferred route is disabled", async () => {
    setup("free", undefined, {
      ...fixtures.free,
      payment_routes: fixtures.free.payment_routes.map((cap) =>
        cap.id === "BANK_CARD"
          ? { ...cap, currencies: [], recurring_currencies: [] }
          : cap,
      ),
    });
    await openPaymentChoice();
    expect(screen.getByDisplayValue("BANK_CARD")).toBeDisabled();
    expect(screen.getByDisplayValue("ALIPAY_WECHAT")).toBeChecked();
  });
  it("blocks checkout when no route supports the selected currency and keeps prices visible", async () => {
    setup("free", undefined, {
      ...fixtures.free,
      payment_routes: fixtures.free.payment_routes.map((cap) => ({
        ...cap,
        currencies: cap.currencies.filter((code) => code === "RUB"),
        recurring_currencies: cap.recurring_currencies.filter(
          (code) => code === "RUB",
        ),
      })),
    });
    await screen.findByText(/в этой валюте оплата недоступна/);
    fireEvent.click(screen.getByRole("button", { name: "купить" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByLabelText("цена в долларах")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "RUB" }));
    expect(screen.getByRole("button", { name: "купить" })).toBeEnabled();
  });
  it("closes a stale quote when capabilities change on refresh", async () => {
    const { billing } = setup();
    await openPaymentChoice();
    vi.mocked(billing.overview).mockResolvedValue(
      parseOverview({
        ...fixtures.free,
        revision: "changed",
        provider_mode: "DISABLED",
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "обновить подписку" }));
    await screen.findByText(/оплата пока недоступна/);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(billing.start).not.toHaveBeenCalled();
  });
  it("can read a pending sandbox operation but never opens its payment URL", async () => {
    const { billing, open } = setup("free", undefined, {
      ...fixtures.free,
      provider_mode: "SANDBOX",
      pending_operation_id: pending.id,
    });
    await waitFor(() => expect(billing.operation).toHaveBeenCalled());
    expect(
      screen.queryByRole("button", { name: "открыть платёжный сервис" }),
    ).not.toBeInTheDocument();
    expect(billing.start).not.toHaveBeenCalled();
    expect(open).not.toHaveBeenCalled();
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

it("confirms renewal at the immutable contract price and currency despite a newer offer and display currency", async () => {
  saveCurrency("user", "USD");
  const { billing } = setup("active", undefined, {
    ...fixtures.active,
    current_price: { amount_minor: 12345, currency: "RUB" },
  });
  const dialog = await openPaymentChoice("продлить подписку");
  expect(dialog.querySelector(".payment-choice-summary")).toHaveTextContent(
    "123,45 ₽",
  );
  fireEvent.click(
    within(dialog).getByRole("button", { name: "перейти к оплате" }),
  );
  await waitFor(() =>
    expect(billing.start).toHaveBeenCalledWith(
      "token",
      expect.objectContaining({ action: "RENEW", currency: "RUB" }),
      expect.any(AbortSignal),
    ),
  );
});
