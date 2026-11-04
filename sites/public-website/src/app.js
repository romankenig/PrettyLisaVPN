import { releaseMetadata } from "./downloads.mjs";

const paymentDialog = document.querySelector("#payment-dialog");
document.querySelectorAll("[data-purchase]").forEach((link) => {
  link.addEventListener("click", (event) => {
    // The ordinary link remains a working no-JS/no-dialog fallback.
    if (typeof paymentDialog?.showModal !== "function") return;
    event.preventDefault();
    paymentDialog.querySelector("[data-payment-price]").textContent =
      link.dataset.price;
    paymentDialog.showModal();
  });
});
document
  .querySelector("[data-payment-close]")
  ?.addEventListener("click", () => paymentDialog.close());

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
