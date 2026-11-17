"""Canadian Forest Fire Weather Index System (Van Wagner 1987), vectorised over points.

Inputs per day are noon local values: temperature (°C), relative humidity (%), 10 m wind (km/h) and
24 h precipitation (mm) ending at noon. The moisture codes (FFMC, DMC, DC) carry memory from the
previous day, so every call needs yesterday's codes.
"""
import numpy as np

# day-length factors (northern hemisphere, ~ lat 30-60 N) for DMC and DC
DMC_LE = np.array([6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.0, 6.0])
DC_LF = np.array([-1.6, -1.6, -1.6, 0.9, 3.8, 5.8, 6.4, 5.0, 2.4, 0.4, -1.6, -1.6])


def ffmc(T, H, W, ro, F0):
    H = np.clip(H, 0, 100)
    mo = 147.2 * (101 - F0) / (59.5 + F0)
    rf = np.where(ro > 0.5, ro - 0.5, 0.0)
    rain = ro > 0.5
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        add = 42.5 * rf * np.exp(-100 / (251 - mo)) * (1 - np.exp(-6.93 / np.where(rain, rf, 1)))
        add = np.where(mo > 150, add + 0.0015 * (mo - 150) ** 2 * np.sqrt(rf), add)
    mo = np.where(rain, np.minimum(mo + add, 250), mo)
    ed = 0.942 * H ** 0.679 + 11 * np.exp((H - 100) / 10) + 0.18 * (21.1 - T) * (1 - np.exp(-0.115 * H))
    ew = 0.618 * H ** 0.753 + 10 * np.exp((H - 100) / 10) + 0.18 * (21.1 - T) * (1 - np.exp(-0.115 * H))
    ko = 0.424 * (1 - (H / 100) ** 1.7) + 0.0694 * np.sqrt(W) * (1 - (H / 100) ** 8)
    kd = ko * 0.581 * np.exp(0.0365 * T)
    k1 = 0.424 * (1 - ((100 - H) / 100) ** 1.7) + 0.0694 * np.sqrt(W) * (1 - ((100 - H) / 100) ** 8)
    kw = k1 * 0.581 * np.exp(0.0365 * T)
    m = np.where(mo > ed, ed + (mo - ed) * 10 ** (-kd),
                 np.where(mo < ew, ew - (ew - mo) * 10 ** (-kw), mo))
    return np.clip(59.5 * (250 - m) / (147.2 + m), 0, 101)


def dmc(T, H, ro, P0, month):
    T = np.maximum(T, -1.1)
    K = 1.894 * (T + 1.1) * (100 - np.clip(H, 0, 100)) * DMC_LE[month - 1] * 1e-6
    re = 0.92 * ro - 1.27
    Mo = 20 + np.exp(5.6348 - P0 / 43.43)
    with np.errstate(divide="ignore", invalid="ignore"):
        lnP = np.log(np.maximum(P0, 1e-6))
        b = np.where(P0 <= 33, 100 / (0.5 + 0.3 * P0), np.where(P0 <= 65, 14 - 1.3 * lnP, 6.2 * lnP - 17.2))
        Mr = Mo + 1000 * re / (48.77 + b * re)
        Pr = np.maximum(244.72 - 43.43 * np.log(np.maximum(Mr - 20, 1e-6)), 0)
    Pr = np.where(ro > 1.5, Pr, P0)
    return np.maximum(Pr + 100 * K, 0)


def dc(T, ro, D0, month):
    T = np.maximum(T, -2.8)
    V = np.maximum(0.36 * (T + 2.8) + DC_LF[month - 1], 0)
    rd = 0.83 * ro - 1.27
    Qr = 800 * np.exp(-D0 / 400) + 3.937 * rd
    with np.errstate(divide="ignore", invalid="ignore"):
        Dr = np.maximum(400 * np.log(800 / np.maximum(Qr, 1e-6)), 0)
    Dr = np.where(ro > 2.8, Dr, D0)
    return Dr + 0.5 * V


def isi(W, F):
    m = 147.2 * (101 - F) / (59.5 + F)
    fF = 91.9 * np.exp(-0.1386 * m) * (1 + m ** 5.31 / 4.93e7)
    return 0.208 * np.exp(0.05039 * W) * fF


def bui(P, D):
    with np.errstate(divide="ignore", invalid="ignore"):
        U = np.where(P <= 0.4 * D, 0.8 * P * D / (P + 0.4 * D),
                     P - (1 - 0.8 * D / (P + 0.4 * D)) * (0.92 + (0.0114 * P) ** 1.7))
    return np.nan_to_num(np.maximum(U, 0))


def fwi(R, U):
    fD = np.where(U <= 80, 0.626 * U ** 0.809 + 2, 1000 / (25 + 108.64 * np.exp(-0.023 * U)))
    B = 0.1 * R * fD
    with np.errstate(divide="ignore", invalid="ignore"):
        S = np.where(B > 1, np.exp(2.72 * (0.434 * np.log(np.maximum(B, 1e-6))) ** 0.647), B)
    return S


FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def fetch_noon_weather(lat, lon, url=FORECAST_URL, batch=100, **params):
    """Open-Meteo hourly weather -> noon (Europe/Istanbul) T, H, W and 24 h rain ending at noon.
    Returns (dates, {T, H, W, ro: [D, P]}). The first day has no full rain window and is dropped."""
    import time

    import pandas as pd
    import requests
    cols = {"T": [], "H": [], "W": [], "ro": []}
    dates = None
    for i in range(0, len(lat), batch):
        q = {"latitude": ",".join(f"{v:.3f}" for v in lat[i:i + batch]),
             "longitude": ",".join(f"{v:.3f}" for v in lon[i:i + batch]),
             "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation",
             "timezone": "Europe/Istanbul", "wind_speed_unit": "kmh", **params}
        for attempt in range(5):
            r = requests.get(url, params=q, timeout=120)
            if r.status_code == 429:                       # rate limit: back off and retry
                time.sleep(30 * (attempt + 1))
                continue
            r.raise_for_status()
            break
        res = r.json()
        res = res if isinstance(res, list) else [res]
        for loc in res:
            h = pd.DataFrame(loc["hourly"])
            h["time"] = pd.to_datetime(h["time"])
            h = h.set_index("time")
            rain24 = h.precipitation.rolling(24, min_periods=24).sum()     # 13:00 previous day .. 12:00
            noon = h[h.index.hour == 12]
            if dates is None:
                dates = noon.index.normalize()[1:]
            cols["T"].append(noon.temperature_2m.values[1:])
            cols["H"].append(noon.relative_humidity_2m.values[1:])
            cols["W"].append(noon.wind_speed_10m.values[1:])
            cols["ro"].append(rain24[noon.index].values[1:])
    return dates, {k: np.array(v, np.float64).T for k, v in cols.items()}


def run(weather, months, start):
    """weather: dict of [D, P] arrays T, H, W, ro; months: [D]; start: dict ffmc, dmc, dc of [P].
    Returns dict of [D, P] arrays fwi, ffmc, dmc, dc, isi, bui."""
    F, P, D = (np.asarray(start[k], np.float64) for k in ("ffmc", "dmc", "dc"))
    out = {k: [] for k in ("fwi", "ffmc", "dmc", "dc", "isi", "bui")}
    for d in range(len(months)):
        T, H, W, ro = (np.asarray(weather[k][d], np.float64) for k in ("T", "H", "W", "ro"))
        ro = np.nan_to_num(np.maximum(ro, 0))
        F, P, D = ffmc(T, H, W, ro, F), dmc(T, H, ro, P, months[d]), dc(T, ro, D, months[d])
        R, U = isi(W, F), bui(P, D)
        for k, v in zip(out, (fwi(R, U), F, P, D, R, U)):
            out[k].append(v)
    return {k: np.array(v, np.float32) for k, v in out.items()}
