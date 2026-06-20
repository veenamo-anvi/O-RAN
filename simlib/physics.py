"""Physics-based cell KPI generation.

generate_cell_kpi(cell, load, cls, rng) -> full cell_kpi field dict, with features
correlated to the cell's hardware specs and the target health class. Feature ranges are
aligned with the KPI agent's rule thresholds (OVERLOAD PRB>85, UNDERLOAD PRB<20,
SINR_LOW SINR<5, POWER_WASTE power>500W & UEs<15) so labels are physically consistent.
"""
from __future__ import annotations

import random
from typing import Any

CLASSES = ["NORMAL", "OVERLOAD", "UNDERLOAD", "SINR_LOW", "POWER_WASTE"]
CLASS_WEIGHTS = [0.70, 0.15, 0.08, 0.05, 0.02]


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def pick_dataset_class(rng: random.Random) -> str:
    return rng.choices(CLASSES, weights=CLASS_WEIGHTS, k=1)[0]


def pick_live_class(load: float, rng: random.Random) -> str:
    """Class for a live sim cycle — mostly NORMAL, natural OVERLOAD at peak load,
    occasional injected anomalies so the KPI agent has something to act on."""
    r = rng.random()
    if load >= 0.88 and r < 0.45:
        return "OVERLOAD"
    if r < 0.03:
        return "SINR_LOW"
    if r < 0.05:
        return "POWER_WASTE"
    if load <= 0.12 and r < 0.40:
        return "UNDERLOAD"
    return "NORMAL"


def generate_cell_kpi(cell: dict[str, Any], load: float, cls: str, rng: random.Random) -> dict[str, Any]:
    max_ues = int(cell.get("max_ues", 300) or 300)
    peak = float(cell.get("peak_dl_mbps", 200) or 200)
    tx = float(cell.get("tx_power_w", 320) or 320)
    idle = float(cell.get("idle_power_w", 100) or 100)

    if cls == "OVERLOAD":
        prb = rng.uniform(86, 99); ue_frac = rng.uniform(0.85, 1.0)
        sinr = rng.uniform(4, 11); latency = rng.uniform(45, 95); bler = rng.uniform(9, 19)
        power = idle + (tx - idle) * rng.uniform(0.85, 1.0)
    elif cls == "UNDERLOAD":
        prb = rng.uniform(3, 19); ue_frac = rng.uniform(0.01, 0.12)
        sinr = rng.uniform(13, 25); latency = rng.uniform(5, 15); bler = rng.uniform(0, 2)
        power = idle + (tx - idle) * rng.uniform(0.05, 0.20)
    elif cls == "SINR_LOW":
        prb = rng.uniform(28, 78); ue_frac = rng.uniform(0.25, 0.70)
        sinr = rng.uniform(-4, 4.5); latency = rng.uniform(28, 65); bler = rng.uniform(11, 20)
        power = idle + (tx - idle) * _clamp(prb / 100, 0, 1)
    elif cls == "POWER_WASTE":
        # few UEs but high power -> keep connected_ues < 15 even on max_ues=900 cells
        prb = rng.uniform(2, 14); ue_frac = rng.uniform(0.0, 0.014)
        sinr = rng.uniform(12, 24); latency = rng.uniform(6, 16); bler = rng.uniform(0, 2)
        power = idle + (tx - idle) * rng.uniform(0.60, 0.85)
    else:  # NORMAL — driven by live load
        prb = _clamp(load * rng.uniform(75, 92), 4, 84)
        ue_frac = _clamp(load * rng.uniform(0.85, 1.05), 0.02, 0.83)
        sinr = rng.uniform(8, 22); latency = rng.uniform(8, 32); bler = rng.uniform(1, 6)
        power = idle + (tx - idle) * _clamp(prb / 100, 0, 1)

    connected = int(_clamp(ue_frac * max_ues * rng.uniform(0.92, 1.04), 0, max_ues))
    eff = _clamp((sinr + 5) / 30, 0.12, 1.0)
    dl = round(peak * _clamp(prb / 100, 0, 1) * eff * rng.uniform(0.90, 1.05), 1)
    ul = round(dl * rng.uniform(0.10, 0.25), 1)
    cqi = int(_clamp(round((sinr + 6) / 2), 1, 15))
    mcs = int(_clamp(round(cqi * 1.85), 0, 28))
    rsrp = round(rng.uniform(-118, -100) if cls == "SINR_LOW" else rng.uniform(-108, -80), 1)
    rsrq = round(rng.uniform(-19, -12) if cls == "SINR_LOW" else rng.uniform(-12, -3), 1)
    pkt = round(_clamp(bler * rng.uniform(0.04, 0.18) + (latency > 50) * rng.uniform(0.1, 0.6), 0, 8), 2)
    jitter = round(latency * rng.uniform(0.05, 0.20), 2)
    interf = round(rng.uniform(-100, -90) if cls == "SINR_LOW" else rng.uniform(-112, -100), 1)
    prb_ul = round(_clamp(prb * rng.uniform(0.4, 0.7), 0, 100), 1)

    return {
        "connected_ues": connected,
        "prb_dl_pct": round(prb, 1),
        "prb_ul_pct": prb_ul,
        "sinr_db": round(sinr, 1),
        "rsrp_dbm": rsrp,
        "rsrq_db": rsrq,
        "dl_throughput_mbps": dl,
        "ul_throughput_mbps": ul,
        "power_w": round(power, 1),
        "packet_loss_pct": pkt,
        "cqi": cqi,
        "mcs": mcs,
        "bler_pct": round(bler, 1),
        "latency_ms": round(latency, 1),
        "jitter_ms": jitter,
        "interference_dbm": interf,
    }
