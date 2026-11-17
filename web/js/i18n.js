// Tiny i18n: JSON dictionaries in /locales, {placeholder} interpolation, English fallback.
// To edit wording, change locales/<lang>.json — no code changes needed.
export const LANGS = ['en', 'tr', 'id'];
const dicts = {};
let lang = 'en';

async function fetchDict(l) {
  if (!dicts[l]) {
    const res = await fetch(`locales/${l}.json`);
    if (!res.ok) throw new Error(`locales/${l}.json: ${res.status}`);
    dicts[l] = await res.json();
  }
  return dicts[l];
}

export function initialLang() {
  try { const s = localStorage.getItem('bb-lang'); if (LANGS.includes(s)) return s; } catch { /* ignore */ }
  const nav = (navigator.languages || [navigator.language || 'en']).map(x => x.slice(0, 2).toLowerCase());
  return nav.find(x => LANGS.includes(x)) || 'en';
}

export async function setLang(l) {
  if (!LANGS.includes(l)) l = 'en';
  await fetchDict('en');
  await fetchDict(l);
  lang = l;
  document.documentElement.lang = l;
  try { localStorage.setItem('bb-lang', l); } catch { /* ignore */ }
}

export const getLang = () => lang;
export const locale = () => (dicts[lang]?.meta?.locale) || 'en-GB';

function lookup(d, key) {
  return key.split('.').reduce((o, k) => (o == null ? undefined : o[k]), d);
}
export function t(key, vars) {
  let v = lookup(dicts[lang], key);
  if (v === undefined) v = lookup(dicts.en, key);
  if (v === undefined) return key;
  if (typeof v === 'string' && vars) v = v.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
  return v;
}

// Static HTML (dialogs in index.html): data-i18n="key", data-i18n-html="key", data-i18n-attr="placeholder:key;aria-label:key"
export function applyStatic(root = document) {
  root.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  root.querySelectorAll('[data-i18n-html]').forEach(el => { el.innerHTML = t(el.dataset.i18nHtml); });
  root.querySelectorAll('[data-i18n-attr]').forEach(el => {
    el.dataset.i18nAttr.split(';').forEach(pair => { const [attr, key] = pair.split(':'); el.setAttribute(attr.trim(), t(key.trim())); });
  });
}

export const fmtNum = (n, opts) => new Intl.NumberFormat(locale(), opts).format(n);
export const fmtDate = (iso, opts) => new Date(`${iso}T12:00:00`).toLocaleDateString(locale(), opts);
export function fmtAgo(ms) {
  const rtf = new Intl.RelativeTimeFormat(locale(), { numeric: 'auto' });
  const m = Math.round(ms / 60000);
  if (m < 60) return rtf.format(-Math.max(1, m), 'minute');
  const h = Math.round(m / 60);
  if (h < 48) return rtf.format(-h, 'hour');
  return rtf.format(-Math.round(h / 24), 'day');
}
