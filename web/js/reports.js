// Ground reports: storage + ranking.
// Ranking is transparent on purpose: every point a report gets is listed on its card.
//   priority = 0.6 × urgency + 0.4 × verification   (each 0–100)
import { CONFIG } from './config.js';
import { distKm } from './risk.js';
import { levelKey } from './data.js';

const LS_KEY = 'bb-reports';
export const TYPE_WEIGHT = { flames: 45, smoke: 35, spark: 28, stubble: 18, litter: 6 };
export const TYPES = Object.keys(TYPE_WEIGHT);

// Example reports for the demo, placed where the current model run and NASA FIRMS data make them testable.
// times are relative to page load so the demo always looks current.
const DEMO = [
  { id: 'd1', type: 'flames', lat: 36.741, lon: 36.212, min: 25, photo: true, gps: true, time: true, unique: true, ai: 0.95, trust: 0.93 },
  { id: 'd2', type: 'smoke', lat: 36.748, lon: 36.205, min: 40, photo: true, gps: true, time: true, unique: true, ai: 0.88, trust: 0.71 },
  { id: 'd3', type: 'smoke', lat: 36.571, lon: 32.031, min: 55, photo: true, gps: true, time: true, unique: true, ai: 0.91, trust: 0.98 },
  { id: 'd4', type: 'stubble', lat: 36.402, lon: 33.902, min: 125, photo: true, gps: true, time: true, unique: true, ai: 0.62, trust: 0.9 },
  { id: 'd5', type: 'stubble', lat: 36.946, lon: 35.387, min: 180, photo: true, gps: true, time: true, unique: true, ai: 0.7, trust: 0.8 },
  { id: 'd6', type: 'spark', lat: 36.381, lon: 30.302, min: 300, photo: true, gps: true, time: false, unique: true, ai: 0.3, trust: 0.85 },
  { id: 'd7', type: 'litter', lat: 36.802, lon: 31.452, min: 1440, photo: true, gps: true, time: true, unique: true, ai: 0.05, trust: 0.95 },
  { id: 'd8', type: 'smoke', lat: 36.861, lon: 28.281, min: 540, photo: true, gps: false, time: false, unique: false, ai: 0.9, trust: 0.2 },
  { id: 'd9', type: 'smoke', lat: 38.204, lon: 26.851, min: 35, photo: false, gps: true, time: true, unique: false, ai: null, trust: 0.55 },
  { id: 'd10', type: 'flames', lat: 37.321, lon: 27.791, min: 1200, photo: true, gps: true, time: true, unique: true, ai: 0.93, trust: 0.9 },
  { id: 'd11', type: 'stubble', lat: 38.311, lon: 26.781, min: 360, photo: true, gps: true, time: true, unique: true, ai: 0.55, trust: 0.6 },
  { id: 'd12', type: 'litter', lat: 36.631, lon: 29.121, min: 2880, photo: true, gps: true, time: true, unique: true, ai: 0.02, trust: 0.9 },
];
const loadedAt = Date.now();

function readLocal() { try { return JSON.parse(localStorage.getItem(LS_KEY) || '[]'); } catch { return []; } }
function writeLocal(list) { try { localStorage.setItem(LS_KEY, JSON.stringify(list)); } catch { /* storage full or blocked */ } }

export async function loadReports() {
  if (CONFIG.REPORTS_API) {
    const res = await fetch(CONFIG.REPORTS_API);
    if (!res.ok) throw new Error(`Reports API ${res.status}`);
    return (await res.json()).map(r => ({ ...r, createdAt: new Date(r.createdAt).getTime() }));
  }
  const demo = DEMO.map(r => ({ ...r, createdAt: loadedAt - r.min * 60000, demo: true }));
  return [...demo, ...readLocal()];
}

export async function addReport(r) {
  if (CONFIG.REPORTS_API) {
    const res = await fetch(CONFIG.REPORTS_API, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(r) });
    if (!res.ok) throw new Error(`Reports API ${res.status}`);
    return;
  }
  // personal details (name/phone) are not stored in the demo
  const { name, phone, ...safe } = r; void name; void phone;
  writeLocal([...readLocal(), safe]);
}
export function removeLocal(id) { writeLocal(readLocal().filter(r => r.id !== id)); }

// Score every report. `ds` = live model dataset (for risk at the spot, towns and FIRMS fires).
export function rank(list, ds, now = Date.now()) {
  const day = ds.todayIdx;
  const scored = list.map(r => {
    const hasPlace = r.lat != null;
    const ageMin = (now - r.createdAt) / 60000;
    const near = hasPlace ? ds.nearest(r.lat, r.lon) : { s: null, km: null };
    const cell = hasPlace ? ds.cellAt(r.lat, r.lon) : -1;
    const riskScore = cell >= 0 ? ds.score(cell, day) : null;
    const riskK = riskScore == null ? null : levelKey(riskScore);
    const others = hasPlace ? list.filter(o => o.id !== r.id && o.lat != null && distKm(r.lat, r.lon, o.lat, o.lon) <= 5 && Math.abs(o.createdAt - r.createdAt) <= 6 * 3.6e6).length : 0;
    const satellite = hasPlace && ds.fires.some(([lon, lat]) => distKm(r.lat, r.lon, lat, lon) <= 5);

    const vf = r.verifier;   // result from the upload verifier, when it ran
    const checks = vf ? {
      photo: true,
      gps: vf.gps_km != null && vf.gps_km <= 2,
      time: vf.age_h != null && vf.age_h >= -0.25 && vf.age_h <= 2,
      unique: !vf.repost,
      ai: vf.cv_conf != null && vf.cv_conf >= 0.5,
      trust: (r.trust ?? 0) >= 0.7, corroborated: others > 0, satellite: satellite || (vf.firms ?? 0) > 0,
    } : {
      photo: !!r.photo, gps: !!r.gps, time: !!r.time, unique: !!r.unique,
      ai: r.ai != null && r.ai >= 0.5, trust: (r.trust ?? 0) >= 0.7, corroborated: others > 0, satellite,
    };
    // verifier trust score (0–100) already blends EXIF, repost, YOLO, Gemini and weather/FIRMS;
    // without it, the website estimates verification from what it knows.
    const v = vf ? Math.min(100, Math.round(vf.trust_score + (others ? 7.5 : 0))) : Math.min(100, Math.round(
      (r.photo ? 10 : 0) + (r.gps ? 15 : 0) + (r.time ? 10 : 0) + (r.unique ? 15 : 0) +
      (r.ai ?? 0) * 20 + (r.trust ?? 0) * 15 + (others ? 7.5 : 0) + (satellite ? 7.5 : 0)));

    const riskPts = riskK ? { low: 0, moderate: 8, high: 16, extreme: 24 }[riskK] : 0;
    const townPts = near.km == null ? 0 : near.km <= 5 ? 12 : near.km <= 15 ? 6 : 0;
    const recentPts = ageMin <= 60 ? 19 : ageMin <= 180 ? 12 : ageMin <= 720 ? 6 : ageMin <= 2880 ? 2 : 0;
    const u = Math.min(100, TYPE_WEIGHT[r.type] + riskPts + townPts + recentPts);

    const priority = Math.round(0.6 * u + 0.4 * v);
    const status = vf ? { green: 'verified', amber: 'likely', quarantined: 'quarantined' }[vf.badge] || 'unverified'
      : v >= 70 ? 'verified' : v >= 45 ? 'likely' : 'unverified';
    const emergency = (r.type === 'flames' || r.type === 'smoke') && (status === 'verified' || status === 'likely') && ageMin <= 180;
    return { ...r, ai: vf ? vf.cv_conf : r.ai, ageMin, near, riskScore, riskK, others, satellite, checks, passed: Object.values(checks).filter(Boolean).length, v, u, priority, status, emergency };
  });
  return scored.sort((a, b) => b.priority - a.priority || a.ageMin - b.ageMin);
}

export const priorityColor = p => (p >= 70 ? '#ef4444' : p >= 50 ? '#f97316' : p >= 35 ? '#eab308' : '#8a93a3');
