"""Geo + propagation helpers for planning."""
from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def cost231_walfisch_ikegami(dist_m: float, freq_mhz: float) -> float:
    """Simplified COST-231 Walfisch-Ikegami urban NLOS path loss (dB).

    Used for MIP link-budget feasibility. Parameters fixed to a dense-urban macro profile
    (hb=25m roof=20m, w=25m, b=40m, hm=1.5m). Returns path loss in dB for dist>=20 m.
    """
    d_km = max(dist_m, 20.0) / 1000.0
    f = freq_mhz
    # free-space term
    lfs = 32.45 + 20 * math.log10(d_km) + 20 * math.log10(f)
    # rooftop-to-street diffraction (Lrts) + multiscreen (Lmsd), dense-urban constants
    lrts = -16.9 - 10 * math.log10(25.0) + 10 * math.log10(f) + 20 * math.log10(20.0 - 1.5) + 9.646
    lmsd = -18.0 + 18 * math.log10(d_km) + (-2.0 + 0.7 * (f / 925.0 - 1)) * math.log10(f) - 9 * math.log10(40.0)
    return lfs + max(0.0, lrts) + max(0.0, lmsd)


def predicted_sinr_db(dist_m: float, freq_mhz: float, eirp_dbm: float = 63.0) -> float:
    """Crude received-SINR estimate from WI path loss for QoS feasibility checks."""
    pl = cost231_walfisch_ikegami(dist_m, freq_mhz)
    noise_dbm = -95.0
    rx = eirp_dbm - pl
    return rx - noise_dbm
