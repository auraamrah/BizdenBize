"""FireBridge — Tahap 2-4 for the whole of Türkiye: features, LightGBM, evaluation, dashboard export.

Same method as main.ipynb (pilot Antalya-Muğla), scaled to ~31k land cells x 1,528 days (~47M cell-days):
  * weather features are kept per FWI grid point ([day, point] arrays) and gathered per cell on demand,
    so the full cell-day table is never held in memory;
  * training uses every fire cell-day + a random NEG_RATE share of non-fire cell-days, with the sampled
    negatives weighted 1/NEG_RATE (equivalent in expectation to training on all rows);
  * evaluation uses every land cell-day of the held-out year.
Splits as in the pilot: tune on train 2021-23 / val 2024, test 2025 (train 2021-24),
hindcast 2021 (train 2022-25) — the hindcast model drives the 27 Jul - 2 Aug 2021 dashboard week.

Inputs : data/turkiye/{cells,static_human,static_landcover,fire_pos}.csv  (04_grid_labels_turkiye.py)
         data/turkiye/fwi_tr_<year>.grib                                   (03_fwi_turkiye.py)
Outputs: models/fire_lgbm_turkiye.joblib, models/metrics_turkiye.csv,
         bizdenbize/dashboard/data.json (pilot version kept as data.pilot.json)
"""
import json
import shutil
import sys
import time
from pathlib import Path

import geopandas as gpd
import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import shapely
import xarray as xr
from scipy.ndimage import convolve
from scipy.spatial import cKDTree
from shapely.geometry import box
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
DATA, TRD = ROOT / "data", ROOT / "data" / "turkiye"
ZIP = DATA / "turkey-latest-free.shp.zip"
LON0, LAT0, LON1, LAT1, CELL = 25.5, 35.8, 44.9, 42.3, 0.05
NCOLS, NROWS = int(round((LON1 - LON0) / CELL)), int(round((LAT1 - LAT0) / CELL))
PILOT = (27.2, 36.0, 32.4, 37.7)
NEG_RATE = 0.05
RNG = np.random.default_rng(0)
T0 = time.time()
sys.stdout.reconfigure(encoding="utf-8")       # region names (Muğla) on a Windows console


def log(*a):
    print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


# ============================================================== Tahap 1: load + align
cells = pd.read_csv(TRD / "cells.csv")
static = (cells[["ix", "iy"]].merge(pd.read_csv(TRD / "static_human.csv"), on=["ix", "iy"], how="left")
          .merge(pd.read_csv(TRD / "static_landcover.csv"), on=["ix", "iy"], how="left"))
NC = len(cells)

ds = xr.concat([xr.open_dataset(p, engine="cfgrib", backend_kwargs={"indexpath": ""})
                for p in sorted(TRD.glob("fwi_tr_*.grib"))], dim="time").sortby("time")
GRIB = {"fwinx": "fwi", "ffmcode": "ffmc", "dufmcode": "dmc", "drtcode": "dc", "infsinx": "isi", "fbupinx": "bui"}
times = pd.DatetimeIndex(ds.time.values)
raw = {v: ds[k].values.astype(np.float32) for k, v in GRIB.items()}        # [T, P]
valid = ~np.isnan(raw["fwi"]).all(axis=0)
lon = ds.longitude.values
pts = np.column_stack([ds.latitude.values, np.where(lon > 180, lon - 360, lon)])
_, k = cKDTree(pts[valid]).query(cells[["lat_c", "lon_c"]].values)
point = np.flatnonzero(valid)[k]
used, cell_pt = np.unique(point, return_inverse=True)                       # cell -> column in W arrays
log(f"cells {NC} | days {len(times)} ({times[0].date()}..{times[-1].date()}) | FWI points used {len(used)}")

# weather features per point; rolling windows per year so they never bridge the Dec->Apr gap
W = {v: a[:, used] for v, a in raw.items()}
fw = pd.DataFrame(W["fwi"], index=times)
yr = times.year
roll = lambda f: fw.groupby(yr).transform(f).values.astype(np.float32)
W["fwi_mean3"] = roll(lambda s: s.shift(1).rolling(3, min_periods=1).mean())
W["fwi_mean7"] = roll(lambda s: s.shift(1).rolling(7, min_periods=1).mean())
W["fwi_max7"] = roll(lambda s: s.shift(1).rolling(7, min_periods=1).max())
dcf = pd.DataFrame(W["dc"], index=times)
W["dc_change7"] = (dcf - dcf.groupby(yr).shift(7)).values.astype(np.float32)
DOY = times.day_of_year.values.astype(np.float32)
del raw, ds

# labels: positive (cell, day) pairs
pos = pd.read_csv(TRD / "fire_pos.csv", parse_dates=["date"])
cid = pd.Series(np.arange(NC), index=pd.MultiIndex.from_arrays([cells.ix, cells.iy]))
tid = pd.Series(np.arange(len(times)), index=times)
pos = pos[pos.date.isin(times)]
pos_c = cid.loc[list(zip(pos.ix, pos.iy))].values
pos_t = tid.loc[pos.date].values
POS_KEY = np.sort(pos_t.astype(np.int64) * NC + pos_c)
YEAR_T = times.year.values
log("positive cell-days in FWI span:", len(POS_KEY))
print(pd.Series(YEAR_T[pos_t]).value_counts().sort_index().to_string())

# ============================================================== Tahap 2: features
WEATHER = ["fwi", "ffmc", "dmc", "dc", "isi", "bui", "fwi_mean3", "fwi_mean7", "fwi_max7", "dc_change7", "doy"]
HUMAN = ["dist_road_km", "dist_set_km", "dist_farm_km", "road_km_per_cell"]
HISTORY = ["hist_cell", "hist_nb"]
ENV = ["lc_forest", "lc_shrub", "lc_agri", "lc_urban"]
GROUPS = {"cuaca": WEATHER, "manusia": HUMAN, "histori": HISTORY, "lingkungan": ENV}
FEATURES = WEATHER + HUMAN + HISTORY + ENV
S = {c: static[c].values.astype(np.float32) for c in HUMAN + ENV}


def history_from(years):
    """Fire-days per year in each cell and its 3x3 neighbourhood, counted over `years`."""
    m = np.isin(YEAR_T[pos_t], years)
    cnt = np.bincount(pos_c[m], minlength=NC).astype(np.float32)
    g = np.zeros((NROWS, NCOLS), np.float32)
    g[cells.iy, cells.ix] = cnt
    nb = convolve(g, np.ones((3, 3), np.float32), mode="constant")[cells.iy, cells.ix]
    return np.vstack([cnt, nb]) / max(len(years), 1)


def hist_for(train_years):
    """Leakage-safe: a training year sees only the *other* training years, any other year sees all of them."""
    return {y: history_from([t for t in train_years if t != y]) for y in np.unique(YEAR_T)}


def features(c, t, hist):
    X = {v: W[v][t, cell_pt[c]] for v in WEATHER if v != "doy"}
    X["doy"] = DOY[t]
    X.update({k: S[k][c] for k in HUMAN + ENV})
    h = np.empty((2, len(c)), np.float32)
    ty = YEAR_T[t]
    for y, hy in hist.items():
        m = ty == y
        h[:, m] = hy[:, c[m]]
    X["hist_cell"], X["hist_nb"] = h
    return pd.DataFrame(X)[FEATURES]


def label(c, t):
    key = t.astype(np.int64) * NC + c
    i = np.searchsorted(POS_KEY, key)
    return (POS_KEY[np.minimum(i, len(POS_KEY) - 1)] == key).astype(np.int8)


def sample_set(years, hist, rate=NEG_RATE):
    """All positives of `years` + a `rate` share of the other cell-days (weight 1/rate)."""
    ts = np.flatnonzero(np.isin(YEAR_T, years))
    n = int(rate * NC * len(ts))
    c_n, t_n = RNG.integers(0, NC, n), RNG.choice(ts, n)
    keep = label(c_n, t_n) == 0
    m = np.isin(YEAR_T[pos_t], years)
    c = np.concatenate([pos_c[m], c_n[keep]])
    t = np.concatenate([pos_t[m], t_n[keep]])
    y = np.concatenate([np.ones(m.sum(), np.int8), np.zeros(keep.sum(), np.int8)])
    w = np.where(y == 1, 1.0, 1.0 / rate)
    return features(c, t, hist), y, w


def full_year(year, hist):
    ts = np.flatnonzero(YEAR_T == year)
    c, t = np.tile(np.arange(NC), len(ts)), np.repeat(ts, NC)
    return features(c, t, hist), label(c, t), c, t


# ============================================================== Tahap 3: model
def scores(y, p):
    prec, rec, _ = precision_recall_curve(y, p)
    f1 = (2 * prec * rec / np.clip(prec + rec, 1e-12, None)).max()
    top = p >= np.quantile(p, 0.95)
    return {"PR-AUC": average_precision_score(y, p), "ROC-AUC": roc_auc_score(y, p),
            "best F1": f1, "api di top 5%": y[top].sum() / y.sum(), "positif": int(y.sum())}


def fit_lgbm(X, y, w, Xv=None, yv=None, wv=None, n_estimators=3000, **params):
    m = lgb.LGBMClassifier(n_estimators=n_estimators, learning_rate=0.03, subsample=0.8, subsample_freq=1,
                           colsample_bytree=0.8, min_child_samples=200, reg_lambda=1.0, verbose=-1, **params)
    if Xv is None:
        return m.fit(X, y, sample_weight=w)
    return m.fit(X, y, sample_weight=w, eval_set=[(Xv, yv)], eval_sample_weight=[wv],
                 eval_metric="average_precision", callbacks=[lgb.early_stopping(150, verbose=False)])


def predict(model, X, chunk=2_000_000):
    return np.concatenate([model.predict_proba(X.iloc[i:i + chunk])[:, 1] for i in range(0, len(X), chunk)])


# split A tuning: train 2021-23, early-stop on a sampled 2024, score on the full 2024
h_a = hist_for([2021, 2022, 2023])
Xtr, ytr, wtr = sample_set([2021, 2022, 2023], h_a)
Xvs, yvs, wvs = sample_set([2024], h_a)
Xva, yva, cva, _ = full_year(2024, h_a)
spw = (wtr[ytr == 0].sum()) / ytr.sum()
log(f"train rows {len(ytr):,} (positives {ytr.sum():,}, effective neg/pos {spw:.0f}) | val 2024 rows {len(yva):,}")
best = None
for leaves in (15, 63, 255):
    for sw in (1.0, np.sqrt(spw)):
        m = fit_lgbm(Xtr, ytr, wtr, Xvs, yvs, wvs, num_leaves=leaves, scale_pos_weight=sw)
        ap = average_precision_score(yva, predict(m, Xva))
        log(f"num_leaves={leaves} scale_pos_weight={sw:.0f} trees={m.best_iteration_} val PR-AUC={ap:.4f}")
        if best is None or ap > best[0]:
            best = (ap, leaves, sw != 1.0, m.best_iteration_)
_, LEAVES, SPW_SQRT, N_IT = best
log("terbaik:", best)


def train_all(years, hist):
    X, y, w = sample_set(years, hist)
    lr = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                       LogisticRegression(class_weight="balanced", max_iter=2000))
    lr.fit(X, y, logisticregression__sample_weight=w)
    r = w[y == 0].sum() / y.sum()
    gbm = fit_lgbm(X, y, w, n_estimators=int(N_IT * 1.1), num_leaves=LEAVES,
                   scale_pos_weight=np.sqrt(r) if SPW_SQRT else 1.0)
    return lr, gbm


in_pilot = ((cells.lon_c >= PILOT[0]) & (cells.lon_c < PILOT[2]) &
            (cells.lat_c >= PILOT[1]) & (cells.lat_c < PILOT[3])).values


def report(X, y, c, lr, gbm, name):
    p_lr, p_gb = predict(lr, X), predict(gbm, X)
    rows = []
    for region, m in [("Türkiye", slice(None)), ("pilot Antalya-Muğla", in_pilot[c]), ("luar pilot", ~in_pilot[c])]:
        for model, p in [("FWI saja", X.fwi.values), ("Regresi logistik", p_lr), ("LightGBM", p_gb)]:
            rows.append({"set": name, "region": region, "model": model, **scores(y[m], p[m])})
    return rows, p_gb


rows = report(Xva, yva, cva, *train_all([2021, 2022, 2023], h_a), "val 2024")[0]
del Xva, Xtr, Xvs

h_test = hist_for([2021, 2022, 2023, 2024])
lr_a, model_a = train_all([2021, 2022, 2023, 2024], h_test)
X25, y25, c25, _ = full_year(2025, h_test)
r, p25 = report(X25, y25, c25, lr_a, model_a, "test 2025")
rows += r
log("test 2025 done")

h_hind = hist_for([2022, 2023, 2024, 2025])
lr_b, model_b = train_all([2022, 2023, 2024, 2025], h_hind)
X21, y21, c21, t21 = full_year(2021, h_hind)
r, p21 = report(X21, y21, c21, lr_b, model_b, "hindcast 2021")
rows += r
metrics = pd.DataFrame(rows).set_index(["set", "region", "model"])
(ROOT / "models").mkdir(exist_ok=True)
metrics.round(4).to_csv(ROOT / "models/metrics_turkiye.csv")
with pd.option_context("display.width", 200, "display.max_rows", 100):
    print(metrics.round(3).to_string())

# SHAP group shares on test 2025
idx = RNG.choice(len(y25), 200_000, replace=False)
contrib = pd.DataFrame(model_a.booster_.predict(X25.iloc[idx], pred_contrib=True)[:, :-1], columns=FEATURES)


def group_share(cn):
    g = pd.Series({k: cn[v].abs().sum(axis=1).mean() for k, v in GROUPS.items()})
    return (100 * g / g.sum()).round(1)


top = p25[idx] >= np.quantile(p25[idx], 0.99)
print(pd.DataFrame({"semua sel (%)": group_share(contrib), "top 1% risiko (%)": group_share(contrib[top])}))
print(contrib.abs().mean().sort_values(ascending=False).round(4).to_string())
del X25

# ============================================================== Tahap 4: risk map + dashboard
CLASSES = ["rendah", "sedang", "tinggi", "ekstrem"]
season = np.isin(pd.DatetimeIndex(times[t21]).month, [6, 7, 8, 9])
CUTS = {"probs": np.quantile(p21[season], [0, 0.80, 0.95, 0.99, 1]).tolist(), "scores": [0, 0.30, 0.55, 0.75, 1]}
to_score = lambda prob: np.interp(prob, CUTS["probs"], CUTS["scores"])

joblib.dump({"model": model_a, "model_hindcast_2021": model_b, "features": FEATURES, "groups": GROUPS,
             "risk_cuts": CUTS, "grid": {"bbox": [LON0, LAT0, LON1, LAT1], "cell": CELL},
             "neg_rate": NEG_RATE, "tuned": {"num_leaves": LEAVES, "sqrt_spw": SPW_SQRT, "trees": N_IT}},
            ROOT / "models/fire_lgbm_turkiye.joblib")

days = pd.date_range("2021-07-27", "2021-08-02")
dmask = np.isin(times[t21], days)
Xw, cw, tw = X21[dmask.astype(bool)], c21[dmask], t21[dmask]
score_w = to_score(p21[dmask])
fires_w = y21[dmask]
log("week fires:", int(fires_w.sum()))
print(pd.cut(score_w[fires_w == 1], [-1, 0.30, 0.55, 0.75, 2], labels=CLASSES).value_counts().sort_index())

# per-cell SHAP group shares, averaged over the week (hindcast model)
cw_all = model_b.booster_.predict(Xw, pred_contrib=True)[:, :-1]
gabs = np.column_stack([np.abs(cw_all[:, [FEATURES.index(f) for f in v]]).sum(axis=1) for v in GROUPS.values()])
gcell = np.vstack([np.bincount(cw, weights=gabs[:, j], minlength=NC) for j in range(gabs.shape[1])]).T
shap_pct = np.rint(100 * gcell / gcell.sum(axis=1, keepdims=True)).astype(int)

dash_path = ROOT / "bizdenbize/dashboard/data.json"
old = json.loads(dash_path.read_text(encoding="utf-8"))
pilot_copy = dash_path.with_name("data.pilot.json")
if not pilot_copy.exists() and old["meta"]["bbox"] == list(PILOT):
    shutil.copy(dash_path, pilot_copy)

lc = static[ENV].values
landcover = np.where(lc.max(axis=1) >= 0.05, lc.argmax(axis=1), 4)        # 4 = not mapped in OSM
fwi_days, risk_days = [], []
for d in days:
    m = times[tw] == d
    f, s = np.zeros(NC), np.zeros(NC)
    f[cw[m]], s[cw[m]] = Xw.fwi.values[m], score_w[m]
    fwi_days.append(np.round(f, 1).tolist())
    risk_days.append(np.round(s, 3).tolist())

bbox_poly = box(LON0, LAT0, LON1, LAT1)
roads = gpd.read_file(TRD / "osm_roads.gpkg")
roads = roads[roads.fclass.isin(["motorway", "trunk", "primary"])]
merged = shapely.line_merge(shapely.union_all(roads.geometry.values))
lines = gpd.GeoSeries([merged], crs=4326).explode(index_parts=False).to_crs(3035).simplify(500).to_crs(4326)
road_json = [[[round(x, 3), round(y, 3)] for x, y in g.coords] for g in lines if len(g.coords) > 1 and g.length > 0]
towns = gpd.read_file(TRD / "osm_settlements.gpkg")
towns = towns[towns.fclass.isin(["city", "town"])].copy()
# the Geofabrik extract reaches a little over the land border: keep towns inside the national
# boundary (it includes territorial waters, so coastal towns stay)
admin = gpd.read_file(TRD / "adminareas.gpkg", columns=["fclass"])
towns = towns[towns.within(admin[admin.fclass == "national"].union_all())]
towns["population"] = pd.to_numeric(towns.population, errors="coerce").fillna(0)
towns = towns.sort_values("population", ascending=False)

dash = {
    "meta": {**old["meta"], "demo": False, "bbox": [LON0, LAT0, LON1, LAT1], "cell": CELL,
             "ncols": NCOLS, "nrows": NROWS, "pilot_bbox": list(PILOT), "coverage": "turkiye",
             "groups": list(GROUPS),
             "note": ("Cakupan: seluruh Türkiye (sel 0,05°). FWI: Copernicus CEMS/EFFIS. Risiko: LightGBM dilatih "
                      "2022-2025 (hindcast, 2021 tidak dilihat model). Jalan/permukiman/tutupan lahan: OpenStreetMap. "
                      "Label: EFFIS hotspot VIIRS. Elevasi & lereng belum tersedia.")},
    "cells": {"ix": cells.ix.tolist(), "iy": cells.iy.tolist(),
              "dist_road": static.dist_road_km.round(1).tolist(), "dist_set": static.dist_set_km.round(1).tolist(),
              "elev": [None] * NC, "slope": [None] * NC, "landcover": landcover.tolist(),
              "shap": shap_pct.T.tolist(), "fwi": fwi_days, "risk": risk_days},
    "roads": road_json,
    "settlements": [[n, round(g.x, 3), round(g.y, 3), int(p)]
                    for n, g, p in zip(towns.name, towns.geometry, towns.population) if isinstance(n, str)],
    "fires": old.get("fires", []),
}
dash_path.write_text(json.dumps(dash, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
log(f"data.json: {dash_path.stat().st_size // 1024} KB | cells {NC} | roads {len(road_json)} | "
    f"settlements {len(dash['settlements'])}")
