"""FireBridge — shared grid, feature and scoring code for training (05) and live prediction (06).

Everything here is a pure function of arrays, so both scripts build the exact same feature table.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.ndimage import convolve
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
DATA, TRD = ROOT / "data", ROOT / "data" / "turkiye"
LON0, LAT0, LON1, LAT1, CELL = 25.5, 35.8, 44.9, 42.3, 0.05
NCOLS, NROWS = int(round((LON1 - LON0) / CELL)), int(round((LAT1 - LAT0) / CELL))
PILOT = (27.2, 36.0, 32.4, 37.7)

FWI_VARS = ["fwi", "ffmc", "dmc", "dc", "isi", "bui"]
WEATHER = FWI_VARS + ["fwi_mean3", "fwi_mean7", "fwi_max7", "dc_change7", "doy"]
HUMAN = ["dist_road_km", "dist_set_km", "dist_farm_km", "road_km_per_cell"]
HISTORY = ["hist_cell", "hist_nb"]
ENV = ["wc_tree", "wc_shrub", "wc_grass", "wc_crop", "wc_built", "elev_m", "slope_mean", "slope_p90"]
CLASSES = ["rendah", "sedang", "tinggi", "ekstrem"]
SCORES = [0, 0.30, 0.55, 0.75, 1]

# 2021-2024 megafires used to check that the map flags the events the campaign is about
MEGAFIRES = [("Manavgat 2021", 31.5, 36.88), ("Gündoğmuş 2021", 32.05, 36.78), ("Akseki 2021", 31.72, 36.98),
             ("Marmaris 2021", 28.35, 36.9), ("Köyceğiz 2021", 28.75, 36.96), ("Milas 2021", 27.72, 37.18),
             ("Bodrum 2021", 27.58, 37.02)]


def groups(use_history=True):
    g = {"cuaca": WEATHER, "manusia": HUMAN, "histori": HISTORY, "lingkungan": ENV}
    if not use_history:
        g.pop("histori")
    return g


def features_list(use_history=True):
    return [f for v in groups(use_history).values() for f in v]


def load_cells():
    """Land cells and their static features (OSM human access + WorldCover/DEM environment)."""
    cells = pd.read_csv(TRD / "cells.csv")
    static = (cells[["ix", "iy"]].merge(pd.read_csv(TRD / "static_human.csv"), on=["ix", "iy"], how="left")
              .merge(pd.read_csv(TRD / "static_env.csv"), on=["ix", "iy"], how="left"))
    return cells, static


def map_cells_to_points(cells, lat, lon):
    """Nearest weather point for every cell -> (used point ids, cell -> column in the used-point arrays)."""
    pts = np.column_stack([lat, np.where(lon > 180, lon - 360, lon)])
    _, k = cKDTree(pts).query(cells[["lat_c", "lon_c"]].values)
    used, cell_pt = np.unique(k, return_inverse=True)
    return used, cell_pt


def weather_features(raw, times):
    """raw: {fwi, ffmc, dmc, dc, isi, bui} -> [T, P] float32. Adds lags; windows never bridge two seasons."""
    W = {v: np.asarray(raw[v], np.float32) for v in FWI_VARS}
    fw = pd.DataFrame(W["fwi"], index=times)
    yr = times.year
    roll = lambda f: fw.groupby(yr).transform(f).values.astype(np.float32)
    W["fwi_mean3"] = roll(lambda s: s.shift(1).rolling(3, min_periods=1).mean())
    W["fwi_mean7"] = roll(lambda s: s.shift(1).rolling(7, min_periods=1).mean())
    W["fwi_max7"] = roll(lambda s: s.shift(1).rolling(7, min_periods=1).max())
    dcf = pd.DataFrame(W["dc"], index=times)
    W["dc_change7"] = (dcf - dcf.groupby(yr).shift(7)).values.astype(np.float32)
    return W


def history_from(pos_c, n_cells, cells, n_years):
    """Fire-days per year in each cell and its 3x3 neighbourhood, from positive cell ids `pos_c`."""
    cnt = np.bincount(pos_c, minlength=n_cells).astype(np.float32)
    g = np.zeros((NROWS, NCOLS), np.float32)
    g[cells.iy, cells.ix] = cnt
    nb = convolve(g, np.ones((3, 3), np.float32), mode="constant")[cells.iy, cells.ix]
    return np.vstack([cnt, nb]) / max(n_years, 1)


def build_features(W, cell_pt, static, times, c, t, hist=None, use_history=True):
    """Feature table for cell ids `c` on day ids `t`. `hist`: {year: [2, n_cells]} or a single [2, n_cells].
    Filled column by column into one float32 block, so a 9M-row year needs a single allocation."""
    feats = features_list(use_history)
    A = np.empty((len(c), len(feats)), np.float32)
    col = {f: i for i, f in enumerate(feats)}
    pt = cell_pt[c]
    for v in WEATHER:
        A[:, col[v]] = times.day_of_year.values[t] if v == "doy" else W[v][t, pt]
    for k in HUMAN + ENV:
        A[:, col[k]] = static[k].values[c]
    if use_history:
        if isinstance(hist, dict):
            ty = times.year.values[t]
            for y, hy in hist.items():
                m = np.flatnonzero(ty == y)
                A[m, col["hist_cell"]] = hy[0, c[m]]
                A[m, col["hist_nb"]] = hy[1, c[m]]
        else:
            A[:, col["hist_cell"]], A[:, col["hist_nb"]] = hist[0, c], hist[1, c]
    return pd.DataFrame(A, columns=feats, copy=False)


def to_score(prob, cuts):
    """Probability -> 0..1 risk score whose class bands are SCORES (cuts from season quantiles)."""
    return np.interp(prob, cuts["probs"], cuts["scores"])


# FWI danger bands (EFFIS: moderate 5.2, high 11.2, very high 21.3). The model ranks *where* fire is likely
# relative to the fire season; the weather sets how high a class can go on a given day, so a calm day
# can never show "ekstrem". Ceiling per band: < 5.2 rendah, < 11.2 sedang, < 21.3 tinggi, else ekstrem.
FWI_BANDS = [5.2, 11.2, 21.3]
SCORE_CAPS = [0.299, 0.549, 0.749, 1.0]


def fwi_ceiling(score, fwi):
    """Cap the risk score by the FWI danger band of the same cell-day."""
    cap = np.asarray(SCORE_CAPS)[np.searchsorted(FWI_BANDS, np.nan_to_num(fwi), side="right")]
    return np.minimum(score, cap)


def season_cuts(prob, months):
    """Class cuts: top 20% of fire-season cell-days >= sedang, top 5% tinggi, top 1% ekstrem."""
    season = np.isin(months, [6, 7, 8, 9])
    return {"probs": np.quantile(prob[season], [0, 0.80, 0.95, 0.99, 1]).tolist(), "scores": SCORES}


def shap_group_pct(booster, X, c, n_cells, use_history=True):
    """Per-cell share (%) of |SHAP| per feature group, summed over the rows of X."""
    feats = features_list(use_history)
    contrib = booster.predict(X, pred_contrib=True)[:, :-1]
    gabs = np.column_stack([np.abs(contrib[:, [feats.index(f) for f in v]]).sum(axis=1)
                            for v in groups(use_history).values()])
    gcell = np.vstack([np.bincount(c, weights=gabs[:, j], minlength=n_cells) for j in range(gabs.shape[1])]).T
    return np.rint(100 * gcell / np.clip(gcell.sum(axis=1, keepdims=True), 1e-12, None)).astype(int)


def site_cells(cells, lon, lat, radius=2):
    cx, cy = int((lon - LON0) / CELL), int((lat - LAT0) / CELL)
    return np.flatnonzero((abs(cells.ix.values - cx) <= radius) & (abs(cells.iy.values - cy) <= radius))
