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

# ---------------------------------------------------------------- 6) satellite land cover + terrain
# ESA WorldCover 2021 (10 m, CC-BY 4.0) and Copernicus DEM GLO-90, both open COGs on AWS, read through
# their overviews so only a fraction of each tile is transferred. WorldCover stands in for CORINE
# (whose download needs a Copernicus Land account) and is complete where OSM land use is not.
ENVF = OUT / "static_env.csv"
WC_URL = ("/vsicurl/https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
          "ESA_WorldCover_10m_2021_v200_{ns}{lat:02d}E{lon:03d}_Map.tif")
DEM_URL = ("/vsicurl/https://copernicus-dem-90m.s3.amazonaws.com/Copernicus_DSM_COG_30_N{lat:02d}_00_E{lon:03d}_00_DEM/"
           "Copernicus_DSM_COG_30_N{lat:02d}_00_E{lon:03d}_00_DEM.tif")
WC_CLASSES = {"wc_tree": [10], "wc_shrub": [20], "wc_grass": [30], "wc_crop": [40], "wc_built": [50],
              "wc_bare": [60]}


def _read(url, size):
    import rasterio
    from rasterio.errors import RasterioIOError
    try:
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="4",
                          GDAL_HTTP_RETRY_DELAY="2"):
            with rasterio.open(url) as s:
                return s.read(1, out_shape=(size, size)), s.nodata
    except RasterioIOError:
        return None, None                                   # tile does not exist (open sea)


def _cell_index(lon0, lat0, deg, px_per_cell):
    """Grid (ix, iy) of the cells covered by a tile with lower-left corner (lon0, lat0)."""
    n = int(round(deg / CELL))
    ix0, iy0 = int(round((lon0 - LON0) / CELL)), int(round((lat0 - LAT0) / CELL))
    return n, ix0, iy0


def wc_tile(lat0, lon0):
    a, _ = _read(WC_URL.format(ns="N", lat=lat0, lon=lon0), 3000)     # 0.001 deg pixels, 50 per cell
    if a is None:
        return None
    n, ix0, iy0 = _cell_index(lon0, lat0, 3, 50)
    blocks = a.reshape(n, 50, n, 50).transpose(0, 2, 1, 3).reshape(n, n, -1)
    rows = []
    for r in range(n):                                       # raster row 0 is the northern edge
        for c in range(n):
            b = blocks[r, c]
            rows.append({"ix": ix0 + c, "iy": iy0 + n - 1 - r,
                         **{k: np.isin(b, v).mean() for k, v in WC_CLASSES.items()}})
    return pd.DataFrame(rows)


def dem_tile(lat0, lon0):
    z, nod = _read(DEM_URL.format(lat=lat0, lon=lon0), 1200)          # 3 arc-sec, 60 px per cell
    if z is None:
        return None
    z = z.astype(np.float32)
    if nod is not None:
        z[z == nod] = np.nan
    lat_c = lat0 + 0.5
    dy = 3 / 3600 * 111_320
    dx = dy * np.cos(np.radians(lat_c))
    gy, gx = np.gradient(z, dy, dx)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    n, ix0, iy0 = _cell_index(lon0, lat0, 1, 60)
    zb = z.reshape(n, 60, n, 60).transpose(0, 2, 1, 3).reshape(n, n, -1)
    sb = slope.reshape(n, 60, n, 60).transpose(0, 2, 1, 3).reshape(n, n, -1)
    rows = []
    for r in range(n):
        for c in range(n):
            rows.append({"ix": ix0 + c, "iy": iy0 + n - 1 - r, "elev_m": np.nanmean(zb[r, c]),
                         "slope_mean": np.nanmean(sb[r, c]), "slope_p90": np.nanpercentile(sb[r, c], 90)})
    return pd.DataFrame(rows)


if not ENVF.exists():
    import warnings
    from concurrent.futures import ThreadPoolExecutor
    warnings.filterwarnings("ignore", category=RuntimeWarning)          # all-NaN sea blocks
    with ThreadPoolExecutor(8) as ex:
        wc = [t for t in ex.map(lambda p: wc_tile(*p), [(la, lo) for la in (33, 36, 39, 42)
                                                       for lo in range(24, 45, 3)]) if t is not None]
        log("worldcover tiles:", len(wc))
        dem = [t for t in ex.map(lambda p: dem_tile(*p), [(la, lo) for la in range(35, 43)
                                                         for lo in range(25, 45)]) if t is not None]
        log("dem tiles:", len(dem))
    env = (cells[["ix", "iy"]].merge(pd.concat(wc), on=["ix", "iy"], how="left")
           .merge(pd.concat(dem), on=["ix", "iy"], how="left"))
    env.round(3).to_csv(ENVF, index=False)
env = pd.read_csv(ENVF)
log("static_env:", len(env), "cells | missing:", env.isna().sum().to_dict())

# ---------------------------------------------------------------- 7) wildfire-only labels
# VIIRS also sees agricultural stubble burning, which repeats every summer on the same farmland and
# swamped the wildfire signal (2021 megafire cells only reached "sedang"). A detection counts as a
# wildfire when its cell is mostly natural vegetation, or when it is part of a spreading event
# (>= CLUSTER_MIN detections in the cell's 3x3 neighbourhood over that day and the previous one).
# Other positives are not turned into negatives; 05 drops those cell-days from training.
WILD = OUT / "fire_pos_wild.csv"
VEG_MIN, CLUSTER_MIN, MAX_CROP, MAX_DAYS_PER_YEAR = 0.3, 8, 0.5, 15
if not WILD.exists():
    p = pos.merge(env[["ix", "iy", "wc_tree", "wc_shrub", "wc_grass", "wc_crop"]], on=["ix", "iy"], how="left")
    veg = (p.wc_tree.fillna(0) + p.wc_shrub.fillna(0)) >= VEG_MIN
    nat = (p.wc_tree.fillna(0) + p.wc_shrub.fillna(0) + p.wc_grass.fillna(0)) >= 0.5
    key = {(r.ix, r.iy, r.date): r.n for r in pos.itertuples()}
    one = pd.Timedelta(days=1)
    burst = np.array([sum(key.get((x + dx, y + dy, d - k * one), 0)
                          for dx in (-1, 0, 1) for dy in (-1, 0, 1) for k in (0, 1))
                      for x, y, d in zip(p.ix, p.iy, p.date)])
    # cropland (Harran, Çukurova, ...) burns in big clusters after harvest, so a cluster alone is not
    # enough there: the cluster rules only apply to cells that are not crop-dominated
    not_crop = p.wc_crop.fillna(0) < MAX_CROP
    # a 5 km cell with hotspots on >= MAX_DAYS_PER_YEAR days of one year is an industrial heat source
    # (Iskenderun steel, Aliağa refinery, ...) that the ~100 m spot filter misses because detections
    # jitter between spots; a wildfire burns a cell for a few days at most
    days_year = pos.groupby([pos.ix, pos.iy, pos.date.dt.year]).size()
    hot = days_year[days_year >= MAX_DAYS_PER_YEAR].reset_index()[["ix", "iy"]].drop_duplicates()
    persistent = p.set_index(["ix", "iy"]).index.isin(hot.set_index(["ix", "iy"]).index)
    p["wild"] = ((veg | (not_crop & ((nat & (burst >= CLUSTER_MIN // 2)) | (burst >= CLUSTER_MIN))))
                 & ~persistent).astype(np.int8)
    p[["ix", "iy", "date", "n", "wild"]].to_csv(WILD, index=False)
    log(f"persistent heat-source cells excluded: {len(hot)}")
wild = pd.read_csv(WILD, parse_dates=["date"])
log(f"wildfire cell-days: {wild.wild.sum()} of {len(wild)}")
print(wild.groupby(wild.date.dt.year).wild.agg(["sum", "size"]).to_string())
