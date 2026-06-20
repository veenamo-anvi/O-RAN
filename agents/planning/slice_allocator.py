"""Slice allocation — split a PRB budget across eMBB / URLLC / mMTC.

PRB budget is split by the traffic_profile fractions; per-cell allocations scale by the
cell's max_ues so larger cells get proportionally more resource blocks.
"""
from __future__ import annotations

from typing import Any

DEFAULT_PROFILE = {"eMBB": 0.7, "URLLC": 0.2, "mMTC": 0.1}
# total downlink PRBs per band (numerology/bandwidth dependent, simplified)
PRB_PER_BAND = {"n78": 273, "n41": 162, "n28": 52, "B40": 100, "B3": 100}


def allocate(cells: dict[str, Any], traffic_profile: dict[str, float] | None) -> dict[str, Any]:
    prof = dict(DEFAULT_PROFILE)
    if traffic_profile:
        prof.update({k: v for k, v in traffic_profile.items() if k in DEFAULT_PROFILE})
    total = sum(prof.values()) or 1.0
    prof = {k: v / total for k, v in prof.items()}

    per_cell: dict[str, Any] = {}
    totals = {"eMBB": 0, "URLLC": 0, "mMTC": 0}
    for cid, c in cells.items():
        prbs = PRB_PER_BAND.get(c.get("band"), 100)
        alloc = {s: int(round(prbs * frac)) for s, frac in prof.items()}
        per_cell[cid] = {"total_prb": prbs, **alloc}
        for s in totals:
            totals[s] += alloc[s]
    return {"profile_fractions": prof, "per_cell": per_cell, "totals": totals}
