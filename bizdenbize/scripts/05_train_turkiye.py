"""FireBridge — Tahap 2-4 for the whole of Türkiye: features, LightGBM, evaluation, dashboard export.

Same method as main.ipynb (pilot Antalya-Muğla), scaled to ~33k land cells x ~1,500 days:
  * weather features are kept per FWI grid point ([day, point] arrays) and gathered per cell on demand;
  * labels are *wildfire* cell-days (fire_pos_wild.csv); hotspot cell-days that look like agricultural
    burning are dropped from training and evaluation instead of being counted as "no fire";
  * training uses every fire cell-day + a random NEG_RATE share of non-fire cell-days, weighted 1/NEG_RATE;
  * evaluation uses every land cell-day of the held-out year.
Splits: tune on train 2021-23 / val 2024, test 2025 (train 2021-24), hindcast 2021 (train 2022-25,
drives the 27 Jul - 2 Aug 2021 dashboard week), and a final live model trained on 2021-2025.

Usage: python 05_train_turkiye.py [--no-history] [--export]
  --no-history  drop the hist_cell / hist_nb features
  --export      write models/fire_lgbm_turkiye.joblib and bizdenbize/dashboard/data.json
Metrics always go to models/metrics_turkiye_<variant>.csv.
"""
import argparse
import json
import shutil
import sys
import time

import geopandas as gpd
import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import shapely
import xarray as xr
from shapely.geometry import box
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import firebridge_core as fb
from firebridge_core import CELL, LAT0, LAT1, LON0, LON1, NCOLS, NROWS, PILOT, ROOT, TRD

ap = argparse.ArgumentParser()
ap.add_argument("--no-history", action="store_true")
ap.add_argument("--export", action="store_true")
ARGS = ap.parse_args()
USE_HIST = not ARGS.no_history
VARIANT = "hist" if USE_HIST else "nohist"
FEATURES, GROUPS = fb.features_list(USE_HIST), fb.groups(USE_HIST)
NEG_RATE = 0.05
RNG = np.random.default_rng(0)
T0 = time.time()
sys.stdout.reconfigure(encoding="utf-8")       # region names (Muğla) on a Windows console
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*eval_set.*")


def log(*a):
    print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


# ============================================================== Tahap 1: load + align
cells, static = fb.load_cells()
NC = len(cells)
ds = xr.concat([xr.open_dataset(p, engine="cfgrib", backend_kwargs={"indexpath": ""})
                for p in sorted(TRD.glob("fwi_tr_*.grib"))], dim="time").sortby("time")
GRIB = {"fwinx": "fwi", "ffmcode": "ffmc", "dufmcode": "dmc", "drtcode": "dc", "infsinx": "isi", "fbupinx": "bui"}
times = pd.DatetimeIndex(ds.time.values)
raw = {v: ds[k].values.astype(np.float32) for k, v in GRIB.items()}        # [T, P]
valid = np.flatnonzero(~np.isnan(raw["fwi"]).all(axis=0))
k_used, cell_pt = fb.map_cells_to_points(cells, ds.latitude.values[valid], ds.longitude.values[valid])
used = valid[k_used]
W = fb.weather_features({v: a[:, used] for v, a in raw.items()}, times)
log(f"variant {VARIANT} | cells {NC} | days {len(times)} ({times[0].date()}..{times[-1].date()}) | "
    f"FWI points used {len(used)}")
PT_LAT = ds.latitude.values[used]
PT_LON = np.where(ds.longitude.values[used] > 180, ds.longitude.values[used] - 360, ds.longitude.values[used])
del raw, ds

# labels: wildfire (cell, day) pairs; other hotspot cell-days are excluded
lab = pd.read_csv(TRD / "fire_pos_wild.csv", parse_dates=["date"])
lab = lab[lab.date.isin(times)]
cid = pd.Series(np.arange(NC), index=pd.MultiIndex.from_arrays([cells.ix, cells.iy]))
tid = pd.Series(np.arange(len(times)), index=times)
lab_c = cid.loc[list(zip(lab.ix, lab.iy))].values
lab_t = tid.loc[lab.date].values
wild = lab.wild.values == 1
pos_c, pos_t = lab_c[wild], lab_t[wild]
POS_KEY = np.sort(pos_t.astype(np.int64) * NC + pos_c)
EXCL_KEY = np.sort(lab_t[~wild].astype(np.int64) * NC + lab_c[~wild])
YEAR_T = times.year.values
log(f"wildfire cell-days {len(POS_KEY)} | excluded (agricultural-like) {len(EXCL_KEY)}")
print(pd.Series(YEAR_T[pos_t]).value_counts().sort_index().to_string())


# ============================================================== Tahap 2: features
def hist_for(train_years):
    """Leakage-safe: a training year sees only the *other* training years, any other year sees all of them."""
    out = {}
    for y in np.unique(YEAR_T):
        yrs = [t for t in train_years if t != y]
        out[y] = fb.history_from(pos_c[np.isin(YEAR_T[pos_t], yrs)], NC, cells, len(yrs))
    return out


def features(c, t, hist):
    return fb.build_features(W, cell_pt, static, times, c, t, hist, USE_HIST)


def in_keys(keys, c, t):
    key = t.astype(np.int64) * NC + c
    i = np.searchsorted(keys, key)
    return keys[np.minimum(i, len(keys) - 1)] == key


def sample_set(years, hist, rate=NEG_RATE):
    """All positives of `years` + a `rate` share of the other cell-days (weight 1/rate)."""
    ts = np.flatnonzero(np.isin(YEAR_T, years))
    n = int(rate * NC * len(ts))
    c_n, t_n = RNG.integers(0, NC, n), RNG.choice(ts, n)
    keep = ~in_keys(POS_KEY, c_n, t_n) & ~in_keys(EXCL_KEY, c_n, t_n)
    m = np.isin(YEAR_T[pos_t], years)
    c = np.concatenate([pos_c[m], c_n[keep]])
    t = np.concatenate([pos_t[m], t_n[keep]])
    y = np.concatenate([np.ones(m.sum(), np.int8), np.zeros(keep.sum(), np.int8)])
    w = np.where(y == 1, 1.0, 1.0 / rate)
    return features(c, t, hist), y, w


def full_year(year, hist):
    ts = np.flatnonzero(YEAR_T == year)
    c, t = np.tile(np.arange(NC), len(ts)), np.repeat(ts, NC)
    keep = ~in_keys(EXCL_KEY, c, t)
    c, t = c[keep], t[keep]
    return features(c, t, hist), in_keys(POS_KEY, c, t).astype(np.int8), c, t


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
        apv = average_precision_score(yva, predict(m, Xva))
        log(f"num_leaves={leaves} scale_pos_weight={sw:.0f} trees={m.best_iteration_} val PR-AUC={apv:.4f}")
        if best is None or apv > best[0]:
            best = (apv, leaves, sw != 1.0, max(m.best_iteration_, 50))
_, LEAVES, SPW_SQRT, N_IT = best
log("terbaik:", best)


def train_all(years, hist, with_lr=True):
    X, y, w = sample_set(years, hist)
    lr = None
    if with_lr:
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
X25, y25, c25, t25 = full_year(2025, h_test)
r, p25 = report(X25, y25, c25, lr_a, model_a, "test 2025")
rows += r
CUTS_LIVE = fb.season_cuts(p25, times[t25].month)          # out-of-sample cuts for the live model
log("test 2025 done")

h_hind = hist_for([2022, 2023, 2024, 2025])
lr_b, model_b = train_all([2022, 2023, 2024, 2025], h_hind)
X21, y21, c21, t21 = full_year(2021, h_hind)
r, p21 = report(X21, y21, c21, lr_b, model_b, "hindcast 2021")
rows += r
metrics = pd.DataFrame(rows).set_index(["set", "region", "model"])
(ROOT / "models").mkdir(exist_ok=True)
metrics.round(4).to_csv(ROOT / f"models/metrics_turkiye_{VARIANT}.csv")
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

# ============================================================== Tahap 4: risk map check
CUTS = fb.season_cuts(p21, times[t21].month)
days = pd.date_range("2021-07-27", "2021-08-02")
dmask = np.isin(times[t21], days)
Xw, cw, tw = X21[dmask], c21[dmask], t21[dmask]
score_w = fb.fwi_ceiling(fb.to_score(p21[dmask], CUTS), Xw.fwi.values)
fires_w = y21[dmask]
bins = [-1, 0.30, 0.55, 0.75, 2]
log("week wildfire cell-days:", int(fires_w.sum()))
print(pd.cut(score_w[fires_w == 1], bins, labels=fb.CLASSES).value_counts().sort_index().to_string())
print("megafire sites (5x5 cells), max score per day and class of burning cells:")
for name, lo, la in fb.MEGAFIRES:
    s = fb.site_cells(cells, lo, la)
    m = np.isin(cw, s)
    daymax = [score_w[m & (times[tw] == d)].max() for d in days]
    burn = pd.cut(score_w[m & (fires_w == 1)], bins, labels=fb.CLASSES).value_counts()
    print(f"  {name:16s} max {np.round(daymax, 2)} | burning: {dict(burn[burn > 0])}")
topcells = np.bincount(cw, weights=score_w, minlength=NC) / 7
t1 = topcells >= np.quantile(topcells, 0.99)
print("top 1% week cells by longitude band:",
      dict(zip(["25-28", "28-31", "31-34", "34-37", "37-40", "40-45"],
               np.histogram(cells.lon_c.values[t1], bins=[25, 28, 31, 34, 37, 40, 45])[0])))
if not ARGS.export:
    log("done (no export)")
    sys.exit()

# final live model: all labelled years, history from all of them
h_live = fb.history_from(pos_c[np.isin(YEAR_T[pos_t], range(2021, 2026))], NC, cells, 5)
_, model_live = train_all([2021, 2022, 2023, 2024, 2025], {y: h_live for y in np.unique(YEAR_T)}, with_lr=False)
joblib.dump({"model": model_a, "model_hindcast_2021": model_b, "model_live": model_live,
             "features": FEATURES, "groups": GROUPS, "use_history": USE_HIST,
             "risk_cuts": CUTS, "risk_cuts_live": CUTS_LIVE, "hist_live": h_live,
             "grid": {"bbox": [LON0, LAT0, LON1, LAT1], "cell": CELL}, "fwi_points": used, "cell_pt": cell_pt,
             "fwi_point_lat": PT_LAT, "fwi_point_lon": PT_LON,
             "neg_rate": NEG_RATE, "tuned": {"num_leaves": LEAVES, "sqrt_spw": SPW_SQRT, "trees": N_IT}},
            ROOT / "models/fire_lgbm_turkiye.joblib")
shutil.copy(ROOT / f"models/metrics_turkiye_{VARIANT}.csv", ROOT / "models/metrics_turkiye.csv")

# per-cell SHAP group shares, averaged over the week (hindcast model)
shap_pct = fb.shap_group_pct(model_b.booster_, Xw, cw, NC, USE_HIST)

dash_path = ROOT / "bizdenbize/dashboard/data.json"
old = json.loads(dash_path.read_text(encoding="utf-8"))
pilot_copy = dash_path.with_name("data.pilot.json")
if not pilot_copy.exists() and old["meta"]["bbox"] == list(PILOT):
    shutil.copy(dash_path, pilot_copy)


def landcover_class(st):
    """Dashboard class: 0 forest, 1 shrub, 2 agriculture, 3 urban, 4 other (grass/bare)."""
    lc = st[["wc_tree", "wc_shrub", "wc_crop", "wc_built"]].fillna(0).values
    return np.where(lc.max(axis=1) >= 0.2, lc.argmax(axis=1), 4)


def day_layers(X, c, t, score, day_list):
    fwi_days, risk_days = [], []
    for d in day_list:
        m = times[t] == d
        f, s = np.zeros(NC), np.zeros(NC)
        f[c[m]], s[c[m]] = X.fwi.values[m], score[m]
        fwi_days.append(np.round(f, 1).tolist())
        risk_days.append(np.round(s, 3).tolist())
    return fwi_days, risk_days


def base_layers():
    roads = gpd.read_file(TRD / "osm_roads.gpkg")
    roads = roads[roads.fclass.isin(["motorway", "trunk", "primary"])]
    merged = shapely.line_merge(shapely.union_all(roads.geometry.values))
    lines = gpd.GeoSeries([merged], crs=4326).explode(index_parts=False).to_crs(3035).simplify(500).to_crs(4326)
    road_json = [[[round(x, 3), round(y, 3)] for x, y in g.coords] for g in lines if len(g.coords) > 1 and g.length > 0]
    towns = gpd.read_file(TRD / "osm_settlements.gpkg")
    towns = towns[towns.fclass.isin(["city", "town"])].copy()
    # the Geofabrik extract reaches a little over the land border: keep towns inside the national boundary
    admin = gpd.read_file(TRD / "adminareas.gpkg", columns=["fclass"])
    towns = towns[towns.within(admin[admin.fclass == "national"].union_all())]
    towns["population"] = pd.to_numeric(towns.population, errors="coerce").fillna(0)
    towns = towns.sort_values("population", ascending=False)
    sets = [[n, round(g.x, 3), round(g.y, 3), int(p)]
            for n, g, p in zip(towns.name, towns.geometry, towns.population) if isinstance(n, str)]
    return road_json, sets


fwi_days, risk_days = day_layers(Xw, cw, tw, score_w, days)
road_json, settlements = base_layers()
dash = {
    "meta": {**old["meta"], "demo": False, "mode": "hindcast", "dates": [d.strftime("%Y-%m-%d") for d in days],
             "bbox": [LON0, LAT0, LON1, LAT1], "cell": CELL,
             "ncols": NCOLS, "nrows": NROWS, "pilot_bbox": list(PILOT), "coverage": "turkiye",
             "groups": list(GROUPS),
             "note": ("Cakupan: seluruh Türkiye (sel 0,05°). FWI: Copernicus CEMS/EFFIS. Risiko: LightGBM dilatih "
                      "2022-2025 (hindcast, 2021 tidak dilihat model) pada label kebakaran hutan (hotspot VIIRS "
                      "tanpa pembakaran lahan pertanian). Jalan/permukiman: OpenStreetMap. Tutupan lahan: ESA "
                      "WorldCover 2021. Elevasi & lereng: Copernicus DEM GLO-90. Kelas dibatasi oleh tingkat "
                      "bahaya FWI hari itu (FWI < 5,2 maks. rendah; < 11,2 maks. sedang; < 21,3 maks. tinggi).")},
    "cells": {"ix": cells.ix.tolist(), "iy": cells.iy.tolist(),
              "dist_road": static.dist_road_km.round(1).tolist(), "dist_set": static.dist_set_km.round(1).tolist(),
              "elev": static.elev_m.round(0).fillna(0).astype(int).tolist(),
              "slope": static.slope_mean.round(1).fillna(0).tolist(),
              "landcover": landcover_class(static).tolist(),
              "shap": shap_pct.T.tolist(), "fwi": fwi_days, "risk": risk_days},
    "roads": road_json,
    "settlements": settlements,
    "fires": old.get("fires", []),
}
dash_path.write_text(json.dumps(dash, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
# static layers reused by 06_predict_live.py
(TRD / "dashboard_base.json").write_text(json.dumps(
    {"roads": road_json, "settlements": settlements, "fires": dash["fires"]}, separators=(",", ":"),
    ensure_ascii=False), encoding="utf-8")
log(f"data.json: {dash_path.stat().st_size // 1024} KB | cells {NC} | roads {len(road_json)} | "
    f"settlements {len(settlements)}")
