# Data contracts between the backend and the website

## 1. Risk data (`data/live.json`, `data/hindcast.json`)

Produced by `bizdenbize/scripts/web_export.py` from the backend's `data.live.json` / `data.json`.

```jsonc
{
  "meta": {
    "mode": "live",                       // or "hindcast"
    "generated_at": "2026-11-16T16:12",   // Türkiye local time (UTC+3) if no offset is given
    "dates": ["2026-11-16", "..."],       // 7 days
    "bbox": [25.5, 35.8, 44.9, 42.3],     // west, south, east, north
    "cell": 0.05, "ncols": 388, "nrows": 130,
    "thresholds": [0.30, 0.55, 0.75],
    "shap_groups": ["weather", "human", "history", "environment"]
  },
  "risk":  ["<base64>", ...],   // per day: ncols*nrows uint8, value/250 = score (floored), 255 = no land
  "class": ["<base64>", ...],   // per day: 0 low, 1 moderate, 2 high, 3 extreme (from full-precision score), 255 = no land
  "fwi":   ["<base64>", ...],   // per day: value/2 = FWI
  "shap":  ["<base64>", ...],   // per group: percent share
  "settlements": [["Alanya", 32.002, 36.544, 350636, [mean per day], [max per day]], ...],  // within 10 km
  "active_fires": [[lon, lat, "YYYY-MM-DD", flag], ...],   // NASA FIRMS VIIRS
  "kpis": [{"moderate": 0, "high": 0, "extreme": 0, "land_cells": 32971, "mean_fwi": 1.5, "max_fwi": 16.0}, ...]
}
```
Grid index: `k = iy * ncols + ix`, cell south-west corner = `(bbox[1] + iy*cell, bbox[0] + ix*cell)`.

## 2. Reports API (to build on the backend)

Set `CONFIG.REPORTS_API` in `js/config.js` to the endpoint URL.

`GET {REPORTS_API}` → array of reports. `POST {REPORTS_API}` ← one report (JSON). The website ranks them.

```jsonc
{
  "id": "r_123",
  "type": "flames",              // flames | smoke | spark | stubble | litter (most severe of `types`)
  "types": ["flames", "smoke"],
  "createdAt": "2026-11-17T09:41:00+03:00",
  "lat": 36.741, "lon": 36.212,  // null if only `address` is known
  "address": "",
  "photo": true,                 // the server fills the checks below after processing the upload
  "gps": true,                   // EXIF GPS within ~1 km of lat/lon
  "time": true,                  // EXIF time within ~2 h of createdAt
  "unique": true,                // perceptual hash not seen before
  "ai": 0.95,                    // smoke/fire classifier confidence 0–1, null if not run
  "trust": 0.93                  // reporter track record 0–1
}
```
The browser POST includes `name` and `phone` when given; the server should show them only to the
village head (Muhtar) and never return them in `GET`.
