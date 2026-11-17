"""BizdenBize citizen upload verifier.  Run:  uvicorn app.main:app --reload"""
import asyncio, os, shutil, tempfile, time

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from .frames import extract_flow_pair, extract_keyframes, is_video
from .gates.cv import cv_gate
from .gates.env import env_gate, fov_cone
from .gates.llm import llm_gate
from .gates.meta import capture_time, meta_gate, read_exif
from .scoring import trust_score
from .store import add_hashes

app = FastAPI(title="BizdenBize Verifier")
MAX_BYTES = 50 * 1024 * 1024


@app.post("/verify")
async def verify(
    file: UploadFile = File(...),
    lat: float = Form(...),            # browser Geolocation API
    lon: float = Form(...),
    region: str = Form("Antalya, Türkiye"),
    azimuth: float | None = Form(None),  # DeviceOrientation compass heading
    tz_offset_min: int | None = Form(None),  # minutes EAST of UTC: -new Date().getTimezoneOffset()
):
    t0 = time.perf_counter()
    suffix = os.path.splitext(file.filename or "")[1] or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        path = tmp.name
    try:
        if os.path.getsize(path) > MAX_BYTES:
            raise HTTPException(413, "File too large")
        frames, flow_pair, exif = await asyncio.gather(
            asyncio.to_thread(extract_keyframes, path),
            asyncio.to_thread(extract_flow_pair, path),
            asyncio.to_thread(read_exif, path),
        )
        if not frames:
            raise HTTPException(400, "No frames extracted")
        taken, time_source = capture_time(exif, is_video(path), tz_offset_min)

        meta, cv, env, llm = await asyncio.gather(
            asyncio.to_thread(meta_gate, frames, lat, lon, exif, taken, time_source),
            asyncio.to_thread(cv_gate, frames, flow_pair),
            env_gate(lat, lon),
            asyncio.to_thread(llm_gate, frames, lat, lon, region, taken),
        )
        sub = {"cv": cv["score"], "llm": llm["score"], "meta": meta["score"], "env": env["score"],
               "hard_reject": meta["repost"]}
        score, badge = trust_score(sub)

        if badge != "quarantined":       # remember accepted uploads so later reposts are caught
            add_hashes(meta["hashes"])

        return {
            "trust_score": score,
            "badge": badge,               # green -> publish + WhatsApp; amber -> ask 3 km neighbours
            "subscores": sub,
            "fov_cone": fov_cone(lat, lon, azimuth) if azimuth is not None and badge == "green" else None,
            "gates": {"meta": meta, "cv": cv, "llm": llm, "env": env},
            "latency_s": round(time.perf_counter() - t0, 2),
        }
    finally:
        os.unlink(path)


@app.get("/health")
def health():
    return {"ok": True}
