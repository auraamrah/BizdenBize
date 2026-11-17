"""Gate 4: multimodal LLM forensic audit (biome, screen-recording/watermark, AI-generated look).
Sun position is computed deterministically with pysolar, not guessed by the LLM."""
from __future__ import annotations

import json, os
from datetime import datetime, timezone

import cv2
from pysolar.solar import get_altitude

MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")  # use the current Flash model your credits cover

PROMPT = """You are a forensic auditor for citizen wildfire reports.
Claimed location: lat {lat}, lon {lon} ({region}). Capture time (UTC): {ts} [{ts_src}].
Computed sun altitude at that place/time: {sun:.1f} degrees ({daynight}).
Inspect the attached keyframes and answer ONLY with JSON:
{{"biome_match": 0-1, "lighting_matches_sun": 0-1, "screen_recording_or_watermark": 0-1,
  "ai_generated_likelihood": 0-1, "is_fire_or_smoke": 0-1, "reason": "<one sentence>"}}
biome_match: does the vegetation/terrain fit the region (e.g. Antalya Calabrian pine maquis vs Kalimantan peat swamp)?
lighting_matches_sun: does the sky brightness fit the computed sun altitude (night if below 0)?"""


def sun_altitude(lat, lon, when: datetime) -> float:
    return get_altitude(lat, lon, when)


def llm_gate(frames, lat, lon, region: str, when: datetime | None = None) -> dict:
    """when = capture time from EXIF/video metadata. If unknown we fall back to upload time,
    which is still right for live reports (the frontend should record, not pick from gallery)."""
    ts_src = "from file metadata" if when else "upload time; capture time unknown"
    when = when or datetime.now(timezone.utc)
    sun = sun_altitude(lat, lon, when)
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        parts = [types.Part.from_bytes(data=cv2.imencode(".jpg", f)[1].tobytes(), mime_type="image/jpeg")
                 for f in frames[:3]]
        parts.append(PROMPT.format(lat=lat, lon=lon, region=region, ts=when.isoformat(), ts_src=ts_src,
                                   sun=sun, daynight="day" if sun > 0 else "night"))
        resp = client.models.generate_content(
            model=MODEL, contents=parts,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0))
        r = json.loads(resp.text)
    except Exception as e:  # LLM down -> neutral, never block the pipeline
        return {"score": 0.5, "error": str(e), "sun_altitude": sun, "time_used": when.isoformat()}
    score = (r["biome_match"] + r["lighting_matches_sun"] + r["is_fire_or_smoke"]
             + (1 - r["screen_recording_or_watermark"]) + (1 - r["ai_generated_likelihood"])) / 5
    if r["screen_recording_or_watermark"] > 0.7:
        score = min(score, 0.2)
    return {"score": round(score, 3), "sun_altitude": sun, "time_used": when.isoformat(), **r}
