"""Learn trust-score weights + thresholds from ~100 labeled test uploads.

Usage:
  1. Put test files in verifier/data/calib/{real,fake}/  (fake = reposts, screen recordings,
     sunsets, fog, AI images). Name each file  <anything>__<lat>_<lon>.<ext>
  2. Start the API (uvicorn app.main:app) and run:  python scripts/calibrate.py
  3. Writes data/weights.json, which app/scoring.py picks up on the next request.
"""
import json, pathlib, sys

import httpx
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_curve

ROOT = pathlib.Path(__file__).resolve().parent.parent
API = "http://127.0.0.1:8000/verify"
KEYS = ["cv", "llm", "meta", "env"]


def collect():
    X, y = [], []
    for label, sub in ((1, "real"), (0, "fake")):
        for f in sorted((ROOT / "data" / "calib" / sub).glob("*")):
            try:
                lat, lon = map(float, f.stem.split("__")[1].split("_"))
            except (IndexError, ValueError):
                print("skip (bad name):", f.name); continue
            with f.open("rb") as fh:
                r = httpx.post(API, files={"file": (f.name, fh)},
                               data={"lat": lat, "lon": lon}, timeout=60).json()
            X.append([r["subscores"][k] for k in KEYS]); y.append(label)
            print(f"{sub:4} {f.name:40} {r['trust_score']:5.1f} {r['badge']}")
    return np.array(X), np.array(y)


def main():
    X, y = collect()
    if len(set(y)) < 2:
        sys.exit("Need both real and fake samples.")
    clf = LogisticRegression().fit(X, y)
    coef = np.clip(clf.coef_[0], 0, None)
    w = coef / coef.sum() if coef.sum() else np.full(4, .25)
    s = 100 * X @ w
    fpr, tpr, thr = roc_curve(y, s)
    green = float(thr[np.where(fpr <= 0.02)[0][-1]])          # <=2% false alarms get a green badge
    amber = float(thr[np.where(tpr >= 0.95)[0][0]])           # catch 95% of real fires at amber+
    cfg = {"weights": dict(zip(KEYS, map(lambda v: round(float(v), 3), w))),
           "green": round(min(green, 100), 1), "amber": round(min(amber, green), 1)}
    (ROOT / "data" / "weights.json").write_text(json.dumps(cfg, indent=2))
    print(json.dumps(cfg, indent=2))


if __name__ == "__main__":
    main()
