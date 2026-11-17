import { CONFIG } from './config.js';
import { LEVEL_ORDER, LEVEL_ICON, LEVEL_COLOR, SCORE_LABEL, levelKey, ROLES } from './data.js';
import { t, setLang, getLang, initialLang, applyStatic, LANGS, locale, fmtNum, fmtDate, fmtAgo } from './i18n.js';
import { loadDataset } from './risk.js';
import { createMap } from './map.js';
import { loadReports, addReport, removeLocal, rank, priorityColor, TYPES, TYPE_WEIGHT } from './reports.js';
import { learnCards } from './learn.js';
import { getCurrentWeather } from './weather.js';
import { startCompass, verifyUpload, verifierEnabled } from './verifier.js';

/* ------------------------------------------------------------------ state */
const saved = (() => { try { return JSON.parse(localStorage.getItem('bb-state') || '{}'); } catch { return {}; } })();
const state = {
  dsId: saved.dsId === 'hindcast' ? 'hindcast' : 'live',
  day: null,
  sel: saved.sel || null,               // {kind:'town', name} | {kind:'point', lat, lon}
  role: ROLES.includes(saved.role) ? saved.role : 'farmer',
  checked: new Set(saved.checked || []),
  layer: 'class', showLow: false, showFires: true, showTowns: true,
  sciSel: null, sciDay: null,
  repFilter: 'all', repSort: 'priority', repActive: null,
  learnTab: 'goals',
};
function persist() {
  try { localStorage.setItem('bb-state', JSON.stringify({ dsId: state.dsId, sel: state.sel, role: state.role, checked: [...state.checked] })); } catch { /* ignore */ }
}
const DS = {};
let mapApi = null;
let currentRefresh = null; // re-draws the current map's layers (after theme or day changes)

/* ------------------------------------------------------------------ helpers */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const app = $('#app');
const ICON = {
  flame: '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3c1 3.5 5 5.2 5 10a5 5 0 0 1-10 0c0-2.5 1.6-4.2 2.5-5 0 1.6.8 2.6 1.8 2.6 0-2.8-.8-5 .7-7.6z"/></svg>',
  pin: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/></svg>',
  search: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="m20 20-4-4"/></svg>',
  speaker: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4z"/><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12"/></svg>',
  share: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="m8.2 10.8 7.6-4.4M8.2 13.2l7.6 4.4"/></svg>',
  chat: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 20l1.5-4A8 8 0 1 1 9 19.3L4 20z"/></svg>',
  phone: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/></svg>',
  upload: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5M4 20h16"/></svg>',
  sun: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
  moon: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>',
};
function toast(msg, icon = '', action) {
  const el = document.createElement('div');
  el.className = 'toast'; el.setAttribute('role', 'status');
  el.innerHTML = `${icon}<span>${esc(msg)}</span>${action ? `<a href="${action.href}" style="color:#fff;font-weight:800;margin-left:6px">${esc(action.label)}</a>` : ''}`;
  $('#toasts').append(el);
  setTimeout(() => el.remove(), action ? 6000 : 3000);
}
const levelName = k => t(`levels.${k}.name`);
const fmtScore = n => fmtNum(n, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const dayLabel = (ds, i) => (ds.id === 'live' && i === ds.todayIdx ? t('common.today') : fmtDate(ds.meta.dates[i], { weekday: 'short' }));
const fold = s => s.toLocaleLowerCase('tr').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/ı/g, 'i');

/* ------------------------------------------------------------------ theme */
const isDark = () => document.documentElement.dataset.theme === 'dark';
function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem('bb-theme', theme); } catch { /* ignore */ }
  if (mapApi) { mapApi.setTheme(theme === 'dark'); currentRefresh?.(); }
  $$('[data-theme-toggle]').forEach(b => { b.innerHTML = theme === 'dark' ? ICON.sun : ICON.moon; b.setAttribute('aria-label', t(theme === 'dark' ? 'common.themeToLight' : 'common.themeToDark')); });
}

/* ------------------------------------------------------------------ chrome */
function controls() {
  return `<label><span class="visually-hidden">${t('common.language')}</span>
      <select class="select" data-lang>${LANGS.map(l => `<option value="${l}" ${l === getLang() ? 'selected' : ''}>${l.toUpperCase()}</option>`).join('')}</select></label>
    <button type="button" class="icon-btn" data-theme-toggle aria-label="${t(isDark() ? 'common.themeToLight' : 'common.themeToDark')}">${isDark() ? ICON.sun : ICON.moon}</button>`;
}
function topbar(active, withDataset = true) {
  const ds = (withDataset && DS[state.dsId]) || DS.live;
  let banner = '';
  if (ds) {
    const run = ds.runDate ? ds.runDate.toLocaleString(locale(), { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—';
    const stale = ds.id === 'live' && ds.ageHours != null && ds.ageHours > CONFIG.STALE_HOURS;
    banner = `<div class="banner"><div class="wrap"><strong>${t('common.bannerLabel')}</strong>${esc(ds.id === 'live' ? t('common.bannerLive', { time: run }) : t('common.bannerHindcast'))}${stale ? ` <b>${esc(t('common.bannerStale'))}</b>` : ''}</div></div>`;
  }
  return `<header class="topbar"><div class="wrap topbar__inner">
    <a class="brand" href="#/" aria-label="#BizdenBize"><span class="brand__logo">${ICON.flame}</span>
      <span><span class="brand__name">#BizdenBize</span><br><span class="brand__sub">${t('common.brandSub')}</span></span></a>
    <nav class="seg" aria-label="View">
      <a class="seg__btn" href="#/live" ${active === 'live' ? 'aria-current="page"' : ''}>${t('common.citizen')}<span class="long">${t('common.citizenLong')}</span></a>
      <a class="seg__btn" href="#/science" ${active === 'science' ? 'aria-current="page"' : ''}>${t('common.science')}<span class="long">${t('common.scienceLong')}</span></a>
      <a class="seg__btn" href="#/reports" ${active === 'reports' ? 'aria-current="page"' : ''}>${t('common.reports')}</a>
    </nav>
    <div class="topbar__end">
      ${withDataset ? `<label class="dataset"><span class="visually-hidden">${t('common.dataset')}</span>
        <select class="select" id="dataset"><option value="live" ${state.dsId === 'live' ? 'selected' : ''}>${t('common.datasetLive')}</option><option value="hindcast" ${state.dsId === 'hindcast' ? 'selected' : ''}>${t('common.datasetHindcast')}</option></select></label>` : ''}
      ${controls()}
    </div></div></header>${banner}`;
}
const appFooter = () => `<footer class="app-footer"><div class="wrap"><span>${t('common.footerLeft')}</span><span>${t('common.footerRight')}</span></div></footer>`;

function bindChrome() {
  $$('[data-lang]').forEach(s => s.addEventListener('change', async e => { await setLang(e.target.value); applyStatic(); refreshDialogs(); route(); }));
  $$('[data-theme-toggle]').forEach(b => b.addEventListener('click', () => setTheme(isDark() ? 'light' : 'dark')));
  $('#dataset')?.addEventListener('change', e => {
    state.dsId = e.target.value; state.day = null; state.sel = null; state.sciSel = null; state.sciDay = null; persist(); route();
  });
  $$('[data-report]').forEach(b => b.addEventListener('click', openReport));
}

function levelCard(k, today) {
  return `<article class="level risk risk--${k} ${today ? 'is-today' : ''}">
    <div class="level__head"><span aria-hidden="true" style="font-size:22px">${LEVEL_ICON[k]}</span><div><b>${levelName(k)}</b><small>${t(`levels.${k}.tag`)}</small></div>${today ? `<span class="level__today">${t('live.todayBadge')}</span>` : ''}</div>
    <div class="level__body"><b>${t(`levels.${k}.meaning`)}</b><ul>${t(`levels.${k}.todo`).map(x => `<li>${esc(x)}</li>`).join('')}</ul><span class="level__score">${SCORE_LABEL[k]} · ${t('levels.scoreLabel')}</span></div></article>`;
}
function gaugeSVG(k) {
  const cx = 150, cy = 150, r1 = 70, r2 = 140;
  const p = (r, a) => `${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`;
  const seg = (key, i) => {
    const a0 = Math.PI + (i * Math.PI) / 4, a1 = Math.PI + ((i + 1) * Math.PI) / 4, on = key === k;
    return `<path d="M${p(r2, a0)} A${r2},${r2} 0 0 1 ${p(r2, a1)} L${p(r1, a1)} A${r1},${r1} 0 0 0 ${p(r1, a0)} Z" fill="${LEVEL_COLOR[key]}" opacity="${on ? 1 : 0.35}" stroke="${on ? 'currentColor' : 'transparent'}" stroke-width="3"/>`;
  };
  const ang = Math.PI + ((LEVEL_ORDER.indexOf(k) + 0.5) * Math.PI) / 4;
  return `<svg class="gauge" viewBox="0 0 300 165" role="img" aria-label="${levelName(k)}">${LEVEL_ORDER.map(seg).join('')}
    <line x1="${cx}" y1="${cy}" x2="${(cx + 110 * Math.cos(ang)).toFixed(1)}" y2="${(cy + 110 * Math.sin(ang)).toFixed(1)}" stroke="currentColor" stroke-width="7" stroke-linecap="round"/><circle cx="${cx}" cy="${cy}" r="12" fill="currentColor"/></svg>`;
}
const townLabel = (s, k) => `<b>${esc(s.name)}</b> · ${levelName(k)}`;
const firePopup = d => t('live.firePopup', { date: fmtDate(d, { day: 'numeric', month: 'short' }) });

/* ------------------------------------------------------------------ Citizen (Live) */
function resolveSel(ds) {
  let sel = state.sel;
  if (sel?.kind === 'town' && !ds.byName(sel.name)) sel = null;
  if (sel?.kind === 'point' && ds.cellAt(sel.lat, sel.lon) < 0) sel = null;
  if (!sel) {
    // default: the highest-risk town today — what most people need to see first
    const top = [...ds.settlements].sort((a, b) => b.mean[ds.todayIdx] - a.mean[ds.todayIdx])[0];
    sel = { kind: 'town', name: top.name };
  }
  state.sel = sel;
  if (sel.kind === 'town') {
    const s = ds.byName(sel.name);
    return { name: s.name, lat: s.lat, lon: s.lon, pop: s.pop, scores: s.mean, keys: s.mean.map(levelKey), note: t('live.mean10') };
  }
  const k = ds.cellAt(sel.lat, sel.lon), c = ds.cellCenter(k), near = ds.nearest(sel.lat, sel.lon);
  return {
    name: near.km < 25 ? t('live.spotName', { town: near.s.name }) : t('live.spotNameNone'), lat: c.lat, lon: c.lon,
    scores: Array.from({ length: ds.days }, (_, d) => ds.score(k, d)),
    keys: Array.from({ length: ds.days }, (_, d) => LEVEL_ORDER[ds.classIdx(k, d)]),
    note: t('live.pointNote'),
  };
}

async function renderLive() {
  const ds = DS[state.dsId];
  if (state.day == null || state.day >= ds.days) state.day = ds.todayIdx;
  app.innerHTML = `${topbar('live')}
  <main id="main" class="wrap live">
    <div class="search" role="search">
      <div class="search__field">${ICON.search}<label class="visually-hidden" for="q">${t('live.searchLabel')}</label>
        <input id="q" type="search" placeholder="${esc(t('live.searchPlaceholder'))}" autocomplete="off" role="combobox" aria-expanded="false" aria-controls="results" aria-autocomplete="list"></div>
      <button class="btn btn--soft" id="near-me" type="button">${ICON.pin}${t('live.nearMe')}</button>
      <div class="dropdown" id="results" role="listbox" hidden></div>
    </div>
    <div class="panel" id="panel"></div>
    <div class="card mapcard">
      <div class="lmap" id="map" aria-label="${esc(t('live.mapHint'))}"></div>
      <div class="map-tools">
        <label><input type="checkbox" id="t-low" ${state.showLow ? 'checked' : ''}>${t('live.showLow')}</label>
        <label><input type="checkbox" id="t-towns" ${state.showTowns ? 'checked' : ''}>${t('live.showTowns')}</label>
        ${ds.fires.length ? `<label><input type="checkbox" id="t-fires" ${state.showFires ? 'checked' : ''}><span class="fire-dot"></span>${t('live.showFires')}</label>` : ''}
      </div>
      <div class="legend">${LEVEL_ORDER.map(k => `<button type="button" data-guide><span class="dot risk risk--${k}"></span>${levelName(k)}</button>`).join('')}
        <a class="legend__link" href="#colour-guide" data-guide>${t('live.coloursLink')}</a></div>
      <button type="button" class="dropzone" data-report>${ICON.upload}<span><b>${t('live.dropTitle')}</b><span class="muted small">${t('live.dropText')}</span></span>
        <span class="dropzone__actions"><span class="btn btn--coral">${t('live.sendReport')}</span></span></button>
    </div>
  </main>
  <section class="wrap guide" id="colour-guide" aria-labelledby="guide-h">
    <h2 class="h-section" id="guide-h" style="font-size:26px">${t('live.guideTitle')}</h2><p class="muted">${t('live.guideSub')}</p>
    <div class="guide__grid" id="guide-grid"></div></section>
  ${appFooter()}`;
  bindChrome();
  bindSearch(ds);
  $('#near-me').addEventListener('click', () => nearMe(ds));
  $$('[data-guide]').forEach(b => b.addEventListener('click', e => { e.preventDefault(); $('#colour-guide').scrollIntoView({ behavior: 'smooth' }); }));

  mapApi = createMap($('#map'), { dark: isDark(), onClick: ll => { state.sel = { kind: 'point', lat: ll.lat, lon: ll.lng }; persist(); updateLive(true); } });
  currentRefresh = () => {
    mapApi.setRisk(ds, state.day, { mode: 'class', showLow: state.showLow, attribution: t('common.mapAttribution') });
    mapApi.setTowns(ds, state.day, s => { state.sel = { kind: 'town', name: s.name }; persist(); updateLive(true); }, townLabel);
    mapApi.showTowns(state.showTowns);
    if (ds.fires.length) { mapApi.setFires(ds.fires, firePopup); mapApi.showFires(state.showFires); }
  };
  currentRefresh();
  $('#t-low').addEventListener('change', e => { state.showLow = e.target.checked; currentRefresh(); });
  $('#t-towns').addEventListener('change', e => { state.showTowns = e.target.checked; mapApi.showTowns(state.showTowns); });
  $('#t-fires')?.addEventListener('change', e => { state.showFires = e.target.checked; mapApi.showFires(state.showFires); });
  updateLive(true, true);
}

function updateLive(moveMap = false, first = false) {
  const ds = DS[state.dsId];
  const sel = resolveSel(ds);
  const k = sel.keys[state.day];
  const score = sel.scores[state.day];
  const actions = t(`actions.${state.role}.${k}`);
  $('#panel').innerHTML = `
    <section class="hero-risk risk risk--${k}" aria-live="polite">
      <div class="hero-risk__date">${t('live.fireRisk')} · ${esc(fmtDate(ds.meta.dates[state.day], { weekday: 'short', day: 'numeric', month: 'short' }).toLocaleUpperCase(locale()))}</div>
      <h1 class="hero-risk__place">${esc(sel.name)}</h1>
      <div class="hero-risk__coords">${sel.lat.toFixed(2)}° N, ${sel.lon.toFixed(2)}° E${sel.pop ? ` · ${t('common.population', { n: fmtNum(sel.pop) })}` : ''}</div>
      ${gaugeSVG(k)}
      <div class="gauge__status">${t(`levels.${k}.tag`)}</div>
      <div class="gauge__sub">${esc(t('live.danger', { level: levelName(k).toLocaleUpperCase(locale()) }))} · ${t('live.score', { s: fmtScore(score) })}</div>
      <p class="hero-risk__meaning">${t(`levels.${k}.meaning`)}</p>
      <p class="muted small" style="text-align:center;margin-top:6px">${esc(sel.note)}</p>
    </section>
    <section class="card weather" id="weather" aria-live="polite"><div class="weather__title"><span>${t('live.weatherTitle')}</span><span>${t('live.loading')}</span></div></section>
    <section aria-labelledby="days-h"><h2 class="section-label" id="days-h">${ds.id === 'live' ? t('live.next7') : t('live.days7')}</h2>
      <div class="days">${ds.meta.dates.map((iso, i) => { const kk = sel.keys[i]; return `<button type="button" class="day" data-day="${i}" aria-pressed="${i === state.day}" aria-label="${esc(fmtDate(iso, { weekday: 'long', day: 'numeric', month: 'long' }))}: ${levelName(kk)}">${esc(dayLabel(ds, i))}<span class="chip risk risk--${kk}" aria-hidden="true">${LEVEL_ICON[kk]}</span><small>${esc(fmtDate(iso, { day: '2-digit', month: '2-digit' }))}</small></button>`; }).join('')}</div></section>
    <section aria-labelledby="todo-h"><h2 class="section-label" id="todo-h">${t('live.whatToDo')}</h2>
      <div class="tabs" role="tablist">${ROLES.map(r => `<button class="tab" role="tab" data-role="${r}" aria-selected="${r === state.role}">${t(`live.roles.${r}`)}</button>`).join('')}</div>
      <ul class="checklist" role="tabpanel">${actions.map((a, i) => { const id = `${state.role}:${k}:${i}`; return `<li><label class="check"><input type="checkbox" data-check="${id}" ${state.checked.has(id) ? 'checked' : ''}>${esc(a)}</label></li>`; }).join('')}</ul></section>
    <div class="row-2"><button class="btn btn--soft" id="listen" type="button">${ICON.speaker}${t('live.listen')}</button><button class="btn btn--soft" id="share" type="button">${ICON.share}${t('live.share')}</button></div>
    <a class="btn btn--green btn--block" target="_blank" rel="noopener" href="${waLink(sel.name, k)}">${ICON.chat}${t('live.whatsapp')}</a>
    <a class="emergency" href="tel:112">${ICON.phone}${t('live.callSmoke')} <b>112</b></a>
    <a class="text-link" href="#/science">${t('live.dataBehind')}</a>`;
  $('#guide-grid').innerHTML = LEVEL_ORDER.map(x => levelCard(x, x === k)).join('');
  $$('.day').forEach(b => b.addEventListener('click', () => { state.day = +b.dataset.day; currentRefresh(); updateLive(); }));
  $$('.tab').forEach(b => b.addEventListener('click', () => { state.role = b.dataset.role; persist(); updateLive(); $(`.tab[data-role="${state.role}"]`).focus(); }));
  $$('[data-check]').forEach(c => c.addEventListener('change', () => { c.checked ? state.checked.add(c.dataset.check) : state.checked.delete(c.dataset.check); persist(); }));
  $('#listen').addEventListener('click', () => listen(sel.name, k));
  $('#share').addEventListener('click', () => openShare(sel.name, k));
  mapApi.select(sel.lat, sel.lon, { zoom: moveMap ? (first ? 8 : Math.max(mapApi.map.getZoom() || 8, 8)) : null });
  loadWeather(sel);
}

const shareUrl = () => `${location.href.split('#')[0]}#/live`;
const shareText = (place, k) => t('live.waText', { place, level: levelName(k), tag: t(`levels.${k}.tag`).toLocaleLowerCase(locale()), meaning: t(`levels.${k}.meaning`), url: shareUrl() });
const waLink = (place, k) => `https://wa.me/?text=${encodeURIComponent(shareText(place, k))}`;

let weatherCtl;
async function loadWeather(sel) {
  weatherCtl?.abort(); weatherCtl = new AbortController();
  const box = $('#weather');
  if (state.dsId !== 'live') { box.innerHTML = `<div class="weather__title"><span>${t('live.weatherTitle')}</span><span>${t('live.weatherHindcast')}</span></div>`; return; }
  try {
    const w = await getCurrentWeather(sel.lat, sel.lon, { signal: weatherCtl.signal });
    if (!box.isConnected) return;
    box.innerHTML = `<div class="weather__title"><span>${esc(t('live.weatherNow', { place: sel.name }))}</span><span>${esc(t('live.weatherBy', { time: `${(w.time || '').slice(11, 16)} ${w.timezone}` }))}</span></div>
      <div class="weather__item"><b>${Math.round(w.temperature)}°C</b><span>${t('live.temp')}</span></div>
      <div class="weather__item"><b>${Math.round(w.humidity)}%</b><span>${t('live.humidity')}</span></div>
      <div class="weather__item"><b>${Math.round(w.wind)} km/h</b><span>${t('live.wind')}</span></div>`;
  } catch (err) {
    if (err.name === 'AbortError' || !box.isConnected) return;
    box.innerHTML = `<div class="weather__title"><span>${t('live.weatherTitle')}</span><span>${t('live.weatherError')}</span></div>`;
  }
}

function listen(place, k) {
  const text = t('live.spoken', { place, level: levelName(k), meaning: t(`levels.${k}.meaning`), first: t(`actions.${state.role}.${k}`)[0] });
  if (!('speechSynthesis' in window)) { toast(t('live.toastNoSpeech'), ICON.speaker); return; }
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text); u.lang = locale();
  speechSynthesis.speak(u);
  toast(t('live.toastReading'), ICON.speaker);
}

function nearMe(ds) {
  if (!('geolocation' in navigator)) { toast(t('live.toastNoGeo'), ICON.pin); return; }
  toast(t('live.toastFinding'), ICON.pin);
  navigator.geolocation.getCurrentPosition(pos => {
    const { latitude: la, longitude: lo } = pos.coords;
    const near = ds.nearest(la, lo);
    const inside = ds.cellAt(la, lo) >= 0;
    state.sel = inside ? { kind: 'point', lat: la, lon: lo } : { kind: 'town', name: near.s.name };
    persist(); updateLive(true);
    toast(inside ? t('live.toastUsing', { town: near.s.name }) : t('live.toastOutside', { town: near.s.name }), ICON.pin);
  }, () => toast(t('live.toastBlocked'), ICON.pin), { timeout: 8000, maximumAge: 600000 });
}

function bindSearch(ds) {
  const q = $('#q'), list = $('#results');
  const byPop = [...ds.settlements].sort((a, b) => b.pop - a.pop);
  let items = [], active = -1;
  const close = () => { list.hidden = true; q.setAttribute('aria-expanded', 'false'); active = -1; };
  const draw = () => {
    const term = fold(q.value.trim());
    items = (term ? byPop.filter(s => fold(s.name).includes(term)).sort((a, b) => (fold(a.name).startsWith(term) ? 0 : 1) - (fold(b.name).startsWith(term) ? 0 : 1)) : byPop).slice(0, 8);
    list.innerHTML = `<div class="dropdown__label">${term ? t('live.matching') : t('live.suggested')}</div>` + (items.length
      ? items.map((s, i) => { const k = levelKey(s.mean[state.day]); return `<button type="button" class="dropdown__item" role="option" id="opt-${i}" aria-selected="${i === active}" data-i="${i}">${ICON.pin}<span>${esc(s.name)}<small>${t('common.population', { n: fmtNum(s.pop) })} · ${levelName(k)}</small></span></button>`; }).join('')
      : `<p class="muted small" style="padding:8px 10px">${esc(t('live.noMatch', { q: q.value }))}</p>`);
    list.hidden = false; q.setAttribute('aria-expanded', 'true');
    if (active >= 0) q.setAttribute('aria-activedescendant', `opt-${active}`); else q.removeAttribute('aria-activedescendant');
    $$('.dropdown__item', list).forEach(b => b.addEventListener('mousedown', e => { e.preventDefault(); pick(+b.dataset.i); }));
  };
  const pick = i => { const s = items[i]; if (!s) return; state.sel = { kind: 'town', name: s.name }; persist(); close(); q.value = ''; q.blur(); updateLive(true); };
  q.addEventListener('focus', draw);
  q.addEventListener('input', () => { active = -1; draw(); });
  q.addEventListener('blur', () => setTimeout(close, 120));
  q.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); active = Math.min(items.length - 1, active + 1); draw(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); active = Math.max(0, active - 1); draw(); }
    else if (e.key === 'Enter') { e.preventDefault(); pick(active >= 0 ? active : 0); }
    else if (e.key === 'Escape') close();
  });
}

/* ------------------------------------------------------------------ Science */
async function renderScience() {
  const ds = DS[state.dsId];
  if (state.sciDay == null || state.sciDay >= ds.days) state.sciDay = ds.todayIdx;
  app.innerHTML = `${topbar('science')}
  <main id="main" class="wrap">
    <h1 class="visually-hidden">${t('science.title')}</h1>
    <section class="kpis" id="kpis"></section>
    <div class="sci">
      <section class="card mapcard" aria-label="${t('science.layerClass')}">
        <div class="layers" role="group">${[['class', 'layerClass'], ['score', 'layerScore'], ['fwi', 'layerFwi']].map(([k, l]) => `<button type="button" class="layer" data-layer="${k}" aria-pressed="${k === state.layer}">${t(`science.${l}`)}</button>`).join('')}</div>
        <div class="lmap lmap--tall" id="map"></div>
        <div class="map-tools">${ds.fires.length ? `<label><input type="checkbox" id="t-fires" ${state.showFires ? 'checked' : ''}><span class="fire-dot"></span>${t('live.showFires')}</label>` : ''}
          <label><input type="checkbox" id="t-low" ${state.showLow ? 'checked' : ''}>${t('live.showLow')}</label></div>
        <div class="legend" id="sci-legend"></div>
      </section>
      <section class="card detail" id="detail" aria-live="polite"></section>
    </div>
    <div class="charts">
      <section class="card chart"><h2 style="font-size:18px">${t('science.chartTitle')}</h2><p class="muted small">${t('science.chartSub')}</p><div class="chart__cols" id="chart"></div>
        <div class="legend" style="margin-top:10px">${['moderate', 'high', 'extreme'].map(k => `<span><span class="dot risk risk--${k}"></span> ${levelName(k)}</span>`).join('')}</div></section>
      <section class="card chart"><h2 style="font-size:18px">${t('science.tableTitle')}</h2><p class="muted small">${t('science.tableSub')}</p>
        <table class="table"><thead><tr><th scope="col">${t('science.thPlace')}</th><th scope="col">${t('science.thClass')}</th><th scope="col" class="num">${t('science.thScore')}</th></tr></thead><tbody id="tbody"></tbody></table></section>
    </div>
    <section class="card model"><h2 style="font-size:18px">${t('science.modelTitle')}</h2>
      <div class="model__grid">${[['m1', '0.915'], ['m2', '58.5 %'], ['m3', '0.010']].map(([k, v]) => `<div class="card kpi"><div class="kpi__label">${t(`science.${k}`)}</div><div class="kpi__value">${v}</div><div class="kpi__note">${t(`science.${k}n`)}</div></div>`).join('')}</div>
      <div class="model__grid"><div><b>${t('science.method')}</b><p class="muted small">${t('science.methodText')}</p></div>
        <div><b>${t('science.sources')}</b><ul>${t('science.sourceList').map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
        <div><b>${t('science.limits')}</b><ul>${t('science.limitList').map(x => `<li>${esc(x)}</li>`).join('')}</ul></div></div></section>
  </main>${appFooter()}`;
  bindChrome();
  mapApi = createMap($('#map'), { dark: isDark(), onClick: ll => { state.sciSel = { lat: ll.lat, lon: ll.lng }; updateScience(); } });
  mapApi.fit(ds);
  currentRefresh = () => {
    mapApi.setRisk(ds, state.sciDay, { mode: state.layer, showLow: state.showLow, attribution: t('common.mapAttribution') });
    if (ds.fires.length) { mapApi.setFires(ds.fires, firePopup); mapApi.showFires(state.showFires); }
  };
  currentRefresh();
  $$('.layer').forEach(b => b.addEventListener('click', () => { state.layer = b.dataset.layer; $$('.layer').forEach(x => x.setAttribute('aria-pressed', x === b)); currentRefresh(); updateScience(); }));
  $('#t-fires')?.addEventListener('change', e => { state.showFires = e.target.checked; mapApi.showFires(state.showFires); });
  $('#t-low').addEventListener('change', e => { state.showLow = e.target.checked; currentRefresh(); });
  updateScience();
}

function updateScience() {
  const ds = DS[state.dsId], d = state.sciDay, kp = ds.kpis[d];
  const dateTxt = fmtDate(ds.meta.dates[d], { weekday: 'short', day: 'numeric', month: 'short' });
  const modUp = kp.moderate + kp.high + kp.extreme, hiUp = kp.high + kp.extreme;
  $('#kpis').innerHTML = [
    [t('science.kpiModerate'), fmtNum(modUp), t('science.kpiModerateNote', { date: dateTxt, n: fmtNum(kp.land_cells) })],
    [t('science.kpiHigh'), fmtNum(hiUp), t('science.kpiHighNote', { share: fmtNum(hiUp / kp.land_cells, { style: 'percent', maximumFractionDigits: 1 }) })],
    [t('science.kpiFwi'), fmtNum(kp.mean_fwi), t('science.kpiFwiNote', { max: fmtNum(kp.max_fwi) })],
    [t('science.kpiFires'), fmtNum(ds.fires.length), ds.fires.length ? t('science.kpiFiresNote') : '—'],
  ].map(([l, v, n]) => `<div class="card kpi"><div class="kpi__label">${esc(l)}</div><div class="kpi__value">${esc(v)}</div><div class="kpi__note">${esc(n)}</div></div>`).join('');

  $('#sci-legend').innerHTML = state.layer === 'fwi'
    ? `<span class="muted small">FWI <span style="display:inline-block;width:140px;height:8px;border-radius:4px;vertical-align:middle;background:linear-gradient(90deg,#fff7bc,#fec44f,#fe9929,#d95f0e,#993404)"></span> 0 → 38+</span>`
    : LEVEL_ORDER.map(k => `<span><span class="dot risk risk--${k}"></span> ${levelName(k)} ${SCORE_LABEL[k]}</span>`).join('');

  const det = $('#detail');
  const k = state.sciSel ? ds.cellAt(state.sciSel.lat, state.sciSel.lon) : -1;
  if (k < 0) {
    det.innerHTML = `<h2 style="font-size:18px">${t('science.cellDetail')}</h2><p class="muted small">${t('science.clickCell')}</p>`;
    mapApi.select(null);
  } else {
    const c = ds.cellCenter(k), near = ds.nearest(c.lat, c.lon), cls = LEVEL_ORDER[ds.classIdx(k, d)], shap = ds.shapAt(k);
    const total = shap.reduce((a, b) => a + b, 0) || 1;
    det.innerHTML = `<h2 style="font-size:18px">${t('science.cellDetail')}</h2>
      <div class="detail__row"><b>${esc(near.s.name)} · ${fmtNum(Math.round(near.km))} km</b><span class="chip risk risk--${cls}">${LEVEL_ICON[cls]} ${levelName(cls)}</span></div>
      <div class="detail__row"><span>${t('science.score')}</span><b>${fmtScore(ds.score(k, d))}</b></div>
      <div class="detail__row"><span>${t('science.fwi')}</span><b>${fmtNum(ds.fwiAt(k, d))}</b></div>
      <div class="detail__row"><span>${t('science.coords')}</span><b>${c.lat.toFixed(3)}° N, ${c.lon.toFixed(3)}° E</b></div>
      <h3 class="section-label" style="margin-top:10px">${t('science.drivers')}</h3>
      <div class="bars">${ds.meta.shap_groups.map((g, i) => { const pct = Math.round((shap[i] / total) * 100); return `<div class="bar"><span>${t(`science.groups.${g}`)}</span><span class="bar__track"><span class="bar__fill" style="width:${pct}%"></span></span><b class="num">${pct} %</b></div>`; }).join('')}</div>`;
    mapApi.select(c.lat, c.lon);
  }

  const max = Math.max(...ds.kpis.map(x => x.moderate + x.high + x.extreme), 1);
  $('#chart').innerHTML = ds.kpis.map((x, i) => { const tot = x.moderate + x.high + x.extreme; return `<button type="button" class="chart__col" data-sday="${i}" aria-pressed="${i === d}" aria-label="${esc(fmtDate(ds.meta.dates[i], { day: 'numeric', month: 'short' }))}: ${tot}">
      <span class="chart__num">${fmtNum(tot)}</span><span class="chart__stack" style="height:${(tot / max) * 80}%">${[['moderate', x.moderate], ['high', x.high], ['extreme', x.extreme]].map(([kk, v]) => (v ? `<span style="flex:${v};background:${LEVEL_COLOR[kk]}"></span>` : '')).join('')}</span>${esc(fmtDate(ds.meta.dates[i], { day: '2-digit', month: '2-digit' }))}</button>`; }).join('');
  $$('[data-sday]').forEach(b => b.addEventListener('click', () => { state.sciDay = +b.dataset.sday; currentRefresh(); updateScience(); }));

  const rows = [...ds.settlements].sort((a, b) => b.mean[d] - a.mean[d]).slice(0, 10);
  $('#tbody').innerHTML = rows.map(s => { const kk = levelKey(s.mean[d]); return `<tr tabindex="0" data-open="${esc(s.name)}"><td>${esc(s.name)}</td><td><span class="chip risk risk--${kk}">${LEVEL_ICON[kk]} ${levelName(kk)}</span></td><td class="num">${fmtScore(s.mean[d])}</td></tr>`; }).join('');
  $$('[data-open]').forEach(r => {
    const open = () => { state.sel = { kind: 'town', name: r.dataset.open }; state.day = d; persist(); location.hash = '#/live'; };
    r.addEventListener('click', open); r.addEventListener('keydown', e => { if (e.key === 'Enter') open(); });
  });
}

/* ------------------------------------------------------------------ Reports */
let rankedCache = [];
async function renderReports() {
  const ds = DS.live;
  app.innerHTML = `${topbar('reports', false)}
  <main id="main" class="wrap">
    <div class="rep-head"><div style="display:grid;gap:6px"><h1 class="h-section">${t('reports.title')}</h1><p class="lede">${t('reports.lede')}</p>
      ${CONFIG.REPORTS_API ? '' : `<p class="muted small">${t('reports.demoNote')}</p>`}</div>
      <button class="btn btn--coral" type="button" data-report>${t('landing.reportBtn')}</button></div>
    <div class="rep-filters">
      <div class="seg" role="group">${[['all', 'filterAll'], ['emergency', 'filterEmergency'], ['verified', 'filterVerified'], ['pending', 'filterPending'], ['mine', 'filterMine']].map(([k, l]) => `<button type="button" class="seg__btn" data-filter="${k}" ${state.repFilter === k ? 'aria-current="page"' : ''}>${t(`reports.${l}`)}</button>`).join('')}</div>
      <label class="small muted">${t('reports.sortLabel')} <select class="select" id="rep-sort">${[['priority', 'sortPriority'], ['newest', 'sortNewest'], ['verified', 'sortVerified']].map(([k, l]) => `<option value="${k}" ${state.repSort === k ? 'selected' : ''}>${t(`reports.${l}`)}</option>`).join('')}</select></label>
      <span class="small muted" id="rep-count"></span>
    </div>
    <div class="rep-layout">
      <div><ul class="rep-list" id="rep-list"></ul>
        <details class="card how" style="margin-top:12px"><summary>${t('reports.howTitle')}</summary><ul>${t('reports.howList').map(x => `<li>${esc(x)}</li>`).join('')}</ul></details></div>
      <div class="card mapcard"><div class="lmap lmap--tall" id="map"></div></div>
    </div>
  </main>${appFooter()}`;
  bindChrome();
  mapApi = createMap($('#map'), { dark: isDark() });
  mapApi.fit(ds);
  currentRefresh = () => { mapApi.setRisk(ds, ds.todayIdx, { mode: 'class', attribution: t('common.mapAttribution') }); if (rankedCache.length) drawReports(); };
  currentRefresh();
  $$('[data-filter]').forEach(b => b.addEventListener('click', () => { state.repFilter = b.dataset.filter; $$('[data-filter]').forEach(x => (x === b ? x.setAttribute('aria-current', 'page') : x.removeAttribute('aria-current'))); drawReports(); }));
  $('#rep-sort').addEventListener('change', e => { state.repSort = e.target.value; drawReports(); });
  rankedCache = rank(await loadReports(), ds);
  drawReports();
}

function drawReports() {
  let list = [...rankedCache];
  const rankOf = new Map(list.map((r, i) => [r.id, i + 1]));
  const f = state.repFilter;
  if (f === 'emergency') list = list.filter(r => r.emergency);
  if (f === 'verified') list = list.filter(r => r.status === 'verified');
  if (f === 'pending') list = list.filter(r => r.status === 'unverified');
  if (f === 'mine') list = list.filter(r => r.mine);
  if (state.repSort === 'newest') list.sort((a, b) => a.ageMin - b.ageMin);
  if (state.repSort === 'verified') list.sort((a, b) => b.v - a.v);
  $('#rep-count').textContent = t('reports.count', { n: fmtNum(list.length) });
  const statusBadge = r => (r.status === 'verified' ? `<span class="badge badge--ok">✓ ${t('reports.verified')}</span>` : r.status === 'likely' ? `<span class="badge badge--warn">${t('reports.likely')}</span>` : r.status === 'quarantined' ? `<span class="badge badge--danger">${t('reports.quarantined')}</span>` : `<span class="badge">${t('reports.unverified')}</span>`)
    + (r.verifier ? ` <span class="badge">${esc(t('reports.photoCheck', { badge: t(`reports.badges.${r.verifier.badge}`), score: fmtNum(r.verifier.trust_score) }))}</span>` : '');
  $('#rep-list').innerHTML = list.length ? list.map(r => {
    const place = r.near.s ? r.near.s.name : (r.address ? t('reports.unknownPlace', { text: r.address }) : t('reports.noLocation'));
    const typeName = t(`reports.types.${r.type}`);
    const c = r.checks;
    const checkItems = [
      ['photo', c.photo], ['gps', c.gps], ['time', c.time], ['unique', c.unique],
      ['ai', c.ai, { p: r.ai == null ? '—' : fmtNum(r.ai, { style: 'percent' }) }], ['trust', c.trust, { p: fmtNum(r.trust ?? 0, { style: 'percent' }) }],
      ['corroborated', c.corroborated, { n: r.others }], ['satellite', c.satellite],
    ];
    const why = [t('reports.why.type', { type: typeName }), r.riskK ? t('reports.why.risk', { level: levelName(r.riskK) }) : null, t('reports.why.recent', { ago: fmtAgo(r.ageMin * 60000) }), r.near.s ? t('reports.why.town', { km: fmtNum(Math.round(r.near.km)), town: r.near.s.name }) : null, t('reports.why.checks', { n: r.passed })].filter(Boolean).join(' · ');
    return `<li class="card rep ${state.repActive === r.id ? 'is-active' : ''}" id="rep-${r.id}" style="--pc:${priorityColor(r.priority)}">
      <div class="rep__top"><span class="rep__rank">#${rankOf.get(r.id)}</span>
        <div><div class="rep__title">${esc(typeName)} · ${esc(place)}</div><div class="rep__meta">${esc(fmtAgo(r.ageMin * 60000))}${r.riskK ? ` · <span class="dot risk risk--${r.riskK}"></span> ${levelName(r.riskK)}` : ''}</div></div>
        <div class="rep__score"><b>${r.priority}</b><span>${t('reports.priority')}</span></div></div>
      <div class="rep__badges">${r.emergency ? `<span class="badge badge--danger">● ${t('reports.emergency')}</span>` : ''}${statusBadge(r)}${r.mine ? `<span class="badge">${t('reports.mine')}</span>` : ''}</div>
      <div class="meter"><span>${t('reports.urgency')}</span><span class="meter__track"><span class="meter__fill" style="width:${r.u}%;background:${priorityColor(r.u)}"></span></span><b>${r.u}</b></div>
      <div class="meter"><span>${t('reports.verification')}</span><span class="meter__track"><span class="meter__fill" style="width:${r.v}%;background:var(--action-green)"></span></span><b>${r.v}</b></div>
      <ul class="rep__checks">${checkItems.map(([k, ok, vars]) => `<li class="${ok ? 'ok' : ''}">${esc(t(`reports.checks.${k}`, vars))}</li>`).join('')}</ul>
      <p class="rep__why"><b>${t('reports.whyTitle')}:</b> ${esc(why)}</p>
      <div class="rep__actions">${r.lat != null ? `<button type="button" class="btn btn--soft" data-show="${r.id}">${ICON.pin}${t('reports.showOnMap')}</button>` : ''}
        ${r.emergency ? `<a class="btn btn--coral" href="tel:112">${ICON.phone}${t('reports.call')}</a>` : ''}
        ${r.mine && !CONFIG.REPORTS_API ? `<button type="button" class="btn btn--outline" data-remove="${r.id}">${t('reports.remove')}</button>` : ''}</div>
    </li>`;
  }).join('') : `<li class="card how">${t('reports.empty')}</li>`;
  mapApi.setReports(list, {
    color: r => priorityColor(r.priority),
    label: r => `#${rankOf.get(r.id)} · ${esc(t(`reports.types.${r.type}`))} · ${r.priority}`,
    onPick: r => focusReport(r.id, false),
  });
  $$('[data-show]').forEach(b => b.addEventListener('click', () => focusReport(b.dataset.show, true)));
  $$('[data-remove]').forEach(b => b.addEventListener('click', async () => { removeLocal(b.dataset.remove); rankedCache = rank(await loadReports(), DS.live); drawReports(); }));
}
function focusReport(id, fly) {
  state.repActive = id;
  const r = rankedCache.find(x => x.id === id);
  $$('.rep').forEach(el => el.classList.toggle('is-active', el.id === `rep-${id}`));
  if (r?.lat != null) mapApi.select(r.lat, r.lon, { zoom: fly ? 10 : null });
  if (!fly) $(`#rep-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

/* ------------------------------------------------------------------ Landing */
async function renderLanding(scrollTo) {
  const ds = DS.live, d = ds.todayIdx;
  const top = [...ds.settlements].sort((a, b) => b.mean[d] - a.mean[d])[0];
  const k = levelKey(top.mean[d]);
  const projects = t('landing.projects');
  const money = [[31240, 50000, 812], [52600, 80000, 1204], [7450, 12000, 301]];
  const usd = n => fmtNum(n, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
  app.innerHTML = `
  <header class="l-nav"><div class="wrap">
    <a class="brand" href="#/"><span class="brand__logo">${ICON.flame}</span><span class="brand__name">#BizdenBize</span></a>
    <nav class="l-nav__links" aria-label="Sections">${[['live-map', 'map'], ['danger', 'danger'], ['report', 'report'], ['help', 'help'], ['regrown', 'learn']].map(([id, k2]) => `<a href="#${id}" data-scroll>${t(`landing.nav.${k2}`)}</a>`).join('')}<a href="#/reports">${t('common.reports')}</a></nav>
    <div class="l-nav__end">${controls()}<button class="btn btn--coral" type="button" data-report>${t('landing.reportBtn')}</button></div>
  </div></header>
  <main id="main">
    <section class="hero"><div class="wrap">
      <p class="hero__kicker">${t('landing.kicker')}</p><h1 class="hero__title">FIREPROOF</h1><p class="hero__lede">${t('landing.lede')}</p>
      <div class="hero__ctas"><a class="btn btn--white" href="#/live">${t('landing.seeRisk')}</a><button class="btn btn--coral" type="button" data-report>${t('landing.reportBtn')}</button></div>
    </div>${heroArt()}</section>

    <section class="l-sec l-sec--bg" id="live-map"><div class="wrap l-split">
      <div style="display:grid;gap:16px">
        <p class="eyebrow">${t('landing.mapEyebrow')}</p><h2 class="h-section">${t('landing.mapTitle')}</h2><p class="lede">${t('landing.mapLede')}</p>
        <div class="card place-card risk risk--${k}"><p class="hero-risk__date">${esc(t('landing.highestToday', { date: fmtDate(ds.meta.dates[d], { weekday: 'short', day: 'numeric', month: 'short' }).toLocaleUpperCase(locale()) }))}</p>
          <b style="font-size:26px">${esc(top.name)}</b><span class="hero-risk__coords">${top.lat.toFixed(2)}° N, ${top.lon.toFixed(2)}° E · ${t('live.score', { s: fmtScore(top.mean[d]) })}</span>
          <div class="place-card__level"><span style="font-size:28px" aria-hidden="true">${LEVEL_ICON[k]}</span><div><b>${levelName(k)}</b><small style="font-weight:700">${t(`levels.${k}.tag`)}</small></div></div><span>${t(`levels.${k}.meaning`)}</span></div>
        <div class="btn-row"><a class="btn btn--primary" href="#/live" data-open-top>${t('landing.openMap')}</a><a class="btn btn--outline" href="#/science">${t('landing.seeData')}</a></div>
      </div>
      <div class="card" style="padding:8px"><div class="lmap" id="map" style="height:460px"></div></div>
    </div></section>

    <section class="l-sec l-sec--surface" id="danger"><div class="wrap">
      <p class="eyebrow">${t('landing.dangerEyebrow')}</p><h2 class="h-section">${t('landing.dangerTitle')}</h2><p class="lede">${t('landing.dangerLede')}</p>
      <div class="l-grid-4">${LEVEL_ORDER.map(x => levelCard(x, x === k)).join('')}</div></div></section>

    <section class="l-sec l-sec--navy" id="report"><div class="wrap">
      <p class="eyebrow" style="color:var(--brand-coral)">${t('landing.reportEyebrow')}</p><h2 class="h-section">${t('landing.reportTitle')}</h2><p class="lede">${t('landing.reportLede')}</p>
      <div class="btn-row"><button class="btn btn--coral" type="button" data-report>${t('landing.reportBtn')}</button><a class="btn btn--white" href="tel:112">${ICON.phone}${t('landing.callFirst')}</a></div>
      <p class="muted">${t('landing.otherChannels')} <a href="https://wa.me/" target="_blank" rel="noopener">WhatsApp</a> · <a href="https://t.me/" target="_blank" rel="noopener">Telegram</a> · <a href="sms:">SMS</a></p></div></section>

    <section class="l-sec l-sec--surface"><div class="wrap l-split">
      <div style="display:grid;gap:16px"><p class="eyebrow">${t('landing.verifiedEyebrow')}</p><h2 class="h-section">${t('landing.verifiedTitle')}</h2><p class="lede">${t('landing.verifiedLede')}</p>
        <div class="btn-row"><a class="btn btn--outline" href="#/reports">${t('landing.seeReports')}</a></div></div>
      <ul class="rep-list" id="top-reports" style="margin:0"></ul>
    </div></section>

    <section class="l-sec l-sec--cream" id="help"><div class="wrap">
      <p class="eyebrow">${t('landing.helpEyebrow')}</p><h2 class="h-section">${t('landing.helpTitle')}</h2><p class="lede">${t('landing.helpLede')}</p>
      <div class="l-grid-3">${projects.map((p, i) => { const [r, g, n] = money[i]; return `<article class="card project"><span class="project__loc">${esc(p.loc)}</span><h3>${esc(p.title)}</h3><p class="muted">${esc(p.text)}</p>
        <div class="progress" role="progressbar" aria-valuenow="${Math.round(r / g * 100)}" aria-valuemin="0" aria-valuemax="100"><span style="width:${r / g * 100}%"></span></div>
        <span><b>${t('landing.raised', { r: usd(r) })}</b> <span class="muted small">${t('landing.ofGoal', { g: usd(g), n: fmtNum(n) })}</span></span>
        <div class="amounts" role="group">${[5, 10, 25, 50].map(a => `<button type="button" class="amount" data-p="${i}" data-a="${a}" aria-pressed="${a === 10}">${usd(a)}</button>`).join('')}</div>
        <button type="button" class="btn btn--green btn--block" data-donate="${i}">${t('landing.donate', { a: usd(10) })}</button></article>`; }).join('')}</div></div></section>

    <section class="l-sec l-sec--surface" id="regrown"><div class="wrap">
      <p class="eyebrow" style="color:var(--action-green)">${t('landing.regrownEyebrow')}</p><h2 class="h-section">${t('landing.regrownTitle')}</h2><p class="lede">${t('landing.regrownLede')}</p>
      <div class="tabs" role="tablist" style="max-width:560px">${[['goals', 'tabGoals'], ['tr', 'tabLearnTr'], ['id', 'tabLearnId']].map(([k2, l]) => `<button class="tab" role="tab" data-learn="${k2}" aria-selected="${state.learnTab === k2}" aria-controls="learn-panel">${t(`landing.${l}`)}</button>`).join('')}</div>
      <div id="learn-panel" role="tabpanel"></div></div></section>
  </main>
  <footer class="l-footer"><div class="wrap">
    <div><b style="font-size:20px;color:var(--on-chrome)">#BizdenBize</b><p>${t('landing.footerAbout')}</p></div>
    <div><h4>${t('landing.footerEmergency')}</h4>${t('landing.footerTr')} <a href="tel:112">112</a><br>${esc(t('landing.footerId', { n: '112' }))}</div>
    <div><h4>${t('landing.footerData')}</h4>NASA FIRMS · Copernicus EFFIS<br>Open-Meteo · OpenStreetMap<br>CARTO · OGM</div>
    <div class="l-footer__base"><span>${t('landing.footerDisclaimer')}</span><span>© 2026 #BizdenBize · COP31 Climate Tech Creathon</span></div>
  </div></footer>`;
  bindChrome();
  $$('[data-scroll]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); $(a.getAttribute('href')).scrollIntoView({ behavior: 'smooth' }); }));
  $('[data-open-top]').addEventListener('click', () => { state.dsId = 'live'; state.sel = { kind: 'town', name: top.name }; state.day = null; persist(); });
  $$('.amount').forEach(b => b.addEventListener('click', () => {
    $$(`.amount[data-p="${b.dataset.p}"]`).forEach(x => x.setAttribute('aria-pressed', x === b));
    $(`[data-donate="${b.dataset.p}"]`).textContent = t('landing.donate', { a: usd(+b.dataset.a) });
  }));
  $$('[data-donate]').forEach(b => b.addEventListener('click', () => toast(t('landing.donateDemo'))));
  $$('[data-learn]').forEach(b => b.addEventListener('click', () => { state.learnTab = b.dataset.learn; $$('[data-learn]').forEach(x => x.setAttribute('aria-selected', x === b)); drawLearn(); }));
  drawLearn();

  mapApi = createMap($('#map'), { dark: isDark(), interactive: false });
  mapApi.fit(ds);
  currentRefresh = () => { mapApi.setRisk(ds, d, { mode: 'class', attribution: t('common.mapAttribution') }); mapApi.setTowns(ds, d, null, townLabel); };
  currentRefresh();
  mapApi.map.on('click', () => { location.hash = '#/live'; });

  const ranked = rank(await loadReports(), ds).slice(0, 3);
  const topBox = $('#top-reports');
  if (topBox) topBox.innerHTML = ranked.map((r, i) => `<li class="card rep" style="--pc:${priorityColor(r.priority)}"><div class="rep__top"><span class="rep__rank">#${i + 1}</span>
    <div><div class="rep__title">${esc(t(`reports.types.${r.type}`))} · ${esc(r.near.s?.name || '')}</div><div class="rep__meta">${esc(fmtAgo(r.ageMin * 60000))}</div></div>
    <div class="rep__score"><b>${r.priority}</b><span>${t('reports.priority')}</span></div></div>
    <div class="rep__badges">${r.emergency ? `<span class="badge badge--danger">● ${t('reports.emergency')}</span>` : ''}${r.status === 'verified' ? `<span class="badge badge--ok">✓ ${t('reports.verified')}</span>` : ''}</div></li>`).join('');
  if (scrollTo) setTimeout(() => $(`#${scrollTo}`)?.scrollIntoView(), 50);
}
function drawLearn() {
  const p = $('#learn-panel');
  if (state.learnTab === 'goals') {
    p.innerHTML = `<div class="stats" style="margin-top:12px">${t('landing.goals').map(([n, l]) => `<div class="stat"><b>${esc(n)}</b>${esc(l)}</div>`).join('')}</div>
      <p class="muted small" style="margin-top:8px">${t('landing.goalsNote')}</p>
      <div class="btn-row" style="margin-top:12px"><button type="button" class="btn btn--green" id="plant">${t('landing.plantTree')}</button></div>`;
    $('#plant').addEventListener('click', () => toast(t('landing.plantDemo')));
  } else {
    p.innerHTML = `<p class="muted" style="margin-top:12px">${t('landing.learnIntro')}</p><div class="learn-grid">${learnCards(state.learnTab)}</div>`;
  }
}
function heroArt() {
  const peaks = Array.from({ length: 16 }, (_, i) => { const x = i * 100; return `M${x - 20},300 L${x + 50},${90 + (i % 3) * 40} L${x + 120},300 Z`; }).join(' ');
  const pines = Array.from({ length: 28 }, (_, i) => { const x = i * 58 + 10, h = 110 + (i % 4) * 30; return `M${x},300 L${x + 18},${300 - h} L${x + 36},300 Z`; }).join(' ');
  return `<svg class="hero__art" viewBox="0 0 1600 300" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
    <path d="M0,180 C300,120 600,200 900,150 C1200,100 1400,170 1600,140 L1600,300 L0,300 Z" fill="rgba(255,255,255,.06)"/>
    <path d="${peaks}" fill="#f4646e"/><path d="${peaks}" fill="#ffd1d4" transform="translate(30 40) scale(.97 1)" opacity=".7"/><path d="${pines}" fill="rgba(0,0,0,.35)"/></svg>`;
}

/* ------------------------------------------------------------------ Report dialog */
let reportLoc = null;
function refreshDialogs() {
  $('#what-toggles').innerHTML = TYPES.map(k => `<button type="button" class="toggle" data-what="${k}" aria-pressed="false">${t(`reports.types.${k}`)}</button>`).join('');
}
function openReport() {
  const dlg = $('#report-dialog');
  dlg.querySelector('form').reset();
  reportLoc = null;
  $('#photo-preview').textContent = t('reportDialog.fileHint');
  $('#loc-box').textContent = t('reportDialog.chooseLoc');
  $('#address').hidden = true;
  $$('#report-dialog .toggle').forEach(x => x.setAttribute('aria-pressed', 'false'));
  dlg.showModal();
}
function initReportDialog() {
  const dlg = $('#report-dialog');
  refreshDialogs();
  dlg.addEventListener('click', e => {
    const tg = e.target.closest('.toggle');
    if (tg) {
      const group = tg.closest('[data-single]');
      if (group) $$('.toggle', group).forEach(x => x.setAttribute('aria-pressed', x === tg));
      else tg.setAttribute('aria-pressed', tg.getAttribute('aria-pressed') !== 'true');
    }
    if (e.target === dlg || e.target.closest('[data-close]')) dlg.close();
  });
  $('#photo').addEventListener('change', e => {
    const f = e.target.files[0];
    $('#photo-preview').textContent = f ? t('reportDialog.fileAdded', { name: f.name, kb: fmtNum(Math.round(f.size / 1024)) }) : t('reportDialog.noFile');
  });
  $('#use-gps').addEventListener('click', () => {
    startCompass(); // camera direction for the verifier's view cone (asks permission on iPhone)
    $('#address').hidden = true;
    if (!navigator.geolocation) { $('#loc-box').textContent = t('reportDialog.noGeo'); return; }
    $('#loc-box').textContent = t('reportDialog.finding');
    navigator.geolocation.getCurrentPosition(
      p => { reportLoc = { lat: p.coords.latitude, lon: p.coords.longitude }; $('#loc-box').textContent = t('reportDialog.yourLoc', { lat: reportLoc.lat.toFixed(3), lon: reportLoc.lon.toFixed(3) }); },
      () => { $('#loc-box').textContent = t('reportDialog.locBlocked'); });
  });
  $('#use-address').addEventListener('click', () => { reportLoc = null; $('#address').hidden = false; $('#address input').focus(); $('#loc-box').textContent = t('reportDialog.addressHint'); });
  dlg.querySelector('form').addEventListener('submit', async e => {
    e.preventDefault();
    const seen = $$('#report-dialog [data-what][aria-pressed="true"]').map(b => b.dataset.what);
    if (!seen.length) { toast(t('reportDialog.needType')); return; }
    const address = $('#address input').value.trim();
    if (!reportLoc && !address) { toast(t('reportDialog.needPlace')); return; }
    const type = [...seen].sort((a, b) => TYPE_WEIGHT[b] - TYPE_WEIGHT[a])[0];
    const fd = new FormData(e.target);
    const r = {
      id: `local-${Date.now()}`, type, types: seen, createdAt: Date.now(), mine: true,
      lat: reportLoc?.lat ?? null, lon: reportLoc?.lon ?? null, address: reportLoc ? '' : address,
      // photo GPS/time/repost/AI checks are only known once the verifier has run
      photo: $('#photo').files.length > 0, gps: false, time: false, unique: false, ai: null, trust: 0.5,
      name: fd.get('name'), phone: fd.get('phone'),
    };
    const submitBtn = dlg.querySelector('button[type=submit]');
    const file = $('#photo').files[0];
    if (file && reportLoc && verifierEnabled()) {
      submitBtn.disabled = true;
      toast(t('reportDialog.verifying'));
      try {
        const near = DS.live.nearest(reportLoc.lat, reportLoc.lon);
        r.verifier = await verifyUpload({ file, lat: reportLoc.lat, lon: reportLoc.lon, region: `${near.s.name}, Türkiye` });
        toast(t('reportDialog.verifyResult', { badge: t(`reports.badges.${r.verifier.badge}`), score: fmtNum(r.verifier.trust_score) }));
      } catch {
        toast(t('reportDialog.verifyFailed'));
      } finally { submitBtn.disabled = false; }
    }
    try {
      await addReport(r);
      dlg.close();
      const ranked = rank(await loadReports(), DS.live);
      const pos = ranked.findIndex(x => x.id === r.id) + 1;
      toast(t('reportDialog.sent', { rank: pos || ranked.length, n: ranked.length }), '', { href: '#/reports', label: t('reportDialog.seeIt') });
      if (location.hash.startsWith('#/reports')) { state.repFilter = 'all'; rankedCache = ranked; drawReports(); focusReport(r.id, true); }
    } catch (err) { toast(String(err.message || err)); }
  });
}

function openShare(place, k) {
  const dlg = $('#share-dialog');
  const text = shareText(place, k);
  $('#share-text').textContent = t('shareDialog.text', { place, level: levelName(k) });
  $('#share-wa').href = waLink(place, k);
  $('#share-sms').href = `sms:?&body=${encodeURIComponent(text)}`;
  $('#share-copy').onclick = async () => { try { await navigator.clipboard.writeText(text); toast(t('shareDialog.copied')); } catch { toast(t('shareDialog.copyFail')); } dlg.close(); };
  $('#share-native').hidden = !navigator.share;
  $('#share-native').onclick = () => navigator.share({ title: '#BizdenBize', text, url: shareUrl() }).catch(() => {});
  dlg.showModal();
}
function initShareDialog() {
  const dlg = $('#share-dialog');
  dlg.addEventListener('click', e => { if (e.target === dlg || e.target.closest('[data-close]')) dlg.close(); });
}

/* ------------------------------------------------------------------ router */
async function route() {
  const path = (location.hash.replace(/^#/, '').split('?')[0]) || '/';
  if (!path.startsWith('/')) return;
  mapApi?.destroy(); mapApi = null; currentRefresh = null;
  try {
    DS.live = await loadDataset('live');
    if (state.dsId === 'hindcast') DS.hindcast = await loadDataset('hindcast');
  } catch (err) {
    app.innerHTML = `<main class="wrap" style="padding:40px 0"><h1 class="h-section">#BizdenBize</h1><p class="lede" style="margin-top:12px">${esc(t('common.loadError', { file: err.file || err.message }))}</p><p style="margin-top:12px"><a class="emergency" href="tel:112">${ICON.phone} 112</a></p></main>`;
    return;
  }
  if (path === '/live') await renderLive();
  else if (path === '/science') await renderScience();
  else if (path === '/reports') await renderReports();
  else if (path === '/learn') { if (state.learnTab === 'goals') state.learnTab = 'tr'; await renderLanding('regrown'); }
  else await renderLanding();
  const titles = { '/live': 'common.citizen', '/science': 'common.science', '/reports': 'common.reports' };
  document.title = titles[path] ? `${t(titles[path])} · #BizdenBize` : `#BizdenBize — ${t('common.brandSub')}`;
  if (path !== '/learn') window.scrollTo(0, 0);
}

(async function start() {
  await setLang(initialLang());
  applyStatic();
  initReportDialog();
  initShareDialog();
  window.addEventListener('hashchange', route);
  await route();
})();
