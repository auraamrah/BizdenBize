# BizdenBize – Citizen Upload Verification

```
training/train_detector.ipynb   Colab: D-Fire subset -> YOLOv8s -> best.onnx
verifier/app/main.py            FastAPI POST /verify (5 gates -> trust score + badge)
verifier/app/gates/meta.py      Gate 1+2: EXIF (missing = neutral) + pHash repost check
verifier/app/gates/cv.py        Gate 3: YOLO ONNX + Farneback "smoke rises" flow check
verifier/app/gates/llm.py       Gate 4: Gemini forensic audit; sun altitude via pysolar
verifier/app/gates/env.py       Gate 5: Open-Meteo fire weather + NASA FIRMS; FOV cone polygon
verifier/app/scoring.py         Weighted S_trust; reads data/weights.json if present
verifier/scripts/calibrate.py   Fits weights/thresholds on labeled test uploads
```

## 1. Train
Open `training/train_detector.ipynb` in Colab (T4), run all cells, and put the downloaded
`best.onnx` in `verifier/models/best.onnx`.

## 2. Run the verifier
Needs Python 3.11+, `ffmpeg` and `exiftool` (`brew install ffmpeg exiftool`).

```bash
cd verifier
python3.12 -m venv .venv && source .venv/bin/activate   # already done on this Mac
pip install -r requirements.txt
export GEMINI_API_KEY=...      # Creathon credits
export FIRMS_MAP_KEY=...       # free: firms.modaps.eosdis.nasa.gov/api/map_key
uvicorn app.main:app --reload --reload-dir app
```

Test it:
```bash
curl -F file=@smoke.mp4 -F lat=36.78 -F lon=31.44 -F azimuth=120 -F tz_offset_min=180 http://127.0.0.1:8000/verify
```

Response: `trust_score`, `badge` (`green` / `amber` / `quarantined`), `subscores`,
`fov_cone` (GeoJSON ring, green only) and per-gate details.

## 3. Seed the repost database
Add pHashes of known viral fire clips (e.g. 2021 Manavgat) as hex strings, one per line,
in `verifier/data/known_hashes.txt`. Accepted uploads are appended automatically.

## 4. Calibrate the weights
See the docstring in `verifier/scripts/calibrate.py`: ~100 labeled real/fake uploads ->
logistic-regression weights + ROC-picked thresholds in `data/weights.json`.

## Frontend contract
The upload form must send `lat`/`lon` from `navigator.geolocation` and, if available,
`azimuth` from `DeviceOrientationEvent` (compass heading) for the FOV cone.
It should also send `tz_offset_min = -new Date().getTimezoneOffset()` (minutes east of UTC):
photo EXIF times are local, and older phones don't record the zone, so without it the
photo-age check is skipped (neutral) instead of guessed.
