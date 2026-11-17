"""Gate 5: Open-Meteo fire weather + NASA FIRMS VIIRS hotspots -> Env score in [0,1].
Also returns wind direction for the camera FOV cone on the map."""
import math, os
import httpx

FIRMS_KEY = os.getenv("FIRMS_MAP_KEY", "")


async def _weather(c: httpx.AsyncClient, lat, lon) -> dict:
    r = await c.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,vapour_pressure_deficit,"
                   "wind_speed_10m,wind_direction_10m,precipitation",
    })
    r.raise_for_status()
    return r.json()["current"]


async def _firms_hits(c: httpx.AsyncClient, lat, lon, radius_km=5) -> int:
    if not FIRMS_KEY:
        return -1
    d = radius_km / 111
    area = f"{lon - d:.4f},{lat - d:.4f},{lon + d:.4f},{lat + d:.4f}"
    r = await c.get(f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_KEY}/VIIRS_SNPP_NRT/{area}/1")
    r.raise_for_status()
    return max(0, len(r.text.strip().splitlines()) - 1)


def _fire_weather(w: dict) -> float:
    """Simple proxy: high VPD, low RH, wind, no rain -> conducive. (Swap for FFMC/DC if you compute them.)"""
    vpd = min(w.get("vapour_pressure_deficit", 0) / 3.0, 1)        # kPa, 3+ is extreme
    dry = 1 - min(w.get("relative_humidity_2m", 100) / 100, 1)
    wind = min(w.get("wind_speed_10m", 0) / 40, 1)
    rain_penalty = 0.5 if w.get("precipitation", 0) > 0.5 else 1
    return (0.45 * vpd + 0.35 * dry + 0.2 * wind) * rain_penalty


async def env_gate(lat, lon) -> dict:
    async with httpx.AsyncClient(timeout=6) as c:
        try:
            w = await _weather(c, lat, lon)
        except Exception as e:
            w = {"error": str(e)}
        try:
            hits = await _firms_hits(c, lat, lon)
        except Exception:
            hits = -1
    fw = _fire_weather(w) if "error" not in w else 0.5
    score = fw if hits <= 0 else max(fw, 0.9)   # satellite hotspot nearby = strong corroboration
    return {"score": round(score, 3), "fire_weather": round(fw, 3), "firms_hits_5km": hits,
            "wind_dir_deg": w.get("wind_direction_10m"), "wind_kmh": w.get("wind_speed_10m"), "weather": w}


def fov_cone(lat, lon, azimuth_deg, fov_deg=60, range_km=3, steps=8) -> list[list[float]]:
    """GeoJSON polygon coords for the orange camera FOV cone (azimuth from DeviceOrientation API)."""
    pts = [[lon, lat]]
    for i in range(steps + 1):
        b = math.radians(azimuth_deg - fov_deg / 2 + fov_deg * i / steps)
        pts.append([lon + range_km / (111 * math.cos(math.radians(lat))) * math.sin(b),
                    lat + range_km / 111 * math.cos(b)])
    pts.append([lon, lat])
    return pts
