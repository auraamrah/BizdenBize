#!/usr/bin/env python3
"""Export model output for the website (web/).

06_predict_live.py writes bizdenbize/dashboard/data.live.json (~6–7 MB) and
05_train_turkiye.py --export writes bizdenbize/dashboard/data.json (2021 hindcast).
This turns them into compact files the website loads quickly on a phone (dense uint8
grids, base64) and precomputes the settlement table and national KPIs:

    bizdenbize/dashboard/data.live.json  ->  web/data/live.json
    bizdenbize/dashboard/data.json       ->  web/data/hindcast.json

Usage:
    python bizdenbize/scripts/web_export.py            # both, repo-relative paths
    python bizdenbize/scripts/web_export.py SRC DST    # one file

06_predict_live.py and 05_train_turkiye.py --export call it automatically, and the GitHub
Pages workflow runs it on every deploy. Standard library only.
"""
import base64
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULTS = [
    (ROOT / "bizdenbize/dashboard/data.live.json", ROOT / "web/data/live.json"),
    (ROOT / "bizdenbize/dashboard/data.json", ROOT / "web/data/hindcast.json"),
]
NO_DATA = 255
THRESHOLDS = (0.30, 0.55, 0.75)
RADIUS_KM = 10.0  # same "mean score within 10 km" used in the dashboard settlement table


def b64(buf: bytearray) -> str:
    return base64.b64encode(bytes(buf)).decode("ascii")


def export(src, dst) -> None:
    src, dst = pathlib.Path(src), pathlib.Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(src, encoding="utf-8") as f:
        d = json.load(f)
    meta, cells = d["meta"], d["cells"]
    ncols, nrows, cell = meta["ncols"], meta["nrows"], meta["cell"]
    west, south = meta["bbox"][0], meta["bbox"][1]
    n = len(cells["ix"])
    days = len(cells["risk"])
    dates = meta.get("dates") or meta.get("days")

    def dense(values, scale, cap=254):
        g = bytearray([NO_DATA]) * (ncols * nrows)
        for i in range(n):
            v = values[i]
            if v is None:
                continue
            # floor, not round: the model caps scores just below class cut-points (e.g. 0.299),
            # and rounding would push them into the next class
            g[cells["iy"][i] * ncols + cells["ix"][i]] = max(0, min(cap, int(math.floor(v * scale + 1e-6))))
        return g

    risk = [dense(cells["risk"][t], 250) for t in range(days)]        # 0..250 → 0.00..1.00
    # exact class from the full-precision score (0 low, 1 moderate, 2 high, 3 extreme)
    def classes(values):
        g = bytearray([NO_DATA]) * (ncols * nrows)
        for i in range(n):
            v = values[i]
            if v is not None:
                g[cells["iy"][i] * ncols + cells["ix"][i]] = sum(v >= th for th in THRESHOLDS)
        return g
    klass = [classes(cells["risk"][t]) for t in range(days)]
    fwi = [dense(cells["fwi"][t], 2) for t in range(days)]            # 0..254 → 0..127 FWI
    shap = [dense(cells["shap"][g], 1, 100) for g in range(len(cells["shap"]))]  # % share per group

    # settlements: mean + max risk of land cells within RADIUS_KM, per day
    kmy = 110.57
    kmx = 111.32 * math.cos(math.radians((meta["bbox"][1] + meta["bbox"][3]) / 2))
    rx, ry = int(math.ceil(RADIUS_KM / (cell * kmx))) + 1, int(math.ceil(RADIUS_KM / (cell * kmy))) + 1
    settlements = []
    for name, lon, lat, pop in d.get("settlements", []):
        cx, cy = int((lon - west) / cell), int((lat - south) / cell)
        idx = []
        for yy in range(cy - ry, cy + ry + 1):
            for xx in range(cx - rx, cx + rx + 1):
                if 0 <= xx < ncols and 0 <= yy < nrows and risk[0][yy * ncols + xx] != NO_DATA:
                    clon, clat = west + (xx + 0.5) * cell, south + (yy + 0.5) * cell
                    if math.hypot((clon - lon) * kmx, (clat - lat) * kmy) <= RADIUS_KM:
                        idx.append(yy * ncols + xx)
        if not idx:
            continue
        mean = [round(sum(risk[t][k] for k in idx) / len(idx) / 250, 3) for t in range(days)]
        mx = [round(max(risk[t][k] for k in idx) / 250, 3) for t in range(days)]
        settlements.append([name, round(lon, 4), round(lat, 4), pop, mean, mx])

    kpis = []
    for t in range(days):
        c = [v for v in klass[t] if v != NO_DATA]
        fw = [v / 2 for v in fwi[t] if v != NO_DATA]
        kpis.append({
            "moderate": c.count(1), "high": c.count(2), "extreme": c.count(3),
            "land_cells": len(c),
            "mean_fwi": round(sum(fw) / max(1, len(fw)), 1),
            "max_fwi": round(max(fw or [0]), 1),
        })

    out = {
        "meta": {
            "mode": meta.get("mode", "live"),
            "generated_at": meta.get("generated_at"),
            "dates": dates,
            "bbox": meta["bbox"], "cell": cell, "ncols": ncols, "nrows": nrows,
            "thresholds": list(THRESHOLDS),
            "shap_groups": ["weather", "human", "history", "environment"],
            "encoding": "risk: uint8/250 (floored); class: 0-3 from full precision; fwi: uint8/2; shap: percent; 255 = no land",
            "source": "BizdenBize LightGBM model (06_predict_live.py / 05_train_turkiye.py)",
            "note": meta.get("note", ""),
        },
        "risk": [b64(g) for g in risk],
        "class": [b64(g) for g in klass],
        "fwi": [b64(g) for g in fwi],
        "shap": [b64(g) for g in shap],
        "settlements": settlements,
        "active_fires": d.get("active_fires", []),
        "reference_fires": d.get("fires", []),
        "kpis": kpis,
    }
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{dst}: {days} days, {n} land cells, {len(settlements)} settlements, "
          f"{len(out['active_fires'])} active fires")


if __name__ == "__main__":
    if len(sys.argv) == 3:
        export(sys.argv[1], sys.argv[2])
    elif len(sys.argv) == 1:
        for s, d in DEFAULTS:
            if s.exists():
                export(s, d)
            else:
                print(f"skip: {s.relative_to(ROOT)} not found")
    else:
        sys.exit(__doc__)
