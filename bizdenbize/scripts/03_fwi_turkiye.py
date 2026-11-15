"""FireBridge — FWI + sub-indices for the whole of Türkiye (Copernicus EWDS, cems-fire-historical-v1).

Same variables, years and months as the pilot (main.ipynb), but area = all of Türkiye.
One request per year keeps each request under the EWDS size limit; existing files are skipped.
Needs ~/.cdsapirc with url https://ewds.climate.copernicus.eu/api
Output: <JUKUT>/data/turkiye/fwi_tr_<year>.grib
"""
from pathlib import Path

import cdsapi

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "turkiye"
OUT.mkdir(parents=True, exist_ok=True)

N, W, S, E = 42.4, 25.5, 35.7, 45.0          # Türkiye + small margin
VARS = ["fire_weather_index", "drought_code", "fine_fuel_moisture_code", "duff_moisture_code",
        "initial_fire_spread_index", "build_up_index"]
MONTHS = {y: range(4, 13) for y in range(2021, 2026)} | {2026: range(4, 9)}   # Apr-Dec, 2026: Apr-Aug

for year, months in MONTHS.items():
    out = OUT / f"fwi_tr_{year}.grib"
    if out.exists():
        print("skip", out.name)
        continue
    request = {
        "product_type": "reanalysis", "variable": VARS, "system_version": ["4_1"],
        "dataset_type": "consolidated_dataset",
        "year": [str(year)], "month": [f"{m:02d}" for m in months], "day": [f"{d:02d}" for d in range(1, 32)],
        "grid": "original_grid", "area": [N, W, S, E], "data_format": "grib",
    }
    tmp = out.with_suffix(".part")
    cdsapi.Client().retrieve("cems-fire-historical-v1", request, str(tmp))
    tmp.rename(out)
    print("saved", out.name, out.stat().st_size // 1024, "KB")
