"""FireBridge — Tahap 1 AKUISISI DATA ASLI (jalankan di laptop dengan internet).

Mengganti data demo (00_demo_data_tahap1_2.py) dengan tiga sumber sungguhan:
  1. FWI harian      -> Copernicus CEMS/EFFIS (dataset "cems-fire-historical-v1")
  2. Jalan+permukiman -> OpenStreetMap via osmnx (Overpass API)
  3. Histori kebakaran-> NASA FIRMS (titik api MODIS/VIIRS) + EFFIS Burnt Area;
                         data OGM resmi diminta terpisah (lihat catatan bawah).

Persiapan (sekali saja):
  pip install cdsapi osmnx geopandas xarray netcdf4 pandas requests
  - Akun gratis di https://cds.climate.copernicus.eu  -> simpan API key ke ~/.cdsapirc
  - API key gratis NASA FIRMS: https://firms.modaps.eosdis.nasa.gov/api/

Keluaran semuanya ke folder data_raw/ ; feature engineering memakai struktur
yang sama dengan Tahap 2 di 00_demo_data_tahap1_2.py (ganti bagian demo-nya).
"""

from pathlib import Path

OUT = Path("data_raw"); OUT.mkdir(exist_ok=True)

# Bounding box pilot — samakan dengan grid dashboard
LON0, LAT0, LON1, LAT1 = 27.2, 36.0, 32.4, 37.7
YEARS = [str(y) for y in range(2015, 2025)]      # periode training
FIRMS_KEY = "ISI_API_KEY_FIRMS_DI_SINI"

# ----------------------------------------------------------------------------
# 1) FWI harian dari Copernicus (EFFIS/CEMS reanalysis, GRIB/NetCDF)
# ----------------------------------------------------------------------------
def download_fwi():
    import cdsapi
    c = cdsapi.Client()
    c.retrieve(
        "cems-fire-historical-v1",
        {
            "product_type": "reanalysis",
            "variable": [
                "fire_weather_index",            # FWI utama
                "fine_fuel_moisture_code",       # FFMC (kering jam-an)
                "duff_moisture_code",            # DMC
                "drought_code",                  # DC (kering mingguan)
                "initial_fire_spread_index",     # ISI
                "build_up_index",                # BUI
            ],
            "dataset_type": "consolidated_dataset",
            "system_version": "4_1",
            "year": YEARS,
            "month": [f"{m:02d}" for m in range(4, 11)],   # musim kebakaran Apr-Okt
            "day": [f"{d:02d}" for d in range(1, 32)],
            "grid": "0.05/0.05",
            "area": [LAT1, LON0, LAT0, LON1],              # N, W, S, E
            "data_format": "netcdf",
        },
        OUT / "fwi_antalya_mugla.nc",
    )
    print("FWI tersimpan:", OUT / "fwi_antalya_mugla.nc")

# ----------------------------------------------------------------------------
# 2) Jalan & permukiman dari OpenStreetMap
# ----------------------------------------------------------------------------
def download_osm():
    import osmnx as ox
    bbox = (LAT1, LAT0, LON1, LON0)  # N, S, E, W (urutan osmnx <2.0; cek versimu)

    roads = ox.features_from_bbox(
        *bbox, tags={"highway": ["motorway", "trunk", "primary",
                                 "secondary", "tertiary", "unclassified"]})
    roads[["highway", "geometry"]].to_file(OUT / "osm_roads.gpkg", driver="GPKG")

    places = ox.features_from_bbox(
        *bbox, tags={"place": ["city", "town", "village", "hamlet"]})
    cols = [c for c in ["name", "place", "population"] if c in places.columns]
    places[cols + ["geometry"]].to_file(OUT / "osm_settlements.gpkg", driver="GPKG")

    # Opsional tapi berguna: lahan pertanian (sumber api pembakaran sisa panen)
    farm = ox.features_from_bbox(*bbox, tags={"landuse": ["farmland", "orchard"]})
    farm[["landuse", "geometry"]].to_file(OUT / "osm_farmland.gpkg", driver="GPKG")
    print("OSM tersimpan: jalan, permukiman, lahan pertanian (.gpkg)")

# ----------------------------------------------------------------------------
# 3) Histori kebakaran: NASA FIRMS (label per titik) — pelengkap/pengganti OGM
# ----------------------------------------------------------------------------
def download_firms():
    import pandas as pd
    frames = []
    for src in ["MODIS_SP", "VIIRS_SNPP_SP"]:           # arsip "standard processing"
        for y in YEARS:
            url = (f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
                   f"{FIRMS_KEY}/{src}/{LON0},{LAT0},{LON1},{LAT1}/365/{y}-01-01")
            try:
                df = pd.read_csv(url)
                df["source"] = src
                frames.append(df)
                print(f"FIRMS {src} {y}: {len(df)} titik")
            except Exception as e:                       # tahun kosong/kuota -> lanjut
                print(f"FIRMS {src} {y}: dilewati ({e})")
    pd.concat(frames, ignore_index=True).to_csv(OUT / "firms_fires.csv", index=False)
    print("FIRMS tersimpan:", OUT / "firms_fires.csv")

# ----------------------------------------------------------------------------
# 4) Poligon area terbakar EFFIS (validasi luas; unduhan manual satu kali)
# ----------------------------------------------------------------------------
EFFIS_NOTE = """
EFFIS Burnt Area (poligon, 2000-sekarang):
  https://forest-fire.emergency.copernicus.eu/applications/data-and-services
  -> "Burnt Areas" shapefile; filter negara = Türkiye, potong dengan bbox pilot.
Data resmi OGM (Orman Genel Müdürlüğü):
  statistik tahunan publik di https://www.ogm.gov.tr (Ormancılık İstatistikleri);
  untuk data kejadian rinci, ajukan permohonan data riset — lampirkan surat tim
  COP31; sambil menunggu, FIRMS + EFFIS Burnt Area sudah cukup sebagai label.
Elevasi/lereng (SRTM 30m): https://portal.opentopography.org  (GeoTIFF, gratis)
Tutupan lahan (CORINE 2018): https://land.copernicus.eu/en/products/corine-land-cover
"""

if __name__ == "__main__":
    print(EFFIS_NOTE)
    download_fwi()
    download_osm()
    download_firms()
