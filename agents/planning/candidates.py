"""Candidate cell sites + hardware catalogue for the Malleswaram planning problem.

Candidates are a SUPERSET of the deployed network so the planner has real choices.
Each candidate site expands into 3 sectors (cells) carrying full hardware metadata, so
plan_to_topology() can preserve vendor / hardware_model / generation / antenna_config /
tx_power_w / idle_power_w / peak_dl_mbps / freq_mhz / pci.

[R3 retired] Default deployed bands are n78/n41/B3/B40. n28 is accepted only when an
operator passes it explicitly in spectrum_bands; it is never injected here.
"""
from __future__ import annotations

from typing import Any

DEFAULT_BANDS = ["n78", "n41", "B3", "B40"]

# band -> (generation, freq_mhz, max_ues, peak_dl_mbps_4g, antenna)
BAND_SPEC = {
    "n78": ("5G", 3500, 900, None, "64T64R"),
    "n41": ("5G", 2500, 700, None, "64T64R"),
    "n28": ("5G",  700, 1200, None, "8T8R"),   # supported but never deployed by default
    "B40": ("4G", 2300, 300, 220, "4T4R"),
    "B3":  ("4G", 1800, 250, 150, "4T4R"),
}

SECTOR_PLAN = {
    "high": ["n78", "n41", "B3"],
    "res":  ["n78", "B40", "B3"],
}

VENDORS = {
    "Nokia":    {"hw5g": "AirScale MAA 64T64R", "hw4g": "AWHFA",    "peak5g": 3800, "power": 1000},
    "Ericsson": {"hw5g": "AIR 6449",            "hw4g": "RBS 6402", "peak5g": 3600, "power": 950},
    "Samsung":  {"hw5g": "TM500 64T64R",        "hw4g": "RRU",      "peak5g": 3400, "power": 900},
    "ZTE":      {"hw5g": "AAU 5614",            "hw4g": "RRU",      "peak5g": 3200, "power": 1000},
}
VENDOR_ORDER = ["Nokia", "Ericsson", "Samsung", "ZTE"]

# (code, area, lat, lon, profile, install_cost_usd, op_cost_usd_per_period)
CANDIDATE_SITES = [
    ("RWS", "Railway Station", 13.01210, 77.57050, "high", 180000, 22000),
    ("18C", "18th Cross",      13.00980, 77.56880, "high", 175000, 21000),
    ("BEL", "BEL Circle",      13.01550, 77.56620, "res",  150000, 18000),
    ("SNK", "Sankey Road",     13.00750, 77.57350, "high", 178000, 21500),
    ("SPG", "Sampige Road",    13.00420, 77.57080, "high", 176000, 21000),
    ("3MN", "3rd Main",        13.00280, 77.56720, "res",  148000, 17500),
    ("10C", "10th Cross",      13.00090, 77.57190, "high", 174000, 20800),
    ("MGR", "Margosa Road",    12.99820, 77.56810, "res",  147000, 17500),
    ("CHD", "Chowdiah",        12.99680, 77.56480, "res",  146000, 17000),
    ("6CR", "6th Cross",       12.99950, 77.56620, "res",  149000, 17800),
    # extra candidate sites (give the optimiser room to choose / reject)
    ("KKP", "Kuvempu Park",    13.01030, 77.57350, "res",  152000, 18200),
    ("MEK", "Malleswaram East",13.00650, 77.57600, "high", 181000, 22500),
    ("YPN", "Yeshwanthpur Edge",13.01700,77.57100, "high", 185000, 23000),
    ("SDP", "Sadashivanagar",  12.99550, 77.57050, "res",  151000, 18000),
]


def build_candidate_cells(bands: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """All candidate sector-cells. `bands` restricts which bands may appear; n28 only if
    explicitly included."""
    allowed = set(bands) if bands else set(DEFAULT_BANDS)
    cells: dict[str, dict[str, Any]] = {}
    idx = 0
    for code, area, lat, lon, profile, _ic, _oc in CANDIDATE_SITES:
        for sector, band in enumerate(SECTOR_PLAN[profile], start=1):
            if band not in allowed:
                continue
            gen, freq, max_ues, peak4g, antenna = BAND_SPEC[band]
            vendor = VENDOR_ORDER[idx % len(VENDOR_ORDER)]
            v = VENDORS[vendor]
            is5g = gen == "5G"
            cid = f"MLS_{code}_{sector:02d}"
            cells[cid] = {
                "cell_id": cid, "site": code, "area": area,
                "lat": round(lat + (sector - 2) * 0.00035, 6),
                "lon": round(lon + (sector - 2) * 0.00035, 6),
                "generation": gen, "band": band, "freq_mhz": freq,
                "vendor": vendor, "hardware_model": v["hw5g"] if is5g else v["hw4g"],
                "antenna_config": antenna,
                "peak_dl_mbps": v["peak5g"] if is5g else peak4g,
                "tx_power_w": v["power"] if is5g else 320,
                "idle_power_w": round((v["power"] if is5g else 320) * 0.30),
                "max_ues": max_ues, "pci": 0,
            }
            idx += 1

        # n28 (700 MHz) is supported-but-not-deployed: only materialise it as an extra
        # sector when an operator passes it explicitly in spectrum_bands.
        if "n28" in allowed:
            gen, freq, max_ues, _peak4g, antenna = BAND_SPEC["n28"]
            vendor = VENDOR_ORDER[idx % len(VENDOR_ORDER)]
            v = VENDORS[vendor]
            cid = f"MLS_{code}_04"
            cells[cid] = {
                "cell_id": cid, "site": code, "area": area,
                "lat": round(lat + 0.0007, 6), "lon": round(lon + 0.0007, 6),
                "generation": gen, "band": "n28", "freq_mhz": freq,
                "vendor": vendor, "hardware_model": v["hw5g"], "antenna_config": antenna,
                "peak_dl_mbps": v["peak5g"], "tx_power_w": v["power"],
                "idle_power_w": round(v["power"] * 0.30), "max_ues": max_ues, "pci": 0,
            }
            idx += 1
    return cells


def site_of(cell_id: str) -> str:
    return cell_id.split("_")[1]


def site_meta() -> dict[str, dict[str, Any]]:
    return {
        code: {"area": area, "lat": lat, "lon": lon, "profile": prof,
               "install_cost": ic, "op_cost": oc}
        for code, area, lat, lon, prof, ic, oc in CANDIDATE_SITES
    }
