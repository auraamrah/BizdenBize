"""Bangun tabel label: 1 jika ada hotspot VIIRS pada sel 5 km di hari tsb, 0 jika tidak.
Input : data hotspot EFFIS (hs_viirs) — CSV dari folder JUKUT.
Output: <JUKUT>/labels/labels_pilot.csv  (ix, iy, date, y)
"""
import pandas as pd, numpy as np, sys
from pathlib import Path
CSV = sys.argv[1]
LON0, LAT0, LON1, LAT1 = 27.2, 36.0, 32.4, 37.7
CELL = 0.05
NCOLS = int(round((LON1-LON0)/CELL)); NROWS = int(round((LAT1-LAT0)/CELL))

df = pd.read_csv(CSV, dtype={"lat": float, "lon": float})
df["date"] = pd.to_datetime(df["acq_at_s"]).dt.normalize()
df = df.drop_duplicates(subset=["lat", "lon", "acq_at_s"])       # 1.353 duplikat dibuang
# 1) Drop persistent heat sources (factories, flares, landfills):
#    a ~400 m spot that is "on fire" on many separate days is not a wildfire.
df["spot"] = df.lat.round(3).astype(str) + "," + df.lon.round(3).astype(str)
days_per_spot = df.groupby("spot")["date"].nunique()
static = days_per_spot[days_per_spot >= 10].index      # tune the threshold
df = df[~df.spot.isin(static)]

# 2) Drop low-confidence detections (101 = low)
df = df[df.confidence.astype(int) >= 102]
df = df[(df.lon >= LON0) & (df.lon < LON1) & (df.lat >= LAT0) & (df.lat < LAT1)]
df["ix"] = ((df.lon - LON0) / CELL).astype(int)
df["iy"] = ((df.lat - LAT0) / CELL).astype(int)
pos = df.groupby(["ix", "iy", "date"]).size().rename("n").reset_index()
pos["y"] = 1

days = pd.date_range("2021-01-01", "2026-11-15", freq="D")
ix, iy = np.meshgrid(np.arange(NCOLS), np.arange(NROWS))
grid = pd.DataFrame({"ix": ix.ravel(), "iy": iy.ravel()})
full = grid.merge(pd.DataFrame({"date": days}), how="cross")
full = full.merge(pos[["ix", "iy", "date", "y"]], on=["ix", "iy", "date"], how="left")
full["y"] = full["y"].fillna(0).astype(int)
OUT = Path(__file__).resolve().parents[2] / "labels" / "labels_pilot.csv"   # scripts -> bizdenbize -> JUKUT
OUT.parent.mkdir(exist_ok=True)
full.to_csv(OUT, index=False)

print("hotspot pilot setelah dedup:", len(df))
print("baris sel-hari:", len(full), "| positif:", full.y.sum(),
      "| rasio positif:", round(full.y.mean()*100, 2), "%")
print(full.assign(yr=full.date.dt.year).groupby("yr").y.mean().mul(100).round(2).to_string())
