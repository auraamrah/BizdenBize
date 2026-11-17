"""FireBridge (#BizdenBize) — Tahap 1 & 2 dengan DATA DEMO.

Tahap 1: bangun grid 0.05 derajat (~5 km) wilayah Antalya-Muğla, lapisan
  cuaca-kebakaran (FWI, demo 7 hari meniru pola gelombang panas akhir Juli),
  jalan & permukiman utama (koordinat kota riil, geometri jalan disederhanakan),
  dan histori kebakaran besar (lokasi aproksimatif, mis. Manavgat & Marmaris 2021).
Tahap 2: fitur per sel -- jarak ke jalan, jarak ke permukiman, FWI + lag,
  proxy elevasi/vegetasi, lalu skor risiko gabungan (logistik) per sel per hari.

CATATAN: Semua nilai FWI & skor risiko di file ini adalah DEMO (sintetis tapi
plausibel) karena lingkungan ini tidak punya akses internet. Ganti dengan data
asli memakai scripts/01_data_acquisition.py.
"""

import json
import numpy as np

rng = np.random.default_rng(42)

# ----------------------------------------------------------------------------
# TAHAP 1a — Grid spasial
# ----------------------------------------------------------------------------
LON0, LON1 = 27.2, 32.4
LAT0, LAT1 = 36.0, 37.7
CELL = 0.05  # derajat (~5.5 km lat, ~4.5 km lon di lintang ini)

ncols = int(round((LON1 - LON0) / CELL))   # 104
nrows = int(round((LAT1 - LAT0) / CELL))   # 34
lons = LON0 + (np.arange(ncols) + 0.5) * CELL
lats = LAT0 + (np.arange(nrows) + 0.5) * CELL
LON, LAT = np.meshgrid(lons, lats)          # shape (nrows, ncols), row 0 = selatan

# Garis pantai skematik (barat -> timur): sel dengan pusat di selatan garis = laut
COAST = [(27.20, 36.98), (27.45, 36.93), (27.80, 36.80), (28.05, 36.72),
         (28.27, 36.82), (28.60, 36.76), (28.80, 36.70), (29.12, 36.62),
         (29.40, 36.42), (29.64, 36.18), (29.98, 36.22), (30.15, 36.28),
         (30.35, 36.40), (30.57, 36.55), (30.70, 36.84), (31.00, 36.84),
         (31.45, 36.74), (31.80, 36.60), (32.00, 36.52), (32.40, 36.26)]
cx = np.array([p[0] for p in COAST]); cy = np.array([p[1] for p in COAST])
coast_lat = np.interp(LON, cx, cy)
land = LAT >= coast_lat - 0.012  # buffer kecil agar sel pantai tetap darat

# ----------------------------------------------------------------------------
# TAHAP 1b — Permukiman & jalan (lapisan "manusia", pengganti OSM untuk demo)
# ----------------------------------------------------------------------------
SETTLEMENTS = [
    ("Antalya",   30.71, 36.90, 1300000), ("Muğla",   28.37, 37.21, 70000),
    ("Bodrum",    27.43, 37.04, 200000),  ("Milas",   27.78, 37.32, 60000),
    ("Marmaris",  28.27, 36.85, 100000),  ("Köyceğiz", 28.69, 36.97, 12000),
    ("Ortaca",    28.77, 36.84, 30000),   ("Dalaman", 28.80, 36.77, 25000),
    ("Fethiye",   29.12, 36.65, 170000),  ("Kaş",     29.64, 36.20, 10000),
    ("Demre",     29.98, 36.25, 17000),   ("Finike",  30.15, 36.30, 12000),
    ("Kumluca",   30.29, 36.37, 70000),   ("Kemer",   30.57, 36.60, 45000),
    ("Korkuteli", 30.20, 37.07, 55000),   ("Elmalı",  29.92, 36.74, 40000),
    ("Serik",     31.10, 36.92, 130000),  ("Manavgat", 31.44, 36.79, 240000),
    ("Akseki",    31.79, 37.05, 10000),   ("Gündoğmuş", 32.01, 36.81, 7000),
    ("Alanya",    32.00, 36.54, 360000),  ("Gazipaşa", 32.32, 36.27, 50000),
    ("Yatağan",   28.14, 37.34, 25000),
]

ROADS = [  # polyline disederhanakan; demo pengganti geometri OSM
    # D400/D330 koridor pesisir + lembah
    [(27.43, 37.04), (27.78, 37.32), (28.14, 37.34), (28.37, 37.21),
     (28.27, 36.85)],
    [(28.27, 36.85), (28.69, 36.97), (28.77, 36.84), (28.80, 36.77),
     (29.12, 36.65), (29.40, 36.44), (29.64, 36.20), (29.98, 36.25),
     (30.15, 36.30), (30.29, 36.37), (30.57, 36.60), (30.71, 36.90)],
    [(30.71, 36.90), (31.10, 36.92), (31.44, 36.79), (32.00, 36.54),
     (32.32, 36.27)],
    # Jalan pedalaman
    [(30.71, 36.90), (30.20, 37.07), (29.92, 36.74), (30.15, 36.30)],  # Korkuteli-Elmalı-Finike
    [(31.44, 36.79), (31.79, 37.05)],                                   # Manavgat-Akseki (D695)
    [(32.00, 36.54), (32.01, 36.81)],                                   # Alanya-Gündoğmuş
    [(28.37, 37.21), (28.37, 37.60)],                                   # Muğla ke utara
    [(30.71, 36.90), (30.60, 37.40)],                                   # Antalya ke Burdur
]

# Histori kebakaran besar (lokasi & luas APROKSIMATIF — demo pengganti OGM/EFFIS)
FIRES = [
    ("Manavgat 2021",  31.50, 36.88, 2021, 60000),
    ("Gündoğmuş 2021", 32.05, 36.78, 2021, 15000),
    ("Akseki 2021",    31.72, 36.98, 2021, 8000),
    ("Marmaris 2021",  28.35, 36.90, 2021, 13000),
    ("Köyceğiz 2021",  28.75, 36.96, 2021, 7000),
    ("Milas 2021",     27.72, 37.18, 2021, 10000),
    ("Bodrum 2021",    27.58, 37.02, 2021, 4000),
    ("Marmaris 2022",  28.40, 36.80, 2022, 4400),
    ("Kemerköy 2023",  27.70, 37.05, 2023, 1500),
    ("Serik 2024",     31.18, 37.00, 2024, 2000),
]

# ----------------------------------------------------------------------------
# TAHAP 1c — Medan & cuaca demo
# ----------------------------------------------------------------------------
def smooth2(a, it=3):
    for _ in range(it):
        a = (a + np.roll(a, 1, 0) + np.roll(a, -1, 0)
               + np.roll(a, 1, 1) + np.roll(a, -1, 1)) / 5.0
    return a

# Proxy elevasi: naik menjauh dari pantai (Pegunungan Taurus), + noise halus
dist_coast_deg = np.clip(LAT - coast_lat, 0, None)
elev = 1800 * np.tanh(dist_coast_deg / 0.45) + 350 * smooth2(rng.standard_normal(LAT.shape), 4)
elev = np.clip(elev, 0, 2600)
slope = np.clip(np.abs(np.gradient(elev)[0]) + np.abs(np.gradient(elev)[1]), 0, 400) / 400

# FWI demo 7 hari: gelombang panas memuncak hari ke-6 (pola mirip akhir Juli 2021)
DAYS = ["Sen 27/7", "Sel 28/7", "Rab 29/7", "Kam 30/7", "Jum 31/7", "Sab 1/8", "Min 2/8"]
day_boost = np.array([0.0, 2.0, 5.0, 9.0, 14.0, 17.0, 12.0])
base = 34 + 10 * np.exp(-elev / 900)          # dataran rendah lebih kering-panas
east = 6 * np.clip((LON - 29.5) / 2.9, 0, 1)  # sisi timur (Manavgat dsk.) lebih ekstrem
fwi = np.empty((7,) + LAT.shape)
for d in range(7):
    noise = 3.5 * smooth2(rng.standard_normal(LAT.shape), 3)
    fwi[d] = np.clip(base + east + day_boost[d] + noise, 5, 95)

# ----------------------------------------------------------------------------
# TAHAP 2 — Fitur per sel
# ----------------------------------------------------------------------------
KMX = 111.32 * np.cos(np.deg2rad(36.8))  # km per derajat lon
KMY = 110.57                              # km per derajat lat

def dist_point_seg(px, py, ax, ay, bx, by):
    """Jarak (km) titik->segmen, koordinat sudah dalam km."""
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    t = np.clip((wx * vx + wy * vy) / (vx * vx + vy * vy + 1e-12), 0, 1)
    return np.hypot(px - (ax + t * vx), py - (ay + t * vy))

PX, PY = LON * KMX, LAT * KMY
dist_road = np.full(LAT.shape, 1e9)
for line in ROADS:
    for (a, b) in zip(line[:-1], line[1:]):
        d = dist_point_seg(PX, PY, a[0] * KMX, a[1] * KMY, b[0] * KMX, b[1] * KMY)
        dist_road = np.minimum(dist_road, d)

dist_set = np.full(LAT.shape, 1e9)
for (_, slon, slat, _) in SETTLEMENTS:
    dist_set = np.minimum(dist_set, np.hypot(PX - slon * KMX, PY - slat * KMY))

# Tutupan lahan demo: 0=hutan konifer, 1=maki/semak, 2=pertanian, 3=urban
lc_noise = smooth2(rng.standard_normal(LAT.shape), 3)
landcover = np.ones(LAT.shape, dtype=int)                  # default maki
landcover[(elev > 350) & (elev < 1700) & (lc_noise > -0.6)] = 0   # hutan di perbukitan
landcover[(elev <= 220) & (dist_set < 18) & (slope < 0.25)] = 2   # pertanian dataran
landcover[dist_set < 3.5] = 3                                      # urban
fuel = np.choose(landcover, [1.00, 0.80, 0.55, 0.15])  # faktor bahan bakar

# FWI lag-3 (rerata 3 hari sebelumnya; hari awal pakai rerata yang tersedia)
fwi_lag3 = np.empty_like(fwi)
for d in range(7):
    lo = max(0, d - 3)
    fwi_lag3[d] = fwi[lo:d].mean(axis=0) if d > 0 else fwi[0]

# Skor risiko gabungan (logistik) — struktur sama dengan model ML nantinya
def risk_day(d):
    z = (-4.4
         + 4.4 * (fwi[d] / 100.0)                 # bahaya cuaca hari ini
         + 1.6 * (fwi_lag3[d] / 100.0)            # tren pengeringan
         + 1.5 * np.exp(-dist_road / 3.0)         # akses manusia: jalan
         + 1.2 * np.exp(-dist_set / 6.0)          # akses manusia: permukiman
         + 1.3 * fuel                              # bahan bakar vegetasi
         + 0.5 * slope)                            # lereng mempercepat rambat
    return 1.0 / (1.0 + np.exp(-z))

risk = np.stack([risk_day(d) for d in range(7)])

# ----------------------------------------------------------------------------
# Ekspor: hanya sel darat, array datar terurut
# ----------------------------------------------------------------------------
iy, ix = np.where(land)
order = np.argsort(iy * ncols + ix)
iy, ix = iy[order], ix[order]

def grab(a, dec):  # ambil nilai sel darat, bulatkan
    return np.round(a[iy, ix], dec).tolist()

payload = {
    "meta": {
        "project": "FireBridge / #BizdenBize — COP31 Climate Tech Creathon",
        "demo": True,
        "note": ("SEMUA nilai FWI, risiko, geometri jalan & lokasi kebakaran "
                 "adalah DEMO/aproksimasi. Sumber asli: EFFIS (FWI), OSM "
                 "(jalan/permukiman), OGM/EFFIS Burnt Area (histori)."),
        "bbox": [LON0, LAT0, LON1, LAT1], "cell": CELL,
        "ncols": ncols, "nrows": nrows, "days": DAYS,
        "risk_classes": [[0.00, "Rendah"], [0.30, "Sedang"],
                          [0.55, "Tinggi"], [0.75, "Ekstrem"]],
    },
    "cells": {"ix": ix.tolist(), "iy": iy.tolist(),
              "dist_road": grab(dist_road, 1), "dist_set": grab(dist_set, 1),
              "elev": grab(elev, 0), "slope": grab(slope, 2),
              "landcover": [int(v) for v in landcover[iy, ix]],
              "fwi": [grab(fwi[d], 1) for d in range(7)],
              "risk": [grab(risk[d], 3) for d in range(7)]},
    "coast": COAST,
    "roads": ROADS,
    "settlements": [[n, lo, la, p] for (n, lo, la, p) in SETTLEMENTS],
    "fires": [[n, lo, la, y, ha] for (n, lo, la, y, ha) in FIRES],
}

with open("/home/claude/firebridge/dashboard/data.json", "w") as f:
    json.dump(payload, f, separators=(",", ":"))

# Ringkasan verifikasi
n_land = len(ix)
peak = risk[5]
extreme = (peak[iy, ix] >= 0.75).sum()
high = ((peak[iy, ix] >= 0.55) & (peak[iy, ix] < 0.75)).sum()
print(f"grid {nrows}x{ncols} = {nrows*ncols} sel, darat = {n_land}")
print(f"FWI hari puncak (Sab 1/8): min {fwi[5][iy,ix].min():.1f}, "
      f"maks {fwi[5][iy,ix].max():.1f}, rerata {fwi[5][iy,ix].mean():.1f}")
print(f"risiko hari puncak: ekstrem {extreme} sel, tinggi {high} sel")
print(f"jarak jalan: median {np.median(dist_road[iy,ix]):.1f} km; "
      f"jarak permukiman: median {np.median(dist_set[iy,ix]):.1f} km")
import os
print("data.json:", os.path.getsize('/home/claude/firebridge/dashboard/data.json')//1024, "KB")
