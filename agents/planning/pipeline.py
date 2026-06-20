"""generate_plan() — the 10-step planning pipeline.

1 select_cells  2 assign_pcis  3 assign_dus  4 assign_cus  5 centroids  6 timing_sync
7 allocate_slices  8 fronthaul_routing  9 plan_to_topology  10 store in _plans (UUID).
"""
from __future__ import annotations

import math
import uuid
from typing import Any

import candidates as C
import demand as D
import mip_placer
import pci_planner
import placement
import slice_allocator
from geo import haversine_m

MAX_CELLS_PER_DU = 12
MAX_DUS_PER_CU = 4
LIGHT_SPEED_FIBER_MPS = 2.0e8  # ~0.67c in fibre

_PLANS: dict[str, dict[str, Any]] = {}


def _centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    return (round(sum(p[0] for p in points) / len(points), 6),
            round(sum(p[1] for p in points) / len(points), 6))


def _greedy_group(items: list[str], coords: dict[str, tuple[float, float]], max_size: int, prefix: str) -> dict[str, list[str]]:
    """Group items into proximity buckets of at most max_size (greedy nearest-neighbour)."""
    remaining = list(items)
    groups: dict[str, list[str]] = {}
    gi = 1
    while remaining:
        seed = remaining.pop(0)
        group = [seed]
        remaining.sort(key=lambda x: haversine_m(*coords[seed], *coords[x]))
        while remaining and len(group) < max_size:
            group.append(remaining.pop(0))
        groups[f"{prefix}{gi}"] = group
        gi += 1
    return groups


def assign_dus(cells: dict[str, Any]) -> dict[str, Any]:
    coords = {cid: (c["lat"], c["lon"]) for cid, c in cells.items()}
    groups = _greedy_group(list(cells), coords, MAX_CELLS_PER_DU, "DU-MLS-")
    dus = {}
    for du_id, cids in groups.items():
        for cid in cids:
            cells[cid]["du_id"] = du_id
        lat, lon = _centroid([coords[c] for c in cids])
        dus[du_id] = {"du_id": du_id, "cu_id": None, "area": "Malleswaram",
                      "lat": lat, "lon": lon, "cell_ids": cids}
    return dus


def assign_cus(dus: dict[str, Any]) -> dict[str, Any]:
    coords = {did: (d["lat"], d["lon"]) for did, d in dus.items()}
    groups = _greedy_group(list(dus), coords, MAX_DUS_PER_CU, "CU-MLS")
    cus = {}
    # single CU expected for Malleswaram; name first group CU-MLS
    for i, (cu_id, dids) in enumerate(groups.items()):
        name = "CU-MLS" if i == 0 else cu_id
        for did in dids:
            dus[did]["cu_id"] = name
        lat, lon = _centroid([coords[d] for d in dids])
        cus[name] = {"cu_id": name, "area": "Malleswaram, North Bangalore",
                     "lat": lat, "lon": lon, "du_ids": dids}
    return cus


def timing_sync(dus: dict[str, Any], cus: dict[str, Any]) -> dict[str, Any]:
    """Estimate fronthaul propagation delay per DU->CU link."""
    out = {}
    for did, d in dus.items():
        cu = cus.get(d["cu_id"])
        if not cu:
            continue
        dist = haversine_m(d["lat"], d["lon"], cu["lat"], cu["lon"])
        prop_us = dist / LIGHT_SPEED_FIBER_MPS * 1e6
        out[did] = {"cu_id": d["cu_id"], "distance_m": round(dist, 1),
                    "propagation_us": round(prop_us, 2),
                    "in_budget": prop_us <= 100.0}
    return out


def fronthaul_routing(dus: dict[str, Any], cus: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for did, d in dus.items():
        cu = cus.get(d["cu_id"])
        if not cu:
            continue
        dist = haversine_m(d["lat"], d["lon"], cu["lat"], cu["lon"])
        latency_ms = dist / LIGHT_SPEED_FIBER_MPS * 1e3 + 0.05
        out[did] = {"cu_id": d["cu_id"], "midhaul_distance_m": round(dist, 1),
                    "est_latency_ms": round(latency_ms, 3)}
    return out


def cost_estimate(site_codes: list[str]) -> dict[str, Any]:
    meta = C.site_meta()
    install = [{"site": s, "cost": meta[s]["install_cost"]} for s in site_codes]
    op = [{"site": s, "cost": meta[s]["op_cost"]} for s in site_codes]
    total = sum(i["cost"] for i in install) + sum(o["cost"] for o in op)
    return {"total": total, "install_costs": install, "op_costs": op}


def plan_to_topology(cells: dict[str, Any], dus: dict[str, Any], cus: dict[str, Any]) -> dict[str, Any]:
    """Convert to topology.json format, preserving all hardware fields."""
    out_cells = {}
    for cid, c in cells.items():
        out_cells[cid] = {
            "cell_id": cid, "du_id": c["du_id"], "cu_id": dus[c["du_id"]]["cu_id"],
            "site": c["site"], "area": c["area"], "lat": c["lat"], "lon": c["lon"],
            "generation": c["generation"], "band": c["band"], "freq_mhz": c["freq_mhz"],
            "vendor": c["vendor"], "hardware_model": c["hardware_model"],
            "antenna_config": c["antenna_config"], "pci": c["pci"],
            "peak_dl_mbps": c["peak_dl_mbps"], "tx_power_w": c["tx_power_w"],
            "idle_power_w": c["idle_power_w"], "max_ues": c["max_ues"],
        }
    return {"cus": cus, "dus": dus, "cells": out_cells}


def generate_plan(params: dict[str, Any]) -> dict[str, Any]:
    bands = params.get("spectrum_bands") or list(C.DEFAULT_BANDS)
    use_mip = bool(params.get("use_mip", False))
    sinr_min = float(params.get("sinr_min_db", 10.0))
    time_limit = int(params.get("mip_time_limit_sec", 120))
    budget = params.get("deployment_budget")

    mip_used = False
    mip_result = None
    if use_mip:
        single_period = [[c["id"] for c in D.clusters()]]
        mip_result = mip_placer.solve(bands, budget, single_period, sinr_min, time_limit)
        if mip_result:
            mip_used = True
            all_cells = C.build_candidate_cells(bands)
            cells = {cid: c for cid, c in all_cells.items() if C.site_of(cid) in mip_result["selected_sites"]}
            site_codes = mip_result["selected_sites"]
        else:
            cells, site_codes = placement.select_cells(bands, budget)
    else:
        cells, site_codes = placement.select_cells(bands, budget)

    pci_planner.assign_pcis(cells)                       # step 2
    dus = assign_dus(cells)                              # step 3
    cus = assign_cus(dus)                                # step 4
    # step 5 centroids already computed in assign_dus/assign_cus
    timing = timing_sync(dus, cus)                       # step 6
    slices = slice_allocator.allocate(cells, params.get("traffic_profile"))  # step 7
    fronthaul = fronthaul_routing(dus, cus)              # step 8
    topo = plan_to_topology(cells, dus, cus)             # step 9

    plan_id = str(uuid.uuid4())
    plan = {
        "plan_id": plan_id,
        "cells": list(topo["cells"].values()),
        "dus": topo["dus"], "cus": topo["cus"],
        "slice_allocations": slices,
        "timing_sync": timing,
        "fronthaul_routing": fronthaul,
        "cost_estimate": cost_estimate(site_codes),
        "pci_check": pci_planner.verify(cells),
        "mip_used": mip_used,
        "selected_cell_count": len(cells),
        "spectrum_bands": bands,
        "_topology": topo,
    }
    if mip_result:
        plan["mip_status"] = mip_result.get("status")
    _PLANS[plan_id] = plan                               # step 10
    return plan


def generate_multi_period(params: dict[str, Any]) -> dict[str, Any]:
    bands = params.get("spectrum_bands") or list(C.DEFAULT_BANDS)
    mode = params.get("demand_mode", "permanent")
    sinr_min = float(params.get("sinr_min_db", 10.0))
    time_limit = int(params.get("mip_time_limit_sec", 120))
    budget = params.get("deployment_budget")
    period_clusters = D.period_profiles(mode, params.get("time_periods"))

    result = mip_placer.solve(bands, budget, period_clusters, sinr_min, time_limit)
    if result is None:
        # fallback: union of all clusters via heuristic
        union = {cid for plist in period_clusters for cid in plist}
        clusters = [c for c in D.clusters() if c["id"] in union]
        cells, site_codes = placement.select_cells(bands, budget, clusters)
        mip_used = False
        build_schedule = [{"site": s, "period": 0} for s in site_codes]
        period_assignments = {}
    else:
        mip_used = True
        site_codes = result["selected_sites"]
        all_cells = C.build_candidate_cells(bands)
        cells = {cid: c for cid, c in all_cells.items() if C.site_of(cid) in site_codes}
        build_schedule = result["build_schedule"]
        period_assignments = result["period_assignments"]

    pci_planner.assign_pcis(cells)
    dus = assign_dus(cells)
    cus = assign_cus(dus)
    timing = timing_sync(dus, cus)
    slices = slice_allocator.allocate(cells, params.get("traffic_profile"))
    fronthaul = fronthaul_routing(dus, cus)
    topo = plan_to_topology(cells, dus, cus)

    plan_id = str(uuid.uuid4())
    plan = {
        "plan_id": plan_id, "demand_mode": mode,
        "cells": list(topo["cells"].values()), "dus": topo["dus"], "cus": topo["cus"],
        "slice_allocations": slices, "timing_sync": timing, "fronthaul_routing": fronthaul,
        "cost_estimate": cost_estimate(site_codes), "pci_check": pci_planner.verify(cells),
        "mip_used": mip_used, "selected_cell_count": len(cells),
        "build_schedule": build_schedule, "period_assignments": period_assignments,
        "spectrum_bands": bands, "_topology": topo,
    }
    _PLANS[plan_id] = plan
    return plan


def get_plan(plan_id: str) -> dict[str, Any] | None:
    return _PLANS.get(plan_id)
