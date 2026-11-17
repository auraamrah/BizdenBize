"""Step 1a: keyframe extraction with FFmpeg (1 fps, max 5). Photos pass through as a single frame.
Also grabs a close-together frame pair (0.2 s apart) for the optical-flow smoke check."""
from __future__ import annotations

import subprocess, tempfile, pathlib
import cv2
import numpy as np

VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".3gp"}


def is_video(path: str) -> bool:
    return pathlib.Path(path).suffix.lower() in VIDEO_EXT


def extract_keyframes(path: str, max_frames: int = 5) -> list[np.ndarray]:
    if not is_video(path):
        img = cv2.imread(path)
        if img is None:
            raise ValueError("Unreadable image")
        return [img]
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", path, "-vf", "fps=1",
             "-frames:v", str(max_frames), f"{tmp}/f_%02d.jpg"],
            check=True, timeout=30,
        )
        return [cv2.imread(str(f)) for f in sorted(pathlib.Path(tmp).glob("f_*.jpg"))]


def extract_flow_pair(path: str, t: float = 0.5, dt: float = 0.2) -> list[np.ndarray] | None:
    """Two frames ~dt seconds apart, starting near t. At 1 fps, smoke changes shape and hand shake
    dominates, so optical flow needs frames this close. None for photos or unreadable clips."""
    if not is_video(path):
        return None
    cap = cv2.VideoCapture(path)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        fps = fps if 1 <= fps <= 240 else 30.0
        i0 = round(t * fps)
        i1 = i0 + max(1, round(dt * fps))
        read: list[np.ndarray] = []
        for i in range(i1 + 1):
            ok, f = cap.read()
            if not ok:
                break
            if i in (i0, i1):
                read.append(f)
        if len(read) == 2:
            return read
        # clip shorter than t+dt: fall back to the first two frames we can get
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ok0, f0 = cap.read()
        for _ in range(max(1, round(dt * fps)) - 1):
            cap.read()
        ok1, f1 = cap.read()
        return [f0, f1] if ok0 and ok1 else None
    finally:
        cap.release()
