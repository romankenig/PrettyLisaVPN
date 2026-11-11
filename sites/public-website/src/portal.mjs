import { portalCopy } from "./portal-copy.mjs";
import {
  cachedPrices,
  referencePriceCopy,
  formatMonthlyPrice,
  purchasePresentation,
} from "./pricing.mjs";

export function providerURL(raw) {
  const url = new URL(raw);
  if (
    url.origin !== "https://pay.platega.io" ||
    url.username ||
    url.password ||
    url.hash ||
    raw.length > 2048
  )
    throw new Error("PAYMENT_URL_NOT_ALLOWED");
  return url.href;
}

export async function mountPortal(root) {
  const t = portalCopy[document.documentElement.lang] ?? portalCopy.en;
  const priceLanguage =
    document.documentElement.lang === "zh-CN"
      ? "zh"
      : document.documentElement.lang;
  const api = "/api/web/billing";
  let account,
    accountEmail,
    overview,
    timer,
    generation = 0,
    locked = false;
  let currency =
    new URLSearchParams(location.search).get("currency") === "USD"
      ? "USD"
      : "RUB";
  const pagePath = () =>
    location.pathname +
    "?currency=" +
    currency +
    (isSuccessPreview() ? "&preview=1" : "");
  const languagePrefix = location.pathname.match(/^\/(en|de|fr|es|zh)\//)?.[1];
  const accountPath =
    (languagePrefix ? "/" + languagePrefix : "") + "/account/";
  const isSuccessPreview = () =>
    location.pathname === accountPath + "success/" &&
    new URLSearchParams(location.search).get("preview") === "1";
  const savedPrices = () => {
    try {
      return cachedPrices(localStorage);
    } catch {
      return null;
    }
  };
  const money = (p) =>
    new Intl.NumberFormat(document.documentElement.lang, {
      style: "currency",
      currency: p.currency,
    }).format(p.amount_minor / 100);
  const date = (raw) =>
    new Intl.DateTimeFormat(document.documentElement.lang, {
      dateStyle: "long",
      timeStyle: "short",
    }).format(new Date(raw));
  const el = (tag, value, className) => {
    const node = document.createElement(tag);
    if (value) node.textContent = value;
    if (className) node.className = className;
    return node;
  };
  const button = (label, action, primary = false) => {
    const node = el("button", label, primary ? "button" : "portal-secondary");
    node.type = "button";
    node.addEventListener("click", () => void guard(action));
    return node;
  };
  const notify = (message) => {
    root.querySelector("[role=alert]")?.remove();
    const node = el("p", message, "portal-error");
    node.role = "alert";
    root.append(node);
  };
  const guard = async (action) => {
    if (locked) return;
    locked = true;
    root.setAttribute("aria-busy", "true");
    try {
      await action();
    } catch (error) {
      if (error.code === "AUTH_INVALID") login();
      else
        notify(
          error.code === "otp_invalid"
            ? t.invalidCode
            : error.status === 429
              ? t.rateLimited
              : t.error,
        );
    } finally {
      locked = false;
      root.removeAttribute("aria-busy");
    }
  };
  async function request(path, body) {
    const response = await fetch(api + path, {
      method: body === undefined ? "GET" : "POST",
      credentials: "same-origin",
      cache: "no-store",
      redirect: "error",
      headers: { "Content-Type": "application/json", "X-PrettyLisa-Web": "1" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(12000),
    });
    const value = await response.json();
    if (!response.ok) {
      const error = new Error("BILLING_REQUEST_FAILED");
      error.code = value.error?.code;
      error.status = response.status;
      throw error;
    }
    return value;
  }
  function screen(title, text) {
    clearTimeout(timer);
    generation++;
    root.replaceChildren(
      el("p", "PrettyLisaVPN Premium", "eyebrow"),
      el("h1", title),
    );
    if (text) root.append(el("p", text, "portal-lead"));
    if (account && accountEmail)
      root.append(el("p", accountEmail, "portal-account"));
  }
  function purchaseCard({
    signedIn = false,
    stale = false,
    preview = null,
  } = {}) {
    const p =
      preview ?? purchasePresentation(overview, currency, savedPrices(), stale);
    const card = el("section", null, "portal-offer portal-purchase");
    card.dataset.purchaseOffer = "";
    if (p.reference) card.dataset.referencePrices = "";
    card.append(
      el("p", p.contract ? t.fixedPrice : t.selected, "portal-product-label"),
      el("h2", "PREMIUM ⭐"),
      el("p", t.productSummary),
    );
    const features = el("ul", null, "portal-benefits");
    for (const feature of [t.unlimited, t.premiumServers, t.devices])
      features.append(el("li", feature));
    card.append(features);
    const row = el("div", null, "portal-price-row"),
      price = el("div");
    const amount = el("p", null, "portal-price");
    if (p.original)
      amount.append(
        el(
          "s",
          formatMonthlyPrice(
            p.original,
            p.currency,
            document.documentElement.lang,
          ),
        ),
      );
    amount.append(
      el(
        "strong",
        formatMonthlyPrice(p.amount, p.currency, document.documentElement.lang),
      ),
    );
    price.append(amount, el("p", t.monthly, "portal-price-period"));
    row.append(price);
    if (!p.contract && !preview) {
      const picker = el("fieldset", null, "portal-currency");
      picker.append(el("legend", t.currency, "sr-only"));
      for (const code of ["RUB", "USD"]) {
        const label = el("label"),
          input = el("input");
        input.type = "radio";
        input.name = "purchase-currency";
        input.value = code;
        input.checked = p.currency === code;
        input.addEventListener("change", () => {
          currency = code;
          history.replaceState(null, "", pagePath());
          const next = purchaseCard({ signedIn, stale });
          card.replaceWith(next);
          next.querySelector(`input[value="${code}"]`).focus();
        });
        label.append(input, el("span", code));
        picker.append(label);
      }
      row.append(picker);
    }
    card.append(row);
    if (signedIn) {
      card.append(
        button(
          t.pay,
          () => (p.canPay ? confirm(p.action, p.offer) : openSuccessPreview(p)),
          true,
        ),
      );
      if (!p.canPay)
        card.append(el("p", t.placeholderHint, "portal-price-note"));
    }
    if (p.reference)
      card.append(
        el(
          "p",
          referencePriceCopy[priceLanguage] ?? referencePriceCopy.en,
          "portal-price-note",
        ),
      );
    return card;
  }
  function openSuccessPreview(preview) {
    location.assign(
      accountPath + "success/?preview=1&currency=" + preview.currency,
    );
  }
  function successPreview(stale = false) {
    const preview = purchasePresentation(
      overview,
      currency,
      savedPrices(),
      stale,
    );
    screen(t.success, t.placeholderText);
    const icon = el("span", "✓", "portal-success-icon");
    icon.setAttribute("aria-hidden", "true");
    root
      .querySelector("h1")
      .before(icon, el("p", t.placeholderTitle, "portal-preview-label"));
    const receipt = el("section", null, "portal-plan");
    receipt.dataset.successPreview = "";
    receipt.append(
      el("h2", "PREMIUM ⭐"),
      el(
        "p",
        formatMonthlyPrice(
          preview.amount,
          preview.currency,
          document.documentElement.lang,
        ) +
          " · " +
          t.monthly,
      ),
    );
    root.append(
      receipt,
      button(
        t.back,
        () => location.assign(accountPath + "?currency=" + preview.currency),
        true,
      ),
    );
    const home = el("a", t.home, "portal-secondary");
    home.href = languagePrefix ? "/" + languagePrefix + "/" : "/";
    root.append(home);
    root.querySelector("h1").tabIndex = -1;
    root.querySelector("h1").focus();
  }
  function login() {
    account = accountEmail = overview = null;
    screen(t.signIn, t.signInText);
    const form = el("form"),
      emailLabel = el("label", t.email),
      email = el("input");
    email.type = "email";
    email.autocomplete = "email";
    email.required = true;
    email.maxLength = 320;
    emailLabel.append(email);
    form.append(emailLabel);
    const codeLabel = el("label", t.code),
      code = el("input");
    code.type = "text";
    code.inputMode = "numeric";
    code.autocomplete = "one-time-code";
    code.pattern = "[0-9]{6}";
    code.maxLength = 6;
    codeLabel.append(code);
    codeLabel.hidden = true;
    form.append(codeLabel);
    const submit = el("button", t.sendCode, "button");
    submit.type = "submit";
    form.append(submit);
    let sent = false;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void guard(async () => {
        if (!sent) {
          await request("/request-otp", { email: email.value });
          sent = true;
          email.readOnly = true;
          code.required = true;
          codeLabel.hidden = false;
          submit.textContent = t.signIn;
          code.focus();
          form.append(
            el("p", t.codeSent),
            button(t.otherEmail, () => login()),
          );
        } else {
          await request("/login", { email: email.value, code: code.value });
          code.value = "";
          await load();
        }
      });
    });
    const layout = el("div", null, "portal-login-layout");
    layout.append(purchaseCard(), form);
    root.append(layout);
  }
  const journalKey = () => "prettylisa.billing." + account;
  async function load() {
    let value;
    try {
      value = await request("/overview");
    } catch (error) {
      if (error.code === "AUTH_INVALID") throw error;
      if (isSuccessPreview()) return successPreview(true);
      screen(t.title, t.error);
      if (overview?.current_price)
        root.append(
          el("p", t.fixedPrice),
          el("h2", money(overview.current_price)),
        );
      root.append(
        purchaseCard({ signedIn: true, stale: true }),
        button(t.refresh, load),
      );
      return;
    }
    account = value.account_id;
    accountEmail = value.email;
    overview = value.billing;
    let saved;
    try {
      saved = localStorage.getItem(journalKey());
    } catch {
      /* Reading the account does not require optional browser storage. */
    }
    if (overview.pending_operation_id)
      return watch({ id: overview.pending_operation_id, status: "PENDING" });
    if (saved) {
      let journal;
      try {
        journal = JSON.parse(saved);
      } catch {
        localStorage.removeItem(journalKey());
      }
      if (!journal || typeof journal !== "object") return summary();
      if (journal.operation_id)
        return watch(
          await request(
            "/operations/" + encodeURIComponent(journal.operation_id),
          ),
        );
      if (journal.command) return send(journal.command);
    }
    if (isSuccessPreview()) return successPreview();
    summary();
  }
  function summary() {
    const showPurchase =
      overview.new_contract_required ||
      overview.plan !== "PREMIUM" ||
      overview.actions.includes("RENEW");
    screen(t.title, showPurchase ? null : t.fixedPrice);
    const card = el("section", null, "portal-plan");
    card.append(el("p", t.yourPlan), el("span", overview.plan, "portal-badge"));
    if (overview.current_price)
      card.append(el("h2", money(overview.current_price) + " / " + t.month));
    if (overview.paid_until)
      card.append(el("p", t.paidUntil + " " + date(overview.paid_until)));
    if (overview.payment_method)
      card.append(
        el(
          "p",
          overview.payment_method.kind === "SBP"
            ? t.sbpAccount
            : overview.payment_method.label,
        ),
      );
    if (
      overview.auto_renew &&
      overview.next_charge_at &&
      overview.next_charge_price
    )
      card.append(
        el(
          "p",
          t.next +
            " " +
            date(overview.next_charge_at) +
            " · " +
            money(overview.next_charge_price),
        ),
      );
    else if (!overview.auto_renew && overview.paid_until)
      card.append(el("p", t.noRenewal));
    if (showPurchase) {
      const current = el("p", null, "portal-current-summary");
      current.append(
        document.createTextNode(t.yourPlan + ": "),
        el("strong", overview.plan),
      );
      root.append(current, purchaseCard({ signedIn: true }));
    }
    if (!showPurchase || overview.current_price || overview.paid_until)
      root.append(card);
    const live =
      overview.provider_mode === "LIVE" &&
      overview.payment_operations_available;
    if (live && overview.actions.includes("CANCEL"))
      root.append(button(t.cancel, cancel));
    root.append(
      button(t.refresh, load),
      button(t.logout, async () => {
        await request("/logout", {});
        login();
      }),
    );
  }
  function confirm(action, offer) {
    screen(t.confirm, t.recurringTerms);
    const price = {
      amount_minor: offer.prices.RUB.amount_minor,
      currency: "RUB",
    };
    root.append(
      el("h2", money(price) + " / " + t.month),
      el("p", t.fixedPrice),
    );
    const label = el("label", null, "portal-consent"),
      check = el("input");
    check.type = "checkbox";
    label.append(check, document.createTextNode(t.consent));
    root.append(label);
    const pay = button(t.pay, () => begin(action, offer.id, "SBP"), true);
    pay.disabled = true;
    check.addEventListener("change", () => {
      pay.disabled = !check.checked;
    });
    root.append(pay, button(t.back, summary));
  }
  function cancel() {
    screen(t.cancel, t.cancelText);
    root.append(el("p", t.changeMethod), el("p", t.newPrice));
    root.append(
      button(t.keep, summary, true),
      button(t.cancelConfirm, () => begin("CANCEL", null, null)),
    );
  }
  async function begin(action, offer_id, payment_route) {
    const command = {
      action,
      offer_id,
      payment_route,
      currency: "RUB",
      request_id: crypto.randomUUID(),
      expected_revision: overview.revision,
    };
    localStorage.setItem(journalKey(), JSON.stringify({ command })); // Before POST; a lost response reuses this exact key.
    await send(command);
  }
  async function send(command) {
    try {
      const operation = await request("/operations", command);
      localStorage.setItem(
        journalKey(),
        JSON.stringify({ operation_id: operation.id }),
      );
      await watch(operation);
    } catch (error) {
      if (
        error.status === 409 &&
        [
          "BILLING_REVISION_CHANGED",
          "BILLING_ACTION_UNAVAILABLE",
          "BILLING_ROUTE_UNAVAILABLE",
          "BILLING_PRICE_UNSUPPORTED",
        ].includes(error.code)
      ) {
        localStorage.removeItem(journalKey());
        await load();
      }
      throw error;
    }
  }
  async function watch(operation) {
    if (operation.status !== "PENDING") {
      localStorage.removeItem(journalKey());
      const value = await request("/overview");
      overview = value.billing;
      const success = operation.status === "SUCCEEDED";
      history.replaceState(
        null,
        "",
        success ? "/account/success/" : "/account/failure/",
      );
      screen(
        success ? t.success : t.failure,
        success ? t.successText : t.failureText,
      );
      if (overview.paid_until)
        root.append(el("p", t.paidUntil + " " + date(overview.paid_until)));
      root.append(button(success ? t.manage : t.retry, load, true));
      root.append(el("p", t.returnApp));
      const home = el("a", t.home, "portal-secondary");
      home.href = "/";
      root.append(home);
      return;
    }
    screen(t.pending, t.pendingText);
    if (operation.redirect_url) {
      const link = el("a", t.openBank, "button");
      link.href = providerURL(operation.redirect_url);
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      root.append(link);
    }
    root.append(button(t.check, () => poll(operation.id)));
    const current = generation;
    timer = setTimeout(() => {
      if (current === generation && !document.hidden && !locked)
        void poll(operation.id);
      else if (current === generation) void watch(operation);
    }, 3000);
  }
  async function poll(id) {
    try {
      await watch(await request("/operations/" + encodeURIComponent(id)));
    } catch (error) {
      if (error.code === "AUTH_INVALID") login();
      else {
        notify(t.pendingError);
        timer = setTimeout(() => void poll(id), 6000);
      }
    }
  }
  const fragment = new URLSearchParams(location.hash.slice(1));
  const handoff = fragment.get("handoff");
  history.replaceState(null, "", pagePath());
  await guard(async () => {
    if (handoff) await request("/exchange", { token: handoff });
    await load();
  });
}
