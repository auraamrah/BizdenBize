"""FireBridge — nationwide grid, land mask, OSM human features and VIIRS labels for all of Türkiye.

Grid: 0.05° cells over 25.5-44.9 E / 35.8-42.3 N. It is aligned with the pilot grid
(pilot ix = national ix - 34, pilot iy = national iy - 4).
Land mask: share of the cell covered by OSM district polygons (admin_level 6, which follow the
coastline; the national polygon includes territorial waters) >= 30%.

Outputs in <JUKUT>/data/turkiye/ (each step is cached and skipped when its file exists):
  cells.csv          ix, iy, lat_c, lon_c, land_frac
  osm_*.gpkg         roads / settlements / farmland, whole country
  static_human.csv   dist_road_km, dist_set_km, dist_farm_km, road_km_per_cell
  fire_pos.csv       positive cell-days only (ix, iy, date, n); every other land cell-day is y = 0
"""
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
OUT = DATA / "turkiye"
OUT.mkdir(parents=True, exist_ok=True)
ZIP = DATA / "turkey-latest-free.shp.zip"
HOTSPOTS = DATA / "a29cb7c7d8004c7c81778ad1bd237a5b.csv"     # EFFIS hs_viirs, admin0 = TR, 2021-2026

LON0, LAT0, LON1, LAT1, CELL = 25.5, 35.8, 44.9, 42.3, 0.05
NCOLS, NROWS = int(round((LON1 - LON0) / CELL)), int(round((LAT1 - LAT0) / CELL))
MIN_LAND = 0.3
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


def cell_boxes(ix, iy):
    return shapely.box(LON0 + ix * CELL, LAT0 + iy * CELL, LON0 + (ix + 1) * CELL, LAT0 + (iy + 1) * CELL)


# ---------------------------------------------------------------- 1) land mask
CELLS = OUT / "cells.csv"
if not CELLS.exists():
    admin = DATA / "turkiye" / "adminareas.gpkg"
    src = admin if admin.exists() else f"zip://{ZIP}!gis_osm_adminareas_a_free_1.shp"
    a = gpd.read_file(src, columns=["fclass"])
    # districts do not overlap, so summing per-district intersection areas gives the land share;
    # districts are split into small pieces first so each clip stays cheap
    land = a[a.fclass == "admin_level6"].to_crs(6933).geometry.values      # equal-area CRS
    ix, iy = np.meshgrid(np.arange(NCOLS), np.arange(NROWS))
    ix, iy = ix.ravel(), iy.ravel()
    g = gpd.GeoSeries(cell_boxes(ix, iy), crs=4326).to_crs(6933).values
    d_i, c_i = shapely.STRtree(land).query(g, predicate="intersects")[::-1]
    area = shapely.area(shapely.intersection(land[d_i], g[c_i], grid_size=1.0))
    frac = np.minimum(np.bincount(c_i, weights=area, minlength=len(g)) / shapely.area(g), 1.0)
    cells = pd.DataFrame({"ix": ix, "iy": iy, "land_frac": frac.round(3)})
    cells = cells[cells.land_frac >= MIN_LAND].reset_index(drop=True)
    cells["lat_c"] = (LAT0 + (cells.iy + 0.5) * CELL).round(3)
    cells["lon_c"] = (LON0 + (cells.ix + 0.5) * CELL).round(3)
    cells.to_csv(CELLS, index=False)
cells = pd.read_csv(CELLS)
log("land cells:", len(cells), f"of {NCOLS}x{NROWS}")

# ---------------------------------------------------------------- 2) OSM layers
OSM_LAYERS = {
    "roads": ("gis_osm_roads_free_1.shp",
              ["motorway", "trunk", "primary", "secondary", "tertiary", "unclassified"]),
    "settlements": ("gis_osm_places_free_1.shp", ["city", "town", "village", "hamlet"]),
    "farmland": ("gis_osm_landuse_a_free_1.shp", ["farmland", "orchard"]),
}
for name, (shp, classes) in OSM_LAYERS.items():
    path = OUT / f"osm_{name}.gpkg"
    if not path.exists():
        where = "fclass IN (" + ",".join(f"'{c}'" for c in classes) + ")"
        cols = ["fclass", "name", "population"] if name == "settlements" else ["fclass"]
        gpd.read_file(f"zip://{ZIP}!{shp}", where=where, columns=cols).to_file(path, driver="GPKG")
    log("osm", name, "ready")

# ---------------------------------------------------------------- 3) static human features
STATIC = OUT / "static_human.csv"
if not STATIC.exists():
    grid = gpd.GeoSeries(cell_boxes(cells.ix.values, cells.iy.values), crs=4326).to_crs(3035)
    centres = gpd.GeoDataFrame(geometry=grid.centroid, crs=3035)
    static = cells[["ix", "iy"]].copy()
    for name, col in [("roads", "dist_road_km"), ("settlements", "dist_set_km"), ("farmland", "dist_farm_km")]:
        layer = gpd.read_file(OUT / f"osm_{name}.gpkg", columns=[]).to_crs(3035)
        if name == "settlements":
            layer["geometry"] = layer.representative_point()
        j = gpd.sjoin_nearest(centres, layer[["geometry"]], distance_col="d")
        static[col] = (j.groupby(level=0)["d"].min() / 1000).round(2).values
        log("distance", name, "done")
    roads = gpd.read_file(OUT / "osm_roads.gpkg", columns=[]).to_crs(3035).geometry.values
    tree = shapely.STRtree(grid.values)
    r_i, c_i = tree.query(roads, predicate="intersects")
    seg_km = shapely.length(shapely.intersection(roads[r_i], grid.values[c_i])) / 1000
    static["road_km_per_cell"] = np.bincount(c_i, weights=seg_km, minlength=len(cells)).round(2)
    static.to_csv(STATIC, index=False)
    log("road length per cell done")
log("static_human:", len(pd.read_csv(STATIC)), "cells")

# ---------------------------------------------------------------- 4) labels (same filters as 02_build_labels.py)
POS = OUT / "fire_pos.csv"
if not POS.exists():
    df = pd.read_csv(HOTSPOTS, usecols=["acq_at_s", "lat", "lon", "confidence"])
    df["date"] = pd.to_datetime(df["acq_at_s"]).dt.normalize()
    df = df.drop_duplicates(subset=["lat", "lon", "acq_at_s"])
    # persistent heat sources (factories, flares, landfills): a ~100 m spot "burning" on >= 10 days
    spot = df.lat.round(3).astype(str) + "," + df.lon.round(3).astype(str)
    days_per_spot = df.groupby(spot)["date"].nunique()
    df = df[~spot.isin(days_per_spot[days_per_spot >= 10].index)]
    df = df[pd.to_numeric(df.confidence, errors="coerce") >= 102]       # drop low confidence (101)
    df["ix"] = np.floor((df.lon - LON0) / CELL).astype(int)
    df["iy"] = np.floor((df.lat - LAT0) / CELL).astype(int)
    pos = df.groupby(["ix", "iy", "date"]).size().rename("n").reset_index()
    pos = pos.merge(cells[["ix", "iy"]], on=["ix", "iy"])                # land cells only
    pos.to_csv(POS, index=False)
pos = pd.read_csv(POS, parse_dates=["date"])
log("positive cell-days:", len(pos))
print(pos.groupby(pos.date.dt.year).size().to_string())

# ---------------------------------------------------------------- 5) land cover share per cell (OSM landuse)
LC_CLASSES = {
    "forest": ["forest"],
    "shrub": ["scrub", "heath"],
    "agri": ["farmland", "orchard", "vineyard", "farmyard", "meadow", "allotments"],
    "urban": ["residential", "industrial", "commercial", "retail"],
}
LC = OUT / "static_landcover.csv"
if not LC.exists():
    every = [c for v in LC_CLASSES.values() for c in v]
    lu = gpd.read_file(f"zip://{ZIP}!gis_osm_landuse_a_free_1.shp",
                       where="fclass IN (" + ",".join(f"'{c}'" for c in every) + ")", columns=["fclass"])
    lu = lu.to_crs(6933)
    lu["geometry"] = shapely.make_valid(lu.geometry.values)
    grid = gpd.GeoSeries(cell_boxes(cells.ix.values, cells.iy.values), crs=4326).to_crs(6933).values
    cell_area = shapely.area(grid)
    tree = shapely.STRtree(grid)
    out = cells[["ix", "iy"]].copy()
    for name, classes in LC_CLASSES.items():
        geoms = lu.geometry.values[lu.fclass.isin(classes).values]
        g_i, c_i = tree.query(geoms, predicate="intersects")
        a = shapely.area(shapely.intersection(geoms[g_i], grid[c_i]))
        out[f"lc_{name}"] = np.clip(np.bincount(c_i, weights=a, minlength=len(cells)) / cell_area, 0, 1).round(3)
        log("landcover", name, "done")
    out.to_csv(LC, index=False)
log("static_landcover:", len(pd.read_csv(LC)), "cells")
