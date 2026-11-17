# BizdenBize

**BizdenBize** (Turkish for "from us", used with the hashtag #BizdenBize) is a daily wildfire-risk platform for Türkiye. It estimates, for every land cell of a 0.05° grid covering the whole country, how likely a wildfire is on each of the next seven days. The result is shown on an interactive map with four risk classes: *düşük* (low), *orta* (moderate), *yüksek* (high) and *aşırı* (extreme).

The project was developed for the COP31 Climate Tech Creathon in Antalya, Türkiye. The pilot region is Antalya–Muğla, and the national model is trained on the same method. The project's base article is Bilgili's *"Forest Fires in 2021"* (Kızılay Akademi), and the 2021 megafires it discusses serve as the main validation case.

---

## 1. How the system is organised (layers)

The system is built as a pipeline of five layers. Each layer reads the output of the layer before it, so the whole chain can be rebuilt from raw data by running the scripts in order.

| Layer | Question it answers | Main files |
|---|---|---|
| **1. Data acquisition** | Where can we obtain weather, fire, and geography data? | `bizdenbize/scripts/01_data_acquisition.py`, `03_fwi_turkiye.py` |
| **2. Labels (ground truth)** | On which cell-days did a wildfire actually occur? | `02_build_labels.py`, `04_grid_labels_turkiye.py` |
| **3. Features** | What is known about each cell on each day? | `firebridge_core.py`, `firebridge_fwi.py` |
| **4. Model** | How risky is each cell, given its features? | `05_train_turkiye.py` → `models/fire_lgbm_turkiye.joblib` |
| **5. Output and dashboard** | What does the public see? | `06_predict_live.py` → `bizdenbize/dashboard/` |

### Layer 1 — Data acquisition
This layer downloads or prepares the raw inputs. `03_fwi_turkiye.py` requests the Fire Weather Index (FWI) system variables for Türkiye, one year at a time, from the Copernicus Emergency Management Service. `01_data_acquisition.py` is the earlier pilot version that fetches the same kind of data for the Antalya–Muğla box and the OpenStreetMap layers. Both scripts cache their results, so an interrupted run can resume without downloading everything again.

### Layer 2 — Labels
A label records whether a fire happened in a given cell on a given day. `02_build_labels.py` builds this table for the pilot region, and `04_grid_labels_turkiye.py` builds it nationally. The script drops detections with low VIIRS confidence. It also removes persistent heat sources such as factories, flares, and landfills, because these are hot every day but do not spread as wildfires. A spot is treated as persistent when it shows heat on ten or more different days. Cell-days that look like agricultural burning are excluded from training and evaluation, rather than being counted as "no fire." This choice prevents the model from learning that field burning is the same as a forest fire.

### Layer 3 — Features
`firebridge_core.py` holds the shared feature code. It is used by both training and live prediction, so the two always build the same input table. The features fall into four groups:

- **Weather (cuaca):** the six FWI components (FFMC, DMC, DC, ISI, BUI and the FWI itself), together with 3-day and 7-day rolling means and maxima, the 7-day change in the Drought Code, and the day of the year. Rolling windows never cross from one year into the next.
- **Human access (manusia):** distance from each cell to the nearest road, settlement, and farmland, and the total road length inside the cell. Human-caused fires cluster near access routes, so these distances carry much of the signal.
- **History (histori):** the number of fire-days per year in the cell and in its 3×3 neighbourhood. Training uses only other training years, so the history feature never sees the answer for the year it is predicting.
- **Environment (lingkungan):** land-cover shares from ESA WorldCover 2021 (tree, shrub, grass, cropland, built-up) and elevation and slope from the Copernicus DEM GLO-90.

`firebridge_fwi.py` implements the Canadian FWI equations in Python. The live pipeline needs this module because weather forecasts do not come with FWI values, so the indices must be computed from temperature, humidity, wind, and rain.

### Layer 4 — Model
The model is a **LightGBM** gradient-boosted decision-tree classifier. A logistic regression is trained alongside it as a baseline. Because wildfire cell-days are rare, the script keeps every fire cell-day and a random 5 % sample of the other cell-days, and then gives each sampled non-fire row a weight of 1/0.05. This keeps the model calibrated to the real frequency while making training fast. The main hyperparameters are a learning rate of 0.03, 80 % row and column subsampling, and a minimum of 200 samples per leaf. The number of leaves and the class weight were tuned on the 2024 validation year.

The script uses a strict time split. Training uses 2021–2023 and validates on 2024. The test year is 2025, trained on 2021–2024. A separate hindcast model is trained on 2022–2025 and predicts 2021, so the team can check the model against the megafire week of 27 July to 2 August 2021. The live model is trained on all of 2021–2025. Each cell's score is converted into a risk class using cut-points found on out-of-sample data. The output uses the cut-points 0.30, 0.55, and 0.75.

### Layer 5 — Output and dashboard
`06_predict_live.py` runs once a day, for example from Windows Task Scheduler at 06:00. It takes the current FWI state, carries it forward using Open-Meteo weather, runs the FWI equations for the next seven days, and scores every cell with the live model. It also pulls the most recent NASA FIRMS hotspots so that the map can show active fires alongside the forecast. The result is written to `data.live.json`, which the browser dashboard (`index.html`, `app.js`) reads. The dashboard also has a demo mode and a pilot mode, so the same interface can display the 2021 hindcast.

---

## 2. Algorithm in brief

For each cell *c* and day *t*, the model estimates the probability that a wildfire is burning or will burn in that cell:

> p(c, t) = LightGBM( weather(c, t), human access(c), history(c), environment(c) )

The raw probability is then combined with the FWI value of the cell to produce the final score. The FWI acts as a ceiling, so a cell with a low fire-weather index cannot be shown as extreme risk merely because of its other features. The score is mapped to the four classes described above. In the hindcast week, the team also reported which classes the burning cells fell into, and whether the highest-risk cells coincided with the 2021 megafire sites at Manavgat, Gündoğmuş, Akseki, Marmaris, Köyceğiz, Milas, and Bodrum.

### Evaluation
The model is judged with two metrics that suit rare events. **ROC-AUC** measures how well the model ranks risky cell-days above safe ones. **PR-AUC** (average precision) measures how precise the top-ranked predictions are, and it is more demanding when fires are rare. The team also reports the share of actual fires that fall inside the top 5 % of predicted risk. Results are taken from `models/metrics_turkiye.csv`. For the 2025 test year on all of Türkiye, the LightGBM model reaches a ROC-AUC of 0.915, compared with 0.669 for the FWI value alone and 0.881 for logistic regression. Its PR-AUC is 0.010. This number looks low, but it reflects how rare fires are in the data, so the figure should be read alongside the ROC-AUC rather than on its own. The top-5 % capture rate is 58.5 %, against 14.6 % for FWI alone.

---

## 3. Data sources

| Data | Source | Used for | Where it is stored |
|---|---|---|---|
| Fire Weather Index and sub-indices (FFMC, DMC, DC, ISI, BUI), 2021–2026 | Copernicus EWDS, dataset `cems-fire-historical-v1` (EFFIS/CEMS reanalysis) | Weather features; training; the FWI start state for live runs | `data/turkiye/fwi_tr_<year>.grib` |
| Daily weather forecast and archive | Open-Meteo (no key required) | Live forecast of FWI for the next seven days | Fetched at run time |
| Active-fire hotspots, VIIRS | EFFIS hotspot export (`hs_viirs`, Türkiye, 2021–2026) | Fire labels | `data/a29cb7c7d8004c7c81778ad1bd237a5b.csv` |
| Near-real-time hotspots | NASA FIRMS (requires a free map key) | Active fires on the live map | Fetched at run time |
| Roads, settlements, farmland, land use | OpenStreetMap via Geofabrik (`turkey-latest-free`) | Human-access features | `data/turkey-latest-free.shp.zip`, `data/turkiye/osm_*.gpkg` |
| Administrative boundaries | OpenStreetMap, admin level 6 (districts) and the national outline | Land mask (cells that are at least 30 % land) | `data/turkiye/adminareas.gpkg` |
| Land cover | ESA WorldCover 2021 | Environment features | `data/turkiye/static_landcover.csv` |
| Elevation and slope | Copernicus DEM GLO-90 | Environment features | `data/turkiye/static_env.csv` |
| Megafire reference sites, 2021 | Listed in `firebridge_core.py` (seven sites, including Manavgat and Marmaris) | Validation of the hindcast week | `bizdenbize/scripts/firebridge_core.py` |

Calibration of the FWI implementation was checked against CEMS values using Open-Meteo weather, so that the live FWI matches the reanalysis closely. The check is carried out by `06b_check_fwi_calibration.py`, and its results are stored in `data/turkiye/fwi_calibration.json`.

Key cell-level tables are stored in `data/turkiye/`: `cells.csv` (the land cells), `static_human.csv` (distances and road lengths), `static_env.csv` (environment), and `fire_pos.csv` / `fire_pos_wild.csv` (positive cell-days).

---

## 4. Repository layout

```
JUKUT/
├── bizdenbize/
│   ├── scripts/        pipeline scripts 01–06, firebridge_core.py, firebridge_fwi.py
│   └── dashboard/      index.html, app.js, data*.json (demo, pilot, hindcast, live)
├── api/                historical CEMS notebook
├── data/               raw and derived data (see section 3)
├── labels/             labels_pilot.csv (pilot labels)
└── models/             trained model (.joblib) and metric tables and training logs
```

## 5. How to run

1. Install the Python dependencies: `cdsapi`, `geopandas`, `xarray`, `cfgrib`, `lightgbm`, `scikit-learn`, `scipy`, `shapely`, `requests`, `pandas`, `numpy`, and `joblib`.
2. Create `~/.cdsapirc` with a Copernicus EWDS key, and set `FIRMS_MAP_KEY` (or add it to `.env`) for NASA FIRMS.
3. Run `03_fwi_turkiye.py` to download the FWI archive, then `04_grid_labels_turkiye.py` to build the grid and labels.
4. Run `05_train_turkiye.py --export` to train the model and write the dashboard data. Add `--no-history` to produce the variant without history features.
5. Run `06_predict_live.py` for the daily map. Open `bizdenbize/dashboard/index.html` in a browser to view it.

## 6. Limitations

- The labels come from satellite hotspots, which detect only fires that are large or hot enough to be seen. Small fires that burn out quickly are missed.
- Agricultural and industrial burning is removed with heuristics, so some real fires are lost along with false alarms.
- The FWI system was designed for Canadian forests. Its fuel assumptions may not match all Turkish vegetation types, although the model's land-cover and history features help correct for this.
- Open-Meteo forecasts become less accurate beyond a few days, so risk for days five to seven is less reliable than for today and tomorrow.
- The risk map shows where conditions favour fire, not where a fire will start. It is a decision-support tool for prevention planning, not a replacement for the official warnings issued by the Turkish forestry authorities (OGM).

## 7. Team and status

The team is made up of Indonesian students studying in Türkiye. Pilot work is based in Antalya and Muğla in Türkiye, with a planned pilot in Central Kalimantan, Indonesia. An awareness-raising campaign is planned alongside the technical work.

---

*Licence and contributor details: to be added by the team.*
