"use strict";
/* Language support. The Finnish text is the key; other languages map it to a translation.
   Add a language: copy the EN table, translate the values and add it to TABLES.
   Placeholders {0}, {1}, … are filled from t()'s extra arguments. */

const LANGS = { fi: "Suomi", en: "English" };

const LANG = (() => {
  // ?lang=en in the address picks the language (and remembers it), handy for shared links
  const q = new URLSearchParams(location.search).get("lang");
  if (q && LANGS[q]) {
    try { localStorage.setItem("openholter.lang", q); } catch {}
    return q;
  }
  try {
    const saved = localStorage.getItem("openholter.lang");
    if (saved && LANGS[saved]) return saved;
  } catch {}
  return /^fi\b/i.test(navigator.language || "") ? "fi" : "en";
})();
const LOCALE = LANG === "fi" ? "fi-FI" : "en-GB";
document.documentElement.lang = LANG;

function setLang(l) {
  try { localStorage.setItem("openholter.lang", l); } catch {}
  location.reload();
}

const TABLES = {};

function t(key, ...args) {
  const tab = TABLES[LANG];
  let s = tab && Object.prototype.hasOwnProperty.call(tab, key) ? tab[key] : key; // "" is a valid translation
  if (args.length) s = s.replace(/\{(\d+)\}/g, (m, i) => (args[+i] ?? ""));
  return s;
}

// number with the language's decimal separator: dec(1.25, 1) -> "1,3" (fi) / "1.3" (en)
function dec(x, d = 1) {
  const s = Number(x).toFixed(d);
  return LANG === "fi" ? s.replace(".", ",") : s;
}

// static HTML: elements with data-t / data-t-title / data-t-aria get their text translated
function translateStatic(root = document) {
  root.querySelectorAll("[data-t]").forEach((el) => (el.textContent = t(el.dataset.t)));
  root.querySelectorAll("[data-t-title]").forEach((el) => (el.title = t(el.dataset.tTitle)));
  root.querySelectorAll("[data-t-aria]").forEach((el) => el.setAttribute("aria-label", t(el.dataset.tAria)));
}

// every request tells the server which language to answer in (error messages, warnings, PDF)
{
  const nativeFetch = window.fetch.bind(window);
  window.fetch = (url, opts = {}) => nativeFetch(url, { ...opts, headers: { "X-Lang": LANG, ...(opts.headers || {}) } });
}
