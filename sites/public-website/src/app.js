import { releaseMetadata } from "./downloads.mjs";
import {
  cachedPrices,
  savePublicPrices,
  acquisitionPrices,
  acquisitionReferencePrices,
  formatMonthlyPrice,
} from "./pricing.mjs";

const pricing = document.querySelector("[data-pricing]");
if (pricing) {
  let storage;
  try {
    storage = localStorage;
  } catch {
    /* Private mode may block storage. */
  }
  const render = ({ prices, original }, reference) => {
    for (const node of pricing.querySelectorAll("[data-price]")) {
      const currency = node.dataset.price;
      node.textContent = formatMonthlyPrice(
        prices[currency],
        currency,
        document.documentElement.lang,
      );
    }
    for (const node of pricing.querySelectorAll("[data-reference-price]")) {
      const currency = node.dataset.referencePrice;
      node.hidden = original[currency] == null;
      node.textContent = node.hidden
        ? ""
        : formatMonthlyPrice(
            original[currency],
            currency,
            document.documentElement.lang,
          );
    }
    pricing.querySelector("[data-price-reference-note]").hidden = !reference;
  };
  const saved = cachedPrices(storage);
  if (saved) render(saved, true);
  fetch("/api/billing/catalog", {
    cache: "no-store",
    credentials: "omit",
    signal: AbortSignal.timeout(8000),
  })
    .then((response) => (response.ok ? response.json() : null))
    .then((value) => {
      const prices = acquisitionPrices(value);
      if (!prices) return;
      render({ prices, original: acquisitionReferencePrices(value) }, false);
      savePublicPrices(storage, value);
    })
    .catch(() => {
      /* Keep last known public prices or the approved reference prices. */
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
if (portal)
  import("./portal.mjs").then(({ mountPortal }) => mountPortal(portal));
