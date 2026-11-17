"""Gate 1 (EXIF) + Gate 2 (pHash repost check) -> Meta score in [0,1]."""
from __future__ import annotations

import json, math, re, subprocess, shutil
from datetime import datetime, timedelta, timezone

import cv2
import imagehash
from PIL import Image

from ..store import known_hashes

MAX_AGE_H = 2
MAX_FUTURE_H = 0.25      # allow 15 min of phone clock drift; later than that = tampered/wrong clock
MAX_GPS_KM = 2.0
REPOST_HAMMING = 5

_TS = re.compile(r"(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?\s*(Z|[+-]\d{2}:?\d{2})?")
_OFF = re.compile(r"([+-])(\d{2}):?(\d{2})")


def _haversine_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def read_exif(path: str) -> dict:
    if not shutil.which("exiftool"):
        return {}
    out = subprocess.run(["exiftool", "-j", "-n", "-Make", "-Model", "-DateTimeOriginal",
                          "-OffsetTimeOriginal", "-OffsetTime", "-CreateDate", "-CreationDate",
                          "-GPSLatitude", "-GPSLongitude", path],
                         capture_output=True, text=True, timeout=10)
    try:
        return json.loads(out.stdout)[0]
    except Exception:
        return {}


def _offset(s) -> timezone | None:
    m = _OFF.fullmatch(str(s or "").strip())
    if not m:
        return None
    mins = int(m[2]) * 60 + int(m[3])
    return timezone(timedelta(minutes=mins if m[1] == "+" else -mins))


def _parse(ts) -> tuple[datetime | None, timezone | None]:
    """'2026:11:17 14:05:09+03:00' -> (naive datetime, tz or None). Rejects 0000:00:00 placeholders."""
    m = _TS.match(str(ts or ""))
    if not m or m[1] == "0000":
        return None, None
    try:
        dt = datetime(*map(int, m.groups()[:6]))
    except ValueError:
        return None, None
    tz = timezone.utc if m[7] == "Z" else _offset(m[7])
    return dt, tz


def capture_time(ex: dict, video: bool, tz_offset_min: int | None = None) -> tuple[datetime | None, str]:
    """Best-effort UTC capture time and where it came from.

    Photos store EXIF DateTimeOriginal in LOCAL time; the zone is in OffsetTimeOriginal (newer phones).
    Videos: QuickTime Keys CreationDate carries its own offset (iPhone); QuickTime CreateDate is UTC
    by spec. If no zone is recorded we use the browser's offset (the citizen is standing there);
    without that the time is unknown rather than guessed."""
    if video:
        dt, tz = _parse(ex.get("CreationDate"))
        if dt and tz:
            return dt.replace(tzinfo=tz).astimezone(timezone.utc), "video CreationDate (with offset)"
        dt, _ = _parse(ex.get("CreateDate"))
        if dt:
            return dt.replace(tzinfo=timezone.utc), "video CreateDate (UTC)"
        return None, "none"

    dt, tz = _parse(ex.get("DateTimeOriginal") or ex.get("CreateDate"))
    if not dt:
        return None, "none"
    tz = tz or _offset(ex.get("OffsetTimeOriginal")) or _offset(ex.get("OffsetTime"))
    if tz:
        return dt.replace(tzinfo=tz).astimezone(timezone.utc), "EXIF + OffsetTime"
    if tz_offset_min is not None:
        tz = timezone(timedelta(minutes=tz_offset_min))
        return dt.replace(tzinfo=tz).astimezone(timezone.utc), "EXIF + browser timezone"
    return None, "EXIF without timezone"


def exif_score(ex: dict, taken: datetime | None, browser_lat: float, browser_lon: float) -> tuple[float, dict]:
    """Missing EXIF is NEUTRAL (0.5): browsers/WhatsApp strip it from honest uploads."""
    detail = {"exif_present": bool(ex.get("Make") or ex.get("GPSLatitude"))}
    if not detail["exif_present"]:
        return 0.5, detail
    score = 0.6 if ex.get("Make") else 0.4
    if taken is not None:
        age_h = (datetime.now(timezone.utc) - taken).total_seconds() / 3600
        detail["age_hours"] = round(age_h, 2)
        score += 0.2 if -MAX_FUTURE_H <= age_h <= MAX_AGE_H else -0.4   # stale OR in the future
    if ex.get("GPSLatitude") is not None and ex.get("GPSLongitude") is not None:
        d = _haversine_km((ex["GPSLatitude"], ex["GPSLongitude"]), (browser_lat, browser_lon))
        detail["gps_mismatch_km"] = round(d, 2)
        score += 0.2 if d <= MAX_GPS_KM else -0.4
    return max(0.0, min(1.0, score)), detail


def phash_frames(frames) -> list[imagehash.ImageHash]:
    return [imagehash.phash(Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))) for f in frames]


def repost_check(hashes) -> tuple[bool, int | None]:
    best = None
    for h in hashes:
        for k in known_hashes():
            d = h - k
            best = d if best is None else min(best, d)
            if d < REPOST_HAMMING:
                return True, d
    return False, best


def meta_gate(frames, lat, lon, ex: dict, taken: datetime | None, time_source: str) -> dict:
    exif, detail = exif_score(ex, taken, lat, lon)
    hashes = phash_frames(frames)
    is_repost, dist = repost_check(hashes)
    return {
        "score": 0.0 if is_repost else exif,
        "repost": is_repost,
        "min_hamming": dist,
        "hashes": [str(h) for h in hashes],
        "capture_time_utc": taken.isoformat() if taken else None,
        "capture_time_source": time_source,
        **detail,
    }
