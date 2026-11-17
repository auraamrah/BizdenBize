// Client for the citizen upload verifier (bizdenbize/upload_verifier → POST /verify).
// Follows the verifier's frontend contract: lat/lon from geolocation, optional compass azimuth,
// and tz_offset_min so EXIF capture times (phone-local) can be compared correctly.
import { CONFIG } from './config.js';

let heading = null;
function onOrient(e) {
  const v = e.webkitCompassHeading ?? (e.absolute && e.alpha != null ? (360 - e.alpha) % 360 : null);
  if (v != null && !Number.isNaN(v)) heading = Math.round(v);
}
// Call from a user gesture (iOS asks permission for the compass).
export function startCompass() {
  heading = null;
  // listen right away (events simply don't arrive until allowed), and ask permission where the browser requires it
  window.addEventListener('deviceorientationabsolute', onOrient);
  window.addEventListener('deviceorientation', onOrient);
  if (typeof DeviceOrientationEvent !== 'undefined' && typeof DeviceOrientationEvent.requestPermission === 'function') {
    DeviceOrientationEvent.requestPermission().catch(() => {});
  }
}
export const getHeading = () => heading;
export const verifierEnabled = () => !!CONFIG.VERIFIER_URL;

export async function verifyUpload({ file, lat, lon, region }) {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('lat', String(lat));
  fd.append('lon', String(lon));
  fd.append('region', region);
  if (heading != null) fd.append('azimuth', String(heading));
  fd.append('tz_offset_min', String(-new Date().getTimezoneOffset()));
  const url = `${CONFIG.VERIFIER_URL.replace(/\/+$/, '')}/verify`;
  const res = await fetch(url, { method: 'POST', body: fd, signal: AbortSignal.timeout(120000) });
  if (!res.ok) throw new Error(`verifier ${res.status}`);
  return summarize(await res.json());
}

// Keep only what the website shows (no frame hashes or raw detections).
function summarize(v) {
  const m = v.gates?.meta || {}, cv = v.gates?.cv || {}, env = v.gates?.env || {};
  return {
    trust_score: v.trust_score, badge: v.badge, subscores: v.subscores, fov_cone: v.fov_cone || null,
    exif: !!m.exif_present, gps_km: m.gps_mismatch_km ?? null, age_h: m.age_hours ?? null, repost: !!m.repost,
    cv_conf: cv.max_conf ?? null, flow_up: cv.flow_upward ?? null, firms: env.firms_hits_5km ?? null,
  };
}
