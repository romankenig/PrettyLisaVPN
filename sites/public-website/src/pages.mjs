import { readFileSync } from "node:fs";
import { languages, platforms, legalKeys, routeFor } from "./structure.mjs";
import { website } from "./model.mjs";
import {
  referencePrices,
  referenceOriginalPrices,
  referencePriceCopy,
  formatMonthlyPrice,
} from "./pricing.mjs";

export const locales = Object.fromEntries(
  languages.map((code) => [
    code,
    JSON.parse(
      readFileSync(new URL(`./locales/${code}.json`, import.meta.url), "utf8"),
    ),
  ]),
);
export const escape = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const text = (value) =>
  escape(value).replaceAll(
    "PrettyLisaVPN",
    '<span class="product-name">PrettyLisaVPN</span>',
  );
const lines = (value) => text(value).replaceAll("\n", "<br>");
const arrow = '<span aria-hidden="true">↗</span>';
const mail = "mailto:help@prettylisavpn.com";
const money = (minor, currency, lang) =>
  new Intl.NumberFormat(lang, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(minor / 100);
function faqAnswer(lang, answer, index) {
  const targets = [
    [
      routeFor(lang, "/download/android/"),
      routeFor(lang, "/download/windows/"),
    ],
    [],
    [],
    [mail],
    [mail],
    [routeFor(lang, "/legal/payments/"), mail],
  ][index];
  let linkIndex = 0;
  const paragraphs = answer.split("\n\n").map(
    (paragraph) =>
      `<p>${paragraph
        .split(/(\[[^\]]+\])/)
        .map((part) => {
          if (!part.startsWith("[")) return text(part);
          const target = targets[linkIndex++];
          if (!target) throw new Error(`Unexpected FAQ link: ${lang}/${index}`);
          return `<a href="${target}">${text(part.slice(1, -1))}</a>`;
        })
        .join("")}</p>`,
  );
  if (linkIndex !== targets.length)
    throw new Error(`Missing FAQ link: ${lang}/${index}`);
  return `<div class="faq-answer">${paragraphs.join("")}</div>`;
}
const icons = {
  android:
    '<path d="m7 5-2-3m12 3 2-3M4 11a8 8 0 0 1 16 0v8H4Z"/><path d="M8 19v3m8-3v3M1 12v6m22-6v6"/><path d="M8 8h.01M16 8h.01"/>',
  windows:
    '<path d="M2 4 10 3v8H2Zm11-1 9-1v9h-9ZM2 14h8v8l-8-1Zm11 0h9v10l-9-1Z"/>',
  ios: '<rect x="6" y="1" width="12" height="22" rx="3"/><path d="M10 4h4m-3 16h2"/>',
  macos:
    '<rect x="4" y="3" width="16" height="13" rx="2"/><path d="M4 16 1 21h22l-3-5M9 20h6"/>',
  linux:
    '<path d="M9 11V6a3 3 0 0 1 6 0v5l4 7-3 3H8l-3-3Z"/><path d="m9 9 3 2 3-2M5 21H2m17 0h3"/>',
  "android-tv":
    '<rect x="2" y="4" width="20" height="14" rx="2"/><path d="M8 22h8m-4-4v4m-2-14-3 3 3 3m4-6 3 3-3 3"/>',
  chrome:
    '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="4"/><path d="M12 8h9M8.5 14 4 6m10 10-4 6"/>',
};
function icon(id) {
  return `<svg class="platform-icon" viewBox="0 0 24 26" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[id]}</svg>`;
}
function screenshot(file, alt) {
  const android = file.startsWith("android");
  return `<img class="app-screen" src="/assets/screenshots/${file}.png" alt="${escape(alt)}" width="${android ? 1080 : 960}" height="${android ? 1920 : 640}" loading="lazy" decoding="async">`;
}
function shell(lang, route, title, content) {
  const t = locales[lang],
    home = routeFor(lang);
  return `<!doctype html><html lang="${lang === "zh" ? "zh-CN" : lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="${escape(t.description)}"><meta name="robots" content="noindex,nofollow"><meta name="theme-color" content="#2c016d"><title>${escape(title)} · PrettyLisaVPN</title><link rel="icon" href="/assets/lock.svg" type="image/svg+xml"><link rel="stylesheet" href="/assets/style.css">${languages.map((code) => `<link rel="alternate" hreflang="${code === "zh" ? "zh-CN" : code}" href="https://prettylisavpn.com${routeFor(code, route)}">`).join("")}<script src="/assets/app.js" type="module"></script></head><body>
  <a class="skip" href="#main">${text(t.nav.skip)}</a><header class="header wrap"><a class="brand" href="${home}" aria-label="PrettyLisaVPN — ${escape(t.nav.home)}"><img src="/assets/lock.svg" width="28" height="38" alt=""><span class="product-name">PrettyLisaVPN</span></a>
  <nav aria-label="${escape(t.nav.menu)}"><a href="${home}#features">${text(t.nav.features)}</a><a href="${home}#pricing">${text(t.nav.pricing)}</a><a href="${home}#download">${text(t.nav.download)}</a><a href="${home}#help">${text(t.nav.help)}</a><a href="#documents">${text(t.footer.documents)}</a></nav>
  <details class="language"><summary aria-label="${escape(t.nav.language)}"><span aria-hidden="true">◎</span> ${lang} <span aria-hidden="true">⌄</span></summary><div>${languages.map((code) => `<a lang="${code}" hreflang="${code}" href="${routeFor(code, route)}" ${code === lang ? 'aria-current="true"' : ""}>${escape(locales[code].name)}</a>`).join("")}</div></details></header>
  <main id="main">${content}</main><footer class="footer wrap"><a class="brand" href="${home}"><img src="/assets/lock.svg" width="24" height="34" alt=""><span class="product-name">PrettyLisaVPN</span></a><nav class="legal-links" id="documents" aria-label="${escape(t.footer.documents)}">${legalKeys.map((key) => `<a href="${routeFor(lang, `/legal/${key}/`)}" class="document-button">${text(t.footer[key])}</a>`).join("")}</nav><div class="footer-bottom"><small class="moderation-marker">${text(website.moderationMarker)}</small><div class="footer-contacts"><a href="${mail}">help@prettylisavpn.com</a></div><small>© 2026 <span class="product-name">PrettyLisaVPN</span></small></div></footer></body></html>`;
}
function platformCard(lang, platform) {
  const t = locales[lang];
  return `<a class="platform-card ${platform.file ? "" : "soon"}" href="${routeFor(lang, `/download/${platform.id}/`)}">${icon(platform.id)}<span><strong>${text(t.platforms.names[platform.id])}</strong><small>${text(t.platforms.descriptions[platform.id])}</small></span><span class="platform-status">${platform.file ? arrow : text(t.platforms.soon)}</span></a>`;
}
function prices(lang) {
  const p = locales[lang].pricing;
  return `<div class="price-options">${["RUB", "USD"].map((currency) => `<div class="price-option" data-currency="${currency}"><p class="currency-label">${text(p.currencies[currency])}</p><p class="price"><s data-reference-price="${currency}">${text(formatMonthlyPrice(referenceOriginalPrices[currency], currency, lang))}</s><strong data-price="${currency}">${text(formatMonthlyPrice(referencePrices[currency], currency, lang))}</strong></p><p class="price-period">${text(p.period)}</p><a class="button" href="${routeFor(lang, "/account/")}?currency=${currency}">${text(p.buy)}</a></div>`).join("")}</div>`;
}
function pricing(lang) {
  const p = locales[lang].pricing;
  return `<section class="pricing section wrap" id="pricing" data-pricing><div class="section-heading"><p class="eyebrow">${text(p.eyebrow)}</p><h2>${text(p.title)}</h2><p>${text(p.intro)}</p></div><div class="plans"><article class="plan premium-plan"><h3>premium ⭐</h3><p class="plan-description">${text(p.description)}</p><ul>${p.features.map((feature) => `<li>${text(feature)}</li>`).join("")}</ul><div class="currency-picker"><fieldset class="currency-switch"><legend class="sr-only">${text(p.currency)}</legend><label><input type="radio" name="currency" value="RUB" checked><span>₽ RUB</span></label><label><input type="radio" name="currency" value="USD"><span>$ USD</span></label></fieldset>${prices(lang)}</div></article><article class="plan free-plan"><h3>free 🆓</h3><p class="free-price"><span data-free-currency="RUB">${text(money(0, "RUB", lang))}</span><span data-free-currency="USD">${text(money(0, "USD", lang))}</span></p><p>${text(p.free)}</p><a class="text-link" href="${routeFor(lang, "/account/")}">${text(p.upgrade)} ${arrow}</a></article></div><aside class="demo-plan" data-demo-plan><div><h3>demo 🌱 · ${text(p.demo.title)}</h3><p>${text(p.demo.description)}</p><p class="demo-upgrade">${text(p.demo.upgrade)}</p></div><a class="text-link" href="${routeFor(lang, "/download/android/")}">${text(p.demo.button)} ${arrow}</a></aside><div class="purchase-details"><p data-price-reference-note>${text(referencePriceCopy[lang])}</p><p>${text(p.terms)}</p></div></section>`;
}
function paymentNotice(lang) {
  const p = locales[lang].pricing;
  return `<aside class="payment-notice" id="payment-unavailable"><h2>${text(p.manage)}</h2><p>${text(p.terms)}</p><a class="button" href="${routeFor(lang, "/account/")}">${text(p.manage)}</a></aside>`;
}
function home(lang) {
  const t = locales[lang];
  return shell(
    lang,
    "/",
    t.title,
    `
  <section class="hero wrap"><p class="launch"><span aria-hidden="true"></span>${text(t.launch)}</p><h1>${lines(t.hero.title)}</h1><p class="lead">${text(t.hero.text)}</p><div class="actions"><a class="button" href="#download">${text(t.hero.button)} ${arrow}</a><a class="text-link" href="#features">${text(t.hero.link)} <span aria-hidden="true">↓</span></a></div></section>
  <section class="features section wrap" id="features"><div class="section-heading"><p class="eyebrow">${text(t.features.eyebrow)}</p><h2>${lines(t.features.title)}</h2></div><div class="feature-layout"><div class="feature-copy">${t.features.items.map((item, i) => `<article><span class="feature-number">0${i + 1}</span><div><h3>${text(item.title)}</h3><p>${text(item.text)}</p></div></article>`).join("")}</div><figure class="desktop-shot">${screenshot("windows-home", t.screens.windows)}<figcaption>${text(t.screens.caption)}</figcaption></figure></div></section>
  ${pricing(lang)}
  <section class="platforms-section" id="download"><div class="section wrap"><div class="section-heading"><p class="eyebrow">${text(t.platforms.eyebrow)}</p><h2>${text(t.platforms.title)}</h2><p>${text(t.platforms.text)}</p></div><div class="platform-layout"><div class="platform-grid">${platforms.map((p) => platformCard(lang, p)).join("")}</div><figure class="phone-shot">${screenshot("android-home", t.screens.android)}<figcaption>${text(t.screens.caption)}</figcaption></figure></div></div></section>
  <section class="help section wrap" id="help"><div class="section-heading"><p class="eyebrow">${text(t.help.eyebrow)}</p><h2 class="faq-title">${text(t.help.title)}</h2></div><div class="help-layout"><div class="questions">${t.help.questions.map(({ q, a }, index) => `<details><summary>${text(q)}<span aria-hidden="true">+</span></summary>${faqAnswer(lang, a, index)}</details>`).join("")}</div><aside class="support-card"><img src="/assets/lock.svg" width="36" height="48" alt=""><h3>${text(t.help.contactTitle)}</h3><p>${text(t.help.contactText)}</p><a class="button" href="${mail}">${text(t.help.contactButton)} ${arrow}</a><a class="support-email" href="${mail}">help@prettylisavpn.com</a></aside></div></section>`,
  );
}
function download(lang, platform) {
  const t = locales[lang],
    d = t.download,
    name = t.platforms.names[platform.id];
  const route = `/download/${platform.id}/`;
  const sources = platform.file
    ? `<div class="source-links"><a href="/downloads/${platform.id}-sources.tar.gz" download>${text(d.sources)}</a>${platform.id === "windows" ? `<a href="/downloads/windows-licenses.txt">${text(d.licenses)}</a>` : ""}</div>`
    : "";
  const choices = `<div class="download-card"><h2>${text(d.direct)}</h2>${platform.file ? `<p>${text(d.requirements[platform.id])}</p><a class="button" href="/downloads/${platform.file}" download>${text(d.file)} <span aria-hidden="true">↓</span></a><div class="release-meta" data-release="${platform.id}" hidden><p><span>${text(d.latest)}</span> <strong data-version></strong> · <span data-size></span></p><details><summary>${text(d.checksum)}</summary><code data-checksum></code></details></div>${sources}` : `<button class="button" disabled>${text(t.platforms.soon)}</button>`}</div><div class="download-card stores"><h2>${text(d.stores)}</h2>${platform.stores.map((store) => `<button class="store-option" disabled><span>${text(d.storeNames[store])}</span><small>${text(t.platforms.soon)}</small></button>`).join("")}</div>`;
  return shell(
    lang,
    route,
    `${d.title} ${name}`,
    `<div class="download-page wrap"><a class="back" href="${routeFor(lang)}#download">← ${text(d.other)}</a><div class="download-heading">${icon(platform.id)}<h1><span class="product-name">PrettyLisaVPN</span><br>${text(d.title)} ${text(name)}</h1><p class="lead">${text(platform.file ? d.text : t.platforms.descriptions[platform.id])}</p></div><div class="download-options">${choices}</div>${
      platform.file
        ? `<section class="setup"><h2>${text(d.setup)}</h2><ol>${d.steps.map((step) => `<li>${text(step)}</li>`).join("")}</ol></section><figure class="download-screen ${platform.id === "android" ? "phone" : ""}">${screenshot(platform.id === "android" ? "android-home" : "windows-home", platform.id === "android" ? t.screens.android : t.screens.windows)}<figcaption>${text(t.screens.caption)}</figcaption></figure>`
        : `<p class="upcoming-copy">${text(d.upcoming)}</p><div class="alternative-platforms">${platforms
            .filter((p) => p.file)
            .map((p) => platformCard(lang, p))
            .join("")}</div>`
    }<p class="download-help"><a href="${routeFor(lang)}#help">${text(d.help)} ${arrow}</a></p></div>`,
  );
}
function legalDocument(lang, key) {
  const t = locales[lang];
  const legalText = (value) =>
    text(value).replaceAll(
      "help@prettylisavpn.com",
      `<a href="${mail}">help@prettylisavpn.com</a>`,
    );
  const paragraphs = (items) =>
    items
      .map((paragraph) => {
        const [lead, ...list] = paragraph.split("\n");
        return `<p>${legalText(lead)}</p>${list.length ? `<ul class="document-list">${list.map((item) => `<li>${legalText(item)}</li>`).join("")}</ul>` : ""}`;
      })
      .join("");
  const document = t.legal[key];
  if (typeof document[0] === "string") return paragraphs(document);
  return `${key === "privacy" ? paragraphs([t.legal.privacyIntro]) : ""}<nav class="document-contents" aria-label="${escape(t.legal.contents)}"><h2>${text(t.legal.contents)}</h2><ol>${document.map((section, index) => `<li><a href="#section-${index + 1}">${text(section.title)}</a></li>`).join("")}</ol></nav>${document.map((section, index) => `<section class="document-section" aria-labelledby="section-${index + 1}"><h2 id="section-${index + 1}">${index + 1}. ${text(section.title)}</h2>${paragraphs(section.paragraphs)}</section>`).join("")}`;
}
export function pages() {
  const result = new Map();
  for (const lang of languages) {
    const t = locales[lang];
    result.set(routeFor(lang), home(lang));
    for (const platform of platforms)
      result.set(
        routeFor(lang, `/download/${platform.id}/`),
        download(lang, platform),
      );
    for (const key of legalKeys) {
      const route = `/legal/${key}/`;
      result.set(
        routeFor(lang, route),
        shell(
          lang,
          route,
          t.footer[key],
          `<article class="legal-page wrap"><a class="back" href="${routeFor(lang)}">← ${text(t.nav.home)}</a><h1>${text(t.footer[key])}</h1><p class="document-date">${text(t.legal.updated)}</p>${key === "payments" ? paymentNotice(lang) : ""}${legalDocument(lang, key)}</article>`,
        ),
      );
    }
    result.set(
      routeFor(lang, "/404/"),
      shell(
        lang,
        "/404/",
        t.notFound.title,
        `<section class="not-found wrap"><h1>${text(t.notFound.title)}</h1><p>${text(t.notFound.text)}</p><a class="button" href="${routeFor(lang)}">${text(t.nav.home)} ${arrow}</a></section>`,
      ),
    );
  }
  for (const lang of languages) {
    for (const route of [
      "/account/",
      "/account/success/",
      "/account/failure/",
    ]) {
      result.set(
        routeFor(lang, route),
        shell(
          lang,
          route,
          locales[lang].pricing.manage,
          `<section class="portal wrap" data-portal aria-live="polite"><h1>${text(locales[lang].pricing.manage)}</h1><p>${text(locales[lang].pricing.loading)}</p></section>`,
        ),
      );
    }
  }
  return result;
}
