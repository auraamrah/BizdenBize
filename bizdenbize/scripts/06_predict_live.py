"""FireBridge — live daily fire-risk map: today + 6 days for all of Türkiye.

1. FWI start values: FFMC/DMC/DC + the last days of all six indices per FWI grid point come from
   data/turkiye/live_state.npz, carried forward by the previous run. With no state (first run), or one
   older than MAX_STATE_AGE days, the script seeds from the latest Copernicus CEMS
   `intermediate_dataset` day on EWDS (needs ~/.cdsapirc, like 03_fwi_turkiye.py).
2. Weather: Open-Meteo hourly forecast (no key) at the same grid points, from the state day to +6 days.
   The FWI system is run forward with firebridge_fwi (checked against CEMS by 06b_check_fwi_calibration.py).
3. Model: `model_live` from models/fire_lgbm_turkiye.joblib (trained on 2021-2025 by 05 --export).
4. Active fires: NASA FIRMS VIIRS near-real-time hotspots of the last FIRMS_DAYS days, if the
   FIRMS_MAP_KEY environment variable (or a line FIRMS_MAP_KEY=... in <JUKUT>/.env) is set.
5. Output: bizdenbize/dashboard/data.live.json (same schema as data.json + meta.mode = "live").

Run once a day, e.g. Windows Task Scheduler at 06:00:  .venv\\Scripts\\python.exe bizdenbize\\scripts\\06_predict_live.py
"""
import datetime as dt
import io
import json
import os
import sys
import time

import joblib
import numpy as np
import pandas as pd
import requests
import xarray as xr

import firebridge_core as fb
import firebridge_fwi as F
from firebridge_core import CELL, LAT0, LAT1, LON0, LON1, NCOLS, NROWS, PILOT, ROOT, TRD

sys.stdout.reconfigure(encoding="utf-8")
STATE = TRD / "live_state.npz"
OUT = ROOT / "bizdenbize/dashboard/data.live.json"
HIST_DAYS, FORECAST_DAYS, MAX_STATE_AGE, FIRMS_DAYS = 8, 7, 60, 2
INDICES = ["fwi", "ffmc", "dmc", "dc", "isi", "bui"]
GRIB = {"fwinx": "fwi", "ffmcode": "ffmc", "dufmcode": "dmc", "drtcode": "dc", "infsinx": "isi", "fbupinx": "bui"}
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:5.0f}s]", *a, flush=True)


bundle = joblib.load(ROOT / "models/fire_lgbm_turkiye.joblib")
model, use_hist = bundle["model_live"], bundle["use_history"]
cell_pt, plat, plon = bundle["cell_pt"], bundle["fwi_point_lat"], bundle["fwi_point_lon"]
cells, static = fb.load_cells()
NC, NP = len(cells), len(plat)
today = pd.Timestamp(dt.date.today())


# ------------------------------------------------------------------ 1) start values
def seed_from_ewds():
    """Latest HIST_DAYS days of CEMS intermediate FWI at the model's grid points."""
    import cdsapi
    from scipy.spatial import cKDTree
    months = sorted({(d.year, d.month) for d in pd.date_range(today - pd.Timedelta(days=40), today)})
    tmp = TRD / "live_seed.grib"
    frames = []
    for y, m in months:
        cdsapi.Client(quiet=True).retrieve("cems-fire-historical-v1", {
            "product_type": "reanalysis", "variable": [
                "fire_weather_index", "drought_code", "fine_fuel_moisture_code", "duff_moisture_code",
                "initial_fire_spread_index", "build_up_index"],
            "system_version": ["4_1"], "dataset_type": "intermediate_dataset",
            "year": [str(y)], "month": [f"{m:02d}"], "day": [f"{d:02d}" for d in range(1, 32)],
            "grid": "original_grid", "area": [42.4, 25.5, 35.7, 45.0], "data_format": "grib"}, str(tmp))
        frames.append(xr.open_dataset(tmp, engine="cfgrib", backend_kwargs={"indexpath": ""}).load())
    ds = xr.concat(frames, dim="time").sortby("time").isel(time=slice(-HIST_DAYS, None))
    lon = ds.longitude.values
    _, k = cKDTree(np.column_stack([ds.latitude.values, np.where(lon > 180, lon - 360, lon)])).query(
        np.column_stack([plat, plon]))
    hist = {v: ds[g].values[:, k].astype(np.float32) for g, v in GRIB.items()}
    return pd.DatetimeIndex(ds.time.values), hist


state = np.load(STATE, allow_pickle=True) if STATE.exists() else None
if state is not None and (today - pd.Timestamp(str(state["date"]))).days <= MAX_STATE_AGE:
    hist_dates = pd.DatetimeIndex(state["dates"])
    hist = {v: state[v] for v in INDICES}
    log("start values from live_state.npz, last day", hist_dates[-1].date())
else:
    hist_dates, hist = seed_from_ewds()
    log("start values from CEMS intermediate dataset, last day", hist_dates[-1].date())
last = hist_dates[-1]

# ------------------------------------------------------------------ 2) weather + FWI forward
past = (today - last).days + 1
dates, wx = F.fetch_noon_weather(plat, plon, past_days=min(max(past, 1), 92), forecast_days=FORECAST_DAYS)
keep = dates > last
dates, wx = dates[keep], {k: v[keep] for k, v in wx.items()}
log(f"Open-Meteo: {len(dates)} days ({dates[0].date()}..{dates[-1].date()}) at {NP} points")
for k in wx:                                                       # rare gaps: carry the previous day
    wx[k] = pd.DataFrame(wx[k]).ffill().bfill().values
calc = F.run(wx, dates.month.values, {k: hist[k][-1] for k in ("ffmc", "dmc", "dc")})
cal = json.loads((TRD / "fwi_calibration.json").read_text()) if (TRD / "fwi_calibration.json").exists() else None
if cal and cal["apply"]:
    for k, c in cal["linear"].items():
        calc[k] = np.maximum(c["slope"] * calc[k] + c["intercept"], 0).astype(np.float32)
    log("applied linear FWI calibration")

series_dates = hist_dates.append(dates)
raw = {v: np.vstack([hist[v], calc[v]]) for v in INDICES}
W = fb.weather_features(raw, series_dates)

# carry state forward to yesterday (forecast days are not stored)
obs = series_dates < today
np.savez(STATE, date=str(series_dates[obs][-1].date()), dates=series_dates[obs][-HIST_DAYS:].values,
         **{v: raw[v][obs][-HIST_DAYS:] for v in INDICES})

# ------------------------------------------------------------------ 3) predict
out_days = pd.DatetimeIndex([d for d in series_dates if d >= today][:FORECAST_DAYS])
if not len(out_days):
    sys.exit("no forecast days returned by Open-Meteo")
if (out_days.month < 4).any():
    log("WARNING: Jan-Mar is outside the Apr-Dec season the model was trained on")
tday = series_dates.get_indexer(out_days)
c = np.tile(np.arange(NC), len(tday))
t = np.repeat(tday, NC)
X = fb.build_features(W, cell_pt, static, series_dates, c, t, bundle["hist_live"], use_hist)
prob = model.predict_proba(X)[:, 1]
score = fb.fwi_ceiling(fb.to_score(prob, bundle["risk_cuts_live"]), X.fwi.values)
shap = fb.shap_group_pct(model.booster_, X, c, NC, use_hist)
log("risk classes per day (cells):")
for j, d in enumerate(out_days):
    s = score[j * NC:(j + 1) * NC]
    print(" ", d.date(), dict(pd.cut(s, [-1, .30, .55, .75, 2], labels=fb.CLASSES).value_counts().sort_index()))


# ------------------------------------------------------------------ 4) FIRMS active fires
def firms_key():
    if os.environ.get("FIRMS_MAP_KEY"):
        return os.environ["FIRMS_MAP_KEY"].strip()
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("FIRMS_MAP_KEY="):
                return line.split("=", 1)[1].strip()
    return None


def persistent_spots():
    """~100 m spots that 'burn' on >= 10 days in the 2021-2026 archive (factories, flares, landfills)."""
    p = TRD / "persistent_spots.csv"
    if not p.exists():
        df = pd.read_csv(DATA_HS, usecols=["acq_at_s", "lat", "lon"])
        spot = df.lat.round(3).astype(str) + "," + df.lon.round(3).astype(str)
        n = df.assign(spot=spot, d=df.acq_at_s.str[:10]).groupby("spot").d.nunique()
        pd.Series(n[n >= 10].index, name="spot").to_csv(p, index=False)
    return set(pd.read_csv(p).spot)


DATA_HS = ROOT / "data/a29cb7c7d8004c7c81778ad1bd237a5b.csv"
active = []
key = firms_key()
if key:
    try:
        rows = []
        for src in ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"):
            url = (f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{src}/"
                   f"{LON0},{LAT0},{LON1},{LAT1}/{FIRMS_DAYS}")
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            if r.text.startswith("latitude"):
                rows.append(pd.read_csv(io.StringIO(r.text)))
        hs = pd.concat(rows) if rows else pd.DataFrame(columns=["latitude", "longitude", "confidence"])
        hs = hs[hs.confidence.astype(str).str.lower().isin(["n", "h", "nominal", "high"])]
        spot = hs.latitude.round(3).astype(str) + "," + hs.longitude.round(3).astype(str)
        hs = hs[~spot.isin(persistent_spots())]
        hs["ix"] = np.floor((hs.longitude - LON0) / CELL).astype(int)
        hs["iy"] = np.floor((hs.latitude - LAT0) / CELL).astype(int)
        hs = hs.merge(cells[["ix", "iy"]].reset_index().rename(columns={"index": "cell"}), on=["ix", "iy"])
        veg = (static.wc_tree.fillna(0) + static.wc_shrub.fillna(0)).values[hs.cell.values]
        nb = hs.groupby(["ix", "iy"]).size()
        burst = np.array([sum(nb.get((x + dx, y + dy), 0) for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                          for x, y in zip(hs.ix, hs.iy)])
        hs["wild"] = (veg >= 0.3) | (burst >= 8)
        active = [[round(a, 3), round(b, 3), str(d), int(w)]
                  for a, b, d, w in zip(hs.longitude, hs.latitude, hs.acq_date, hs.wild)]
        log(f"FIRMS: {len(active)} hotspots in land cells, {int(hs.wild.sum())} look like wildfires")
    except Exception as e:                                # the map is still useful without hotspots
        log("FIRMS failed:", e)
else:
    log("FIRMS_MAP_KEY not set: no active-fire layer")

# ------------------------------------------------------------------ 5) dashboard JSON
base = json.loads((TRD / "dashboard_base.json").read_text(encoding="utf-8"))
fwi_days, risk_days = [], []
for j in range(len(out_days)):
    sl = slice(j * NC, (j + 1) * NC)
    fwi_days.append(np.round(X.fwi.values[sl], 1).tolist())
    risk_days.append(np.round(score[sl], 3).tolist())
lc = static[["wc_tree", "wc_shrub", "wc_crop", "wc_built"]].fillna(0).values
dash = {
    "meta": {"project": "FireBridge", "demo": False, "mode": "live",
             "generated_at": dt.datetime.now().isoformat(timespec="minutes"),
             "dates": [d.strftime("%Y-%m-%d") for d in out_days],
             "bbox": [LON0, LAT0, LON1, LAT1], "cell": CELL, "ncols": NCOLS, "nrows": NROWS,
             "pilot_bbox": list(PILOT), "coverage": "turkiye", "groups": list(fb.groups(use_hist)),
             "risk_classes": [[0.0, "Rendah"], [0.3, "Sedang"], [0.55, "Tinggi"], [0.75, "Ekstrem"]],
             "note": ("Prakiraan langsung: FWI dihitung dari cuaca Open-Meteo (nilai awal Copernicus CEMS), "
                      "risiko dari LightGBM yang dilatih pada kebakaran hutan 2021-2025. Titik api aktif: NASA "
                      "FIRMS VIIRS. Jalan/permukiman: OpenStreetMap. Tutupan lahan: ESA WorldCover. "
                      "Elevasi & lereng: Copernicus DEM. Kelas dibatasi oleh tingkat bahaya FWI hari itu "
                      "(FWI < 5,2 maks. rendah; < 11,2 maks. sedang; < 21,3 maks. tinggi).")},
    "cells": {"ix": cells.ix.tolist(), "iy": cells.iy.tolist(),
              "dist_road": static.dist_road_km.round(1).tolist(), "dist_set": static.dist_set_km.round(1).tolist(),
              "elev": static.elev_m.round(0).fillna(0).astype(int).tolist(),
              "slope": static.slope_mean.round(1).fillna(0).tolist(),
              "landcover": np.where(lc.max(axis=1) >= 0.2, lc.argmax(axis=1), 4).tolist(),
              "shap": shap.T.tolist(), "fwi": fwi_days, "risk": risk_days},
    "roads": base["roads"], "settlements": base["settlements"], "fires": base["fires"],
    "active_fires": active,
}
OUT.write_text(json.dumps(dash, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
log(f"{OUT.name}: {OUT.stat().st_size // 1024} KB, days {dash['meta']['dates'][0]}..{dash['meta']['dates'][-1]}")
