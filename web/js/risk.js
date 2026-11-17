// Loads the model output exported by tools/export_frontend.py and answers questions about it.
import { CONFIG } from './config.js';

const cache = {};
const NO_DATA = 255;

function decode(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
const KM_LAT = 110.57;
export function distKm(lat1, lon1, lat2, lon2) {
  const kx = 111.32 * Math.cos(((lat1 + lat2) / 2) * Math.PI / 180);
  return Math.hypot((lon2 - lon1) * kx, (lat2 - lat1) * KM_LAT);
}

export async function loadDataset(id) {
  if (cache[id]) return cache[id];
  const url = CONFIG.DATA[id];
  const res = await fetch(url, { cache: 'no-cache' });
  if (!res.ok) throw Object.assign(new Error(`${url}: ${res.status}`), { file: url });
  const raw = await res.json();
  const m = raw.meta;
  const [west, south, east, north] = m.bbox;
  const ds = {
    id, meta: m, west, south, east, north,
    risk: raw.risk.map(decode),
    klass: raw.class.map(decode),
    fwi: raw.fwi.map(decode),
    shap: raw.shap.map(decode),
    kpis: raw.kpis,
    fires: raw.active_fires || [],
    refFires: raw.reference_fires || [],
    settlements: raw.settlements.map(([name, lon, lat, pop, mean, max]) => ({ name, lon, lat, pop, mean, max })),
  };
  ds.days = m.dates.length;
  ds.cellAt = (lat, lon) => {
    const ix = Math.floor((lon - west) / m.cell), iy = Math.floor((lat - south) / m.cell);
    if (ix < 0 || iy < 0 || ix >= m.ncols || iy >= m.nrows) return -1;
    const k = iy * m.ncols + ix;
    return ds.klass[0][k] === NO_DATA ? -1 : k;
  };
  ds.cellCenter = k => ({ lat: south + (Math.floor(k / m.ncols) + 0.5) * m.cell, lon: west + ((k % m.ncols) + 0.5) * m.cell });
  ds.score = (k, d) => (k < 0 ? null : ds.risk[d][k] / 250);
  ds.classIdx = (k, d) => (k < 0 ? null : ds.klass[d][k]);
  ds.fwiAt = (k, d) => (k < 0 ? null : ds.fwi[d][k] / 2);
  ds.shapAt = k => ds.shap.map(g => (g[k] === NO_DATA ? 0 : g[k]));
  ds.nearest = (lat, lon) => {
    let best = null, bd = Infinity;
    for (const s of ds.settlements) { const dd = distKm(lat, lon, s.lat, s.lon); if (dd < bd) { bd = dd; best = s; } }
    return { s: best, km: bd };
  };
  ds.byName = name => ds.settlements.find(s => s.name === name);
  // index of "today" in the forecast window (falls back to the first day)
  const todayIso = new Date().toISOString().slice(0, 10);
  ds.todayIdx = Math.max(0, m.dates.indexOf(todayIso));
  // the backend writes local Türkiye time without an offset (e.g. "2026-11-16T16:12"); Türkiye is UTC+3 all year
  const ga = m.generated_at;
  ds.runDate = ga ? new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(ga) ? ga : `${ga.length === 16 ? `${ga}:00` : ga}+03:00`) : null;
  ds.ageHours = ds.runDate ? (Date.now() - ds.runDate.getTime()) / 3.6e6 : null;
  cache[id] = ds;
  return ds;
}
export { NO_DATA };
