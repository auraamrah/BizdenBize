# Website (`web/`)

Public site for #BizdenBize: daily fire risk for every 5 km of Türkiye, what to do about it,
a ranked map of citizen reports, and short lessons on what makes forests burn.
Static HTML/CSS/JS — no build step. Live at **https://auraamrah.github.io/BizdenBize/** once Pages is on.

| Route | Page |
|---|---|
| `#/` | Landing · live-map preview · danger levels · report · projects · Regrown (*Our goals · Learn: Türkiye · Learn: Indonesia*) |
| `#/live` | Citizen view: CARTO map + model risk grid, towns, NASA FIRMS fires, search, Near me, 7-day outlook, what to do, listen/share/WhatsApp/112 |
| `#/science` | KPIs, risk class / score / FWI layers, cell detail with SHAP drivers, daily chart, top settlements |
| `#/reports` | Every report ranked by urgency and verification, on a map |

English · Türkçe · Bahasa Indonesia, light and dark mode.

## How it connects to the rest of the repo

```
05_train_turkiye.py --export ──► bizdenbize/dashboard/data.json ─┐
06_predict_live.py ────────────► bizdenbize/dashboard/data.live.json ─┤
                                                                      ▼
                        bizdenbize/scripts/web_export.py ──► web/data/hindcast.json, web/data/live.json
                                                                      ▼
                                                     web/ (GitHub Pages)  ──POST /verify──►  upload_verifier
```

- **Risk data.** `web_export.py` compacts the dashboard JSON (6.6 MB → ~260 KB gzipped) and computes the
  risk class from the full-precision score, so class counts match the model exactly. 05/06 run it at the end
  of every run; the Pages workflow runs it on every deploy. `web/data/` is generated and not committed.
- **Updating the live site:** run `06_predict_live.py`, then commit and push `bizdenbize/dashboard/data.live.json`.
  The workflow `.github/workflows/pages.yml` rebuilds and redeploys automatically.
- **Photo verifier.** When `VERIFIER_URL` is set in `js/config.js` (or the site is opened once with
  `?verifier=https://…`), the report form sends the photo/video, `lat`/`lon`, compass `azimuth` and
  `tz_offset_min` to `POST /verify` (see `bizdenbize/upload_verifier/README.md`). The returned trust score and
  badge (green / amber / quarantined) drive the report's verification score and status, and green uploads show
  their camera view cone on the map. Without a verifier, photo checks show as pending.
  The Pages site is HTTPS, so the verifier needs an HTTPS URL (a cloud host or an HTTPS tunnel to the Mac);
  allowed browser origins are set with `ALLOWED_ORIGINS` (default: the Pages site and `localhost:8080`).
  For a local test use `?verifier=http://127.0.0.1:8000` — uvicorn listens on IPv4 only, and some browsers resolve `localhost` to IPv6.

## Run locally

```bash
python bizdenbize/scripts/web_export.py      # build web/data/ from the committed model output
cd web && python3 -m http.server 8080        # http://localhost:8080  (8000 is the verifier's port)
```

## Turn on GitHub Pages (once)

Settings → Pages → Build and deployment → Source: **GitHub Actions**. Then push to `main`
(or run *Deploy website* from the Actions tab).

## CARTO basemap key

In `js/config.js`. Browser map keys are visible to visitors, so restrict it to
`auraamrah.github.io` (and `localhost` for testing) in the CARTO key settings.

## Editing text

All words are in `locales/en.json`, `tr.json`, `id.json` (same keys in each). Missing keys fall back to English.
Turkish and Indonesian should get a native-speaker review before launch. Learn-card sources are in `js/learn.js`;
cards marked `checked: false` come from team notes and weren't independently re-checked.

## Report ranking

`priority = 0.6 × urgency + 0.4 × verification` (0–100 each; every point is listed on the card).
Urgency = what was seen + model risk at the spot + distance to a town + recency.
Verification = the verifier's trust score when it ran (+7.5 if another report is within 5 km / 6 h);
otherwise an estimate from photo, location, reporter history, nearby reports and NASA FIRMS.
Emergency = flames or smoke, verified or likely real, sent in the last 3 hours.
The starting reports in `js/reports.js` are labelled demo examples; new reports are kept on the
device until a reports API exists (`CONFIG.REPORTS_API`, contract in `docs/API.md`).
