"""Weighted Authenticity Trust Score. Weights/thresholds load from data/weights.json
(written by scripts/calibrate.py); defaults are the pitch-slide values."""
import json, pathlib

CFG = pathlib.Path(__file__).resolve().parent.parent / "data" / "weights.json"
DEFAULT = {"weights": {"cv": 0.25, "llm": 0.30, "meta": 0.20, "env": 0.25},
           "green": 80, "amber": 50}


def config() -> dict:
    return json.loads(CFG.read_text()) if CFG.exists() else DEFAULT


def trust_score(sub: dict[str, float]) -> tuple[float, str]:
    cfg = config()
    s = 100 * sum(w * sub[k] for k, w in cfg["weights"].items())
    if sub.get("hard_reject"):
        s = min(s, 20)
    badge = "green" if s >= cfg["green"] else "amber" if s >= cfg["amber"] else "quarantined"
    return round(s, 1), badge
