import { releaseMetadata } from "./downloads.mjs";
import { acquisitionPrices, formatMonthlyPrice } from "./pricing.mjs";

const pricing = document.querySelector("[data-pricing]");
if (pricing) {
  fetch("/api/billing/catalog", {
    cache: "no-store",
    credentials: "omit",
    signal: AbortSignal.timeout(8000),
  })
    .then((response) => (response.ok ? response.json() : null))
    .then((value) => {
      const prices = acquisitionPrices(value);
      if (!prices) return;
      const render = (currency) => {
        pricing.querySelector("[data-price]").textContent = formatMonthlyPrice(
          prices[currency],
          currency,
          document.documentElement.lang,
        );
        for (const button of pricing.querySelectorAll("[data-currency]")) {
          button.disabled = false;
          button.setAttribute(
            "aria-pressed",
            String(button.dataset.currency === currency),
          );
        }
      };
      for (const button of pricing.querySelectorAll("[data-currency]"))
        button.addEventListener("click", () => render(button.dataset.currency));
      render(document.documentElement.lang === "ru" ? "RUB" : "USD");
    })
    .catch(() => {
      /* Missing prices stay unavailable; never substitute a hardcoded amount. */
    });
}

const language = document.querySelector(".language");
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && language?.open) {
    language.open = false;
    language.querySelector("summary").focus();
  }
});
document.addEventListener("click", (event) => {
  if (language?.open && !language.contains(event.target)) language.open = false;
});
const release = document.querySelector("[data-release]");
if (release) {
  fetch("/downloads/index.json", {
    cache: "no-store",
    credentials: "omit",
    signal: AbortSignal.timeout(8000),
  })
    .then((response) => (response.ok ? response.json() : null))
    .then((index) => {
      const metadata = releaseMetadata(
        index,
        release.dataset.release,
        document.documentElement.lang,
      );
      if (!metadata) return;
      release.querySelector("[data-version]").textContent = metadata.version;
      release.querySelector("[data-size]").textContent = metadata.size;
      release.querySelector("[data-checksum]").textContent = metadata.sha256;
      release.hidden = false;
    })
    .catch(() => {
      /* The direct download stays usable without optional metadata. */
    });
}

const portal = document.querySelector("[data-portal]");
if (portal) import("./portal.mjs").then(({ mountPortal }) => mountPortal(portal));
