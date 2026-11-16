"""FireBridge — check that FWI computed from Open-Meteo weather matches the Copernicus FWI the model was trained on.

Takes a random sample of FWI grid points, seeds FFMC/DMC/DC with the CEMS values of 1 June 2025, runs
the FWI system on Open-Meteo ERA5 archive weather for June-September 2025, and compares each index with
CEMS (data/turkiye/fwi_tr_2025.grib). Prints correlation and bias, and writes per-index linear corrections
to data/turkiye/fwi_calibration.json, which 06_predict_live.py applies when they are needed.
"""
import json
import sys

import numpy as np
import pandas as pd
import xarray as xr

import firebridge_fwi as F
from firebridge_core import TRD

sys.stdout.reconfigure(encoding="utf-8")
N_POINTS = 80
GRIB = {"fwinx": "fwi", "ffmcode": "ffmc", "dufmcode": "dmc", "drtcode": "dc", "infsinx": "isi", "fbupinx": "bui"}

ds = xr.open_dataset(TRD / "fwi_tr_2025.grib", engine="cfgrib", backend_kwargs={"indexpath": ""})
ds = ds.sel(time=slice("2025-06-01", "2025-09-30"))
valid = np.flatnonzero(~np.isnan(ds["fwinx"].values).any(axis=0))
pts = np.random.default_rng(1).choice(valid, N_POINTS, replace=False)
lat, lon = ds.latitude.values[pts], ds.longitude.values[pts]
lon = np.where(lon > 180, lon - 360, lon)
cems = {v: ds[k].values[:, pts] for k, v in GRIB.items()}
times = pd.DatetimeIndex(ds.time.values)

dates, wx = F.fetch_noon_weather(lat, lon, F.ARCHIVE_URL, start_date="2025-05-31", end_date="2025-09-30")
assert dates[0] == times[0], (dates[0], times[0])
start = {k: cems[k][0] for k in ("ffmc", "dmc", "dc")}
calc = F.run({k: v[1:] for k, v in wx.items()}, dates.month.values[1:], start)

rows, corr = [], {}
for k in ("ffmc", "dmc", "dc", "isi", "bui", "fwi"):
    a, b = calc[k].ravel(), cems[k][1:].ravel()
    m = ~np.isnan(a) & ~np.isnan(b)
    slope, icpt = np.polyfit(a[m], b[m], 1)
    rows.append({"index": k, "r": np.corrcoef(a[m], b[m])[0, 1], "mean Open-Meteo": a[m].mean(),
                 "mean CEMS": b[m].mean(), "bias": (a[m] - b[m]).mean(), "MAE": np.abs(a[m] - b[m]).mean()})
    corr[k] = {"slope": float(slope), "intercept": float(icpt)}
res = pd.DataFrame(rows).set_index("index").round(3)
print(res.to_string())
ok = bool((res.r >= 0.8).all() and (res.bias.abs() <= 0.1 * res["mean CEMS"]).all())
print("calibration needed:", not ok)
(TRD / "fwi_calibration.json").write_text(json.dumps({"apply": not ok, "linear": corr,
                                                      "stats": res.reset_index().to_dict("records")}, indent=1))
