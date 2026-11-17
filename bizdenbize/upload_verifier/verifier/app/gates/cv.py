"""Gate 3: YOLOv8 ONNX detection + Farneback optical-flow smoke physics -> CV score in [0,1]."""
from __future__ import annotations

import pathlib
import cv2
import numpy as np
import onnxruntime as ort

MODEL = pathlib.Path(__file__).resolve().parents[2] / "models" / "best.onnx"
CLASSES = ["smoke", "fire"]
CONF = 0.35
IMGSZ = 640
_sess = None


def _session():
    global _sess
    if _sess is None:
        _sess = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])
    return _sess


def letterbox(frame: np.ndarray, size: int = IMGSZ) -> tuple[np.ndarray, float, int, int]:
    """Resize keeping aspect ratio and pad with gray (114), exactly like Ultralytics does in training.
    Stretching a 16:9 phone frame to a square squashes smoke plumes and lowers confidence."""
    h, w = frame.shape[:2]
    r = size / max(h, w)
    nw, nh = round(w * r), round(h * r)
    px, py = (size - nw) // 2, (size - nh) // 2
    out = np.full((size, size, 3), 114, dtype=np.uint8)
    out[py:py + nh, px:px + nw] = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
    return out, r, px, py


def unletterbox(boxes: np.ndarray, r: float, px: int, py: int, w: int, h: int) -> list[list[int]]:
    """Model-space (cx, cy, bw, bh) -> original-image [x, y, w, h], clipped to the image."""
    out = []
    for cx, cy, bw, bh in boxes:
        x0 = np.clip((cx - bw / 2 - px) / r, 0, w)
        y0 = np.clip((cy - bh / 2 - py) / r, 0, h)
        x1 = np.clip((cx + bw / 2 - px) / r, 0, w)
        y1 = np.clip((cy + bh / 2 - py) / r, 0, h)
        out.append([int(x0), int(y0), int(x1 - x0), int(y1 - y0)])
    return out


def detect(frame: np.ndarray) -> list[dict]:
    h, w = frame.shape[:2]
    img, r, px, py = letterbox(frame)
    blob = img[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255
    out = _session().run(None, {_session().get_inputs()[0].name: blob})[0][0].T  # (8400, 4+nc)
    boxes, scores, cls = out[:, :4], out[:, 4:].max(1), out[:, 4:].argmax(1)
    keep = scores > CONF
    boxes, scores, cls = boxes[keep], scores[keep], cls[keep]
    xywh = unletterbox(boxes, r, px, py, w, h)
    idx = cv2.dnn.NMSBoxes(xywh, scores.tolist(), CONF, 0.45)
    return [{"cls": CLASSES[int(cls[i])], "conf": float(scores[i]), "box": xywh[i]}
            for i in np.array(idx).flatten()]


def camera_motion(g0: np.ndarray, g1: np.ndarray, box_mask: np.ndarray) -> tuple[float, float] | None:
    """Median shift of textured background points OUTSIDE the smoke box = hand shake / panning.
    Uses tracked corners, not dense flow, because flat sky has no texture and would read as 'still'."""
    pts = cv2.goodFeaturesToTrack(g0, maxCorners=300, qualityLevel=0.01, minDistance=7,
                                  mask=(~box_mask).astype(np.uint8) * 255)
    if pts is None or len(pts) < 10:
        return None
    nxt, st, _ = cv2.calcOpticalFlowPyrLK(g0, g1, pts, None)
    good = st.ravel() == 1
    if good.sum() < 10:
        return None
    d = (nxt[good] - pts[good]).reshape(-1, 2)
    return float(np.median(d[:, 0])), float(np.median(d[:, 1]))


def flow_score(f0: np.ndarray, f1: np.ndarray, box, max_side: int = 480) -> float:
    """Share of moving pixels inside the smoke box that go UP after removing camera motion
    (smoke rises; fog/cloud drifts sideways or sits still)."""
    s = min(1.0, max_side / max(f0.shape[:2]))
    g0 = cv2.cvtColor(cv2.resize(f0, None, fx=s, fy=s), cv2.COLOR_BGR2GRAY)
    g1 = cv2.cvtColor(cv2.resize(f1, None, fx=s, fy=s), cv2.COLOR_BGR2GRAY)
    x, y, bw, bh = (int(round(v * s)) for v in box)
    x, y = max(0, x), max(0, y)
    mask = np.zeros(g0.shape, bool)
    mask[y:y + bh, x:x + bw] = True
    if mask.sum() < 400:
        return 0.5

    flow = cv2.calcOpticalFlowFarneback(g0, g1, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    cam = camera_motion(g0, g1, mask)
    if cam is not None:
        flow = flow - np.array(cam, dtype=np.float32)
    dx, dy = flow[..., 0][mask], flow[..., 1][mask]
    moving = np.hypot(dx, dy) > 0.5
    if moving.mean() < 0.05:
        return 0.2  # static -> likely cloud/photo of a screen
    upward = (dy < 0) & (np.abs(dy) > np.abs(dx) * 0.5) & moving
    return float(upward.sum() / moving.sum())


def cv_gate(frames, flow_pair: list[np.ndarray] | None = None) -> dict:
    """frames: 1-fps keyframes for detection. flow_pair: two frames ~0.2 s apart (videos only)."""
    dets = [detect(f) for f in frames]
    flat = [d for ds in dets for d in ds]
    if not flat:
        return {"score": 0.0, "detections": []}
    best_conf = max(d["conf"] for d in flat)
    flow = None
    if flow_pair is not None:
        smoke = [d for d in detect(flow_pair[0]) if d["cls"] == "smoke"]
        if smoke:
            flow = flow_score(flow_pair[0], flow_pair[1], max(smoke, key=lambda d: d["conf"])["box"])
    score = best_conf * (0.4 + 0.6 * flow) if flow is not None else best_conf * 0.8
    return {"score": round(score, 3), "max_conf": best_conf, "flow_upward": flow, "detections": dets}
