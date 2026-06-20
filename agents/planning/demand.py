"""Demand node concept (Tutschku 1998).

Traffic is represented as a finite set of demand clusters, separate from candidate sites.
Each cluster has a channel requirement (rho). Multi-period profiles drive Case A (expanding)
and Case B (shifting) scenarios.
"""
from __future__ import annotations

from typing import Any

# 10 Bangalore/Malleswaram demand clusters: (id, area, lat, lon, rho channels)
DEMAND_CLUSTERS = [
    ("D-RWS", "Railway Station",  13.01230, 77.57040, 520),
    ("D-MKT", "Malleswaram Market",13.00350, 77.57020, 480),
    ("D-18C", "18th Cross",       13.00990, 77.56890, 360),
    ("D-SNK", "Sankey Tank",      13.00770, 77.57340, 300),
    ("D-SPG", "Sampige Road",     13.00430, 77.57090, 410),
    ("D-MGR", "Margosa Road",     12.99830, 77.56820, 260),
    ("D-CHD", "Chowdiah",         12.99690, 77.56490, 230),
    ("D-BEL", "BEL Circle",       13.01540, 77.56630, 250),
    ("D-MEK", "Malleswaram East", 13.00640, 77.57590, 340),
    ("D-SDP", "Sadashivanagar",   12.99560, 77.57040, 210),
]

# preset multi-period profiles (subset/weights of cluster ids per period)
PERIOD_PROFILES = {
    "permanent": [  # Case A — expanding: each period ADDS clusters
        ["D-RWS", "D-MKT", "D-18C", "D-SPG"],
        ["D-RWS", "D-MKT", "D-18C", "D-SPG", "D-SNK", "D-BEL"],
        ["D-RWS", "D-MKT", "D-18C", "D-SPG", "D-SNK", "D-BEL", "D-MGR", "D-CHD", "D-MEK", "D-SDP"],
    ],
    "temporary": [  # Case B — shifting: diurnal residential -> business -> commute
        ["D-MGR", "D-CHD", "D-BEL", "D-SDP"],          # residential morning
        ["D-RWS", "D-MKT", "D-MEK", "D-SPG"],          # business hours
        ["D-RWS", "D-SNK", "D-18C", "D-MKT"],          # evening commute
    ],
}


def clusters() -> list[dict[str, Any]]:
    return [{"id": cid, "area": area, "lat": lat, "lon": lon, "rho": rho}
            for cid, area, lat, lon, rho in DEMAND_CLUSTERS]


def cluster_map() -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in clusters()}


def period_profiles(mode: str, time_periods: list[list[str]] | None = None) -> list[list[str]]:
    if time_periods:
        return time_periods
    return PERIOD_PROFILES.get(mode, PERIOD_PROFILES["permanent"])
