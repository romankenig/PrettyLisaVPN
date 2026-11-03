import { currencyFrom, money, checkoutSummary, supportMail } from "./model.mjs";

const params = new URLSearchParams(location.search);
let currency = currencyFrom(params.get("currency"));
const menu = document.querySelector(".menu-toggle");
menu?.addEventListener("click", () => {
  const expanded = menu.getAttribute("aria-expanded") === "true";
  menu.setAttribute("aria-expanded", String(!expanded));
  document.querySelector("#navigation")?.classList.toggle("open", !expanded);
});
document.addEventListener("keydown", (event) => {
  if (
    event.key === "Escape" &&
    menu?.getAttribute("aria-expanded") === "true"
  ) {
    menu.setAttribute("aria-expanded", "false");
    document.querySelector("#navigation")?.classList.remove("open");
    menu.focus();
  }
});

function showPrice() {
  const quote = checkoutSummary(currency);
  document.querySelectorAll("[data-premium-price]").forEach((node) => {
    node.textContent = money(quote.baseMinor, quote.currency);
  });
  document.querySelectorAll("[data-currency]").forEach((node) => {
    node.setAttribute(
      "aria-pressed",
      String(node.dataset.currency === currency),
    );
  });
  document.querySelectorAll('a[href^="/checkout/"]').forEach((node) => {
    node.href = `/checkout/?currency=${currency}`;
  });
  const select = document.querySelector("#checkout-currency");
  if (select) select.value = currency;
}
document.querySelectorAll("[data-currency]").forEach((button) =>
  button.addEventListener("click", () => {
    currency = currencyFrom(button.dataset.currency);
    history.replaceState(null, "", `${location.pathname}?currency=${currency}`);
    showPrice();
  }),
);
document
  .querySelector("#checkout-currency")
  ?.addEventListener("change", (event) => {
    currency = currencyFrom(event.target.value);
    history.replaceState(null, "", `${location.pathname}?currency=${currency}`);
    showPrice();
  });
showPrice();

const supportForm = document.querySelector("#support-form");
if (supportForm) {
  const topic = document.querySelector("#support-topic");
  const message = document.querySelector("#support-message");
  const error = document.querySelector("#support-error");
  const result = document.querySelector("#support-result");
  const selected = params.get("topic");
  if (["question", "access", "refund", "privacy"].includes(selected))
    topic.value = selected;
  supportForm.addEventListener("submit", (event) => {
    event.preventDefault();
    error.textContent = "";
    result.replaceChildren();
    message.removeAttribute("aria-invalid");
    try {
      const address = supportMail(topic.value, message.value);
      const action = document.createElement("a");
      action.href = address;
      action.className = "text-link";
      action.textContent = "Открыть подготовленное письмо →";
      result.append("Письмо подготовлено, но ещё не отправлено. ", action);
      action.focus();
    } catch (failure) {
      error.textContent = failure.message;
      message.setAttribute("aria-invalid", "true");
      message.focus();
    }
  });
  message.addEventListener("input", () => {
    result.replaceChildren();
    error.textContent = "";
    message.removeAttribute("aria-invalid");
  });
  topic.addEventListener("change", () => result.replaceChildren());
}
