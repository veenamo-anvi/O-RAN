#!/usr/bin/env python3
"""Generate the 30-cell Malleswaram topology.json (source of truth).

Layout: 1 CU (CU-MLS) -> 3 DUs -> 30 cells (10 macro sites x 3 sectors).
Run:  python dev-env/gen_topology.py   ->  writes dev-env/config/topology.json

Cell naming: MLS_<SITE>_<SECTOR>  e.g. MLS_RWS_01.
Bands deployed: n78, n41, B3, B40  (n28 is NOT deployed — explicit-only at plan time).
Vendors: Nokia / Ericsson / Samsung / ZTE, round-robin per cell (~25% each).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "config", "topology.json")

# (code, area, du_id, lat, lon, profile)  — profile: "high" | "res"
# high-traffic sites: RWS, 18C, SNK, SPG, 10C ; residential: BEL, 3MN, MGR, CHD, 6CR
SITES = [
    ("RWS", "Railway Station", "DU-MLS-1", 13.01210, 77.57050, "high"),
    ("18C", "18th Cross",       "DU-MLS-1", 13.00980, 77.56880, "high"),
    ("BEL", "BEL Circle",       "DU-MLS-1", 13.01550, 77.56620, "res"),
    ("SNK", "Sankey Road",      "DU-MLS-1", 13.00750, 77.57350, "high"),
    ("SPG", "Sampige Road",     "DU-MLS-2", 13.00420, 77.57080, "high"),
    ("3MN", "3rd Main",         "DU-MLS-2", 13.00280, 77.56720, "res"),
    ("10C", "10th Cross",       "DU-MLS-2", 13.00090, 77.57190, "high"),
    ("MGR", "Margosa Road",     "DU-MLS-3", 12.99820, 77.56810, "res"),
    ("CHD", "Chowdiah",         "DU-MLS-3", 12.99680, 77.56480, "res"),
    ("6CR", "6th Cross",        "DU-MLS-3", 12.99950, 77.56620, "res"),
]

# sector band plan per site profile -> list of bands for sectors 1..3
SECTOR_PLAN = {
    "high": ["n78", "n41", "B3"],
    "res":  ["n78", "B40", "B3"],
}

# band -> (generation, freq_mhz, max_ues, peak_dl_mbps_4g)
BAND = {
    "n78": ("5G", 3500, 900, None),
    "n41": ("5G", 2500, 700, None),
    "B40": ("4G", 2300, 300, 220),
    "B3":  ("4G", 1800, 250, 150),
}

# vendor -> hardware + power specs
VENDORS = {
    "Nokia":    {"hw5g": "AirScale MAA 64T64R", "hw4g": "AWHFA",    "peak5g": 3800, "power": 1000},
    "Ericsson": {"hw5g": "AIR 6449",            "hw4g": "RBS 6402", "peak5g": 3600, "power": 950},
    "Samsung":  {"hw5g": "TM500 64T64R",        "hw4g": "RRU",      "peak5g": 3400, "power": 900},
    "ZTE":      {"hw5g": "AAU 5614",            "hw4g": "RRU",      "peak5g": 3200, "power": 1000},
}
VENDOR_ORDER = ["Nokia", "Ericsson", "Samsung", "ZTE"]


def centroid(points):
    lat = sum(p[0] for p in points) / len(points)
    lon = sum(p[1] for p in points) / len(points)
    return round(lat, 6), round(lon, 6)


def build():
    cells = {}
    pci = 1
    cell_idx = 0
    for code, area, du_id, lat, lon, profile in SITES:
        for sector, band in enumerate(SECTOR_PLAN[profile], start=1):
            gen, freq, max_ues, peak4g = BAND[band]
            vendor = VENDOR_ORDER[cell_idx % len(VENDOR_ORDER)]
            v = VENDORS[vendor]
            is5g = gen == "5G"
            cell_id = f"MLS_{code}_{sector:02d}"
            # slight per-sector coordinate jitter so co-sited sectors are distinguishable
            jitter = (sector - 2) * 0.00035
            cells[cell_id] = {
                "cell_id": cell_id,
                "du_id": du_id,
                "cu_id": "CU-MLS",
                "site": code,
                "area": area,
                "lat": round(lat + jitter, 6),
                "lon": round(lon + jitter, 6),
                "generation": gen,
                "band": band,
                "freq_mhz": freq,
                "vendor": vendor,
                "hardware_model": v["hw5g"] if is5g else v["hw4g"],
                "antenna_config": "64T64R" if is5g else "4T4R",
                "pci": pci,
                "peak_dl_mbps": v["peak5g"] if is5g else peak4g,
                "tx_power_w": v["power"] if is5g else 320,
                "idle_power_w": round((v["power"] if is5g else 320) * 0.30),
                "max_ues": max_ues,
            }
            pci += 1
            cell_idx += 1

    # group cells into DUs
    dus = {}
    for du_id in ("DU-MLS-1", "DU-MLS-2", "DU-MLS-3"):
        members = [c for c in cells.values() if c["du_id"] == du_id]
        clat, clon = centroid([(c["lat"], c["lon"]) for c in members])
        dus[du_id] = {
            "du_id": du_id,
            "cu_id": "CU-MLS",
            "area": "Malleswaram",
            "lat": clat,
            "lon": clon,
            "cell_ids": [c["cell_id"] for c in members],
        }

    clat, clon = centroid([(d["lat"], d["lon"]) for d in dus.values()])
    cus = {
        "CU-MLS": {
            "cu_id": "CU-MLS",
            "area": "Malleswaram, North Bangalore",
            "lat": clat,
            "lon": clon,
            "du_ids": list(dus.keys()),
        }
    }

    return {"cus": cus, "dus": dus, "cells": cells}


def main():
    topo = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(topo, f, indent=2)
        f.write("\n")
    # quick sanity summary
    cells = topo["cells"]
    from collections import Counter
    by_vendor = Counter(c["vendor"] for c in cells.values())
    by_band = Counter(c["band"] for c in cells.values())
    by_du = Counter(c["du_id"] for c in cells.values())
    print(f"wrote {OUT}")
    print(f"cells={len(cells)}  dus={len(topo['dus'])}  cus={len(topo['cus'])}")
    print(f"by_du={dict(by_du)}")
    print(f"by_band={dict(by_band)}")
    print(f"by_vendor={dict(by_vendor)}")
    pcis = [c["pci"] for c in cells.values()]
    print(f"pci_unique={len(set(pcis)) == len(pcis)}  pci_range={min(pcis)}-{max(pcis)}")


if __name__ == "__main__":
    main()
