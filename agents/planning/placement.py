"""Heuristic cell placement — density-weighted Haversine candidate scoring.

Greedily selects candidate SITES that best cover the demand clusters (weighted by channel
requirement rho and inverse distance) until demand is covered or the budget is exhausted.
Selected sites expand into their sector-cells.
"""
from __future__ import annotations

from typing import Any

import candidates as C
import demand as D
from geo import haversine_m


def _site_score(site_code: str, meta: dict[str, Any], clusters: list[dict[str, Any]]) -> float:
    s = 0.0
    for cl in clusters:
        d = haversine_m(meta["lat"], meta["lon"], cl["lat"], cl["lon"])
        s += cl["rho"] / (1.0 + d / 300.0)
    return s


def select_cells(
    bands: list[str],
    deployment_budget: float | None,
    clusters: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Return (selected_cells, selected_site_codes)."""
    clusters = clusters or D.clusters()
    meta = C.site_meta()
    all_cells = C.build_candidate_cells(bands)

    ranked = sorted(meta, key=lambda code: _site_score(code, meta[code], clusters), reverse=True)

    selected: list[str] = []
    spent = 0.0
    uncovered = {cl["id"] for cl in clusters}
    cluster_by_id = {cl["id"]: cl for cl in clusters}

    for code in ranked:
        if not uncovered and len(selected) >= 1:
            break
        cost = meta[code]["install_cost"]
        if deployment_budget is not None and spent + cost > deployment_budget and selected:
            continue
        selected.append(code)
        spent += cost
        # mark clusters within ~600 m of this site covered
        for cid in list(uncovered):
            cl = cluster_by_id[cid]
            if haversine_m(meta[code]["lat"], meta[code]["lon"], cl["lat"], cl["lon"]) <= 600:
                uncovered.discard(cid)

    cells = {cid: c for cid, c in all_cells.items() if C.site_of(cid) in selected}
    return cells, selected
