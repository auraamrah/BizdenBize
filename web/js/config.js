// Site configuration. Everything that changes between deployments lives here.

// Photo/video verifier (bizdenbize/upload_verifier, FastAPI POST /verify).
// Set VERIFIER_URL below, or open the site once with ?verifier=https://your-verifier-url
// (remembered on that device; ?verifier= with no value clears it).
function verifierOverride() {
  try {
    const q = new URLSearchParams(location.search).get('verifier');
    if (q !== null) (q ? localStorage.setItem('bb-verifier', q) : localStorage.removeItem('bb-verifier'));
    return localStorage.getItem('bb-verifier');
  } catch { return null; }
}

export const CONFIG = {
  // CARTO basemaps key (free tier: 5M tile requests/month non-commercial).
  // It is visible to anyone who opens the site — that is normal for browser map keys.
  // Protect it by limiting the allowed domains/referrers in your CARTO key settings.
  CARTO_KEY: 'cb1_50ld_1_928897c68d453acab257fd5a',

  // Model output, built from bizdenbize/dashboard/data.live.json and data.json by
  // bizdenbize/scripts/web_export.py (run by 05/06 and by the Pages workflow).
  DATA: { live: 'data/live.json', hindcast: 'data/hindcast.json' },

  // Reports backend. null = reports are kept on this device (demo). Set to e.g.
  // 'https://api.bizdenbize.org/reports' to GET the ranked list and POST new reports (see docs/API.md).
  REPORTS_API: null,

  // e.g. 'https://verifier.example.org' (no trailing /verify). null = photo checks show as pending.
  VERIFIER_URL: verifierOverride() || null,

  // Show a warning when the live forecast is older than this.
  STALE_HOURS: 36,
};
