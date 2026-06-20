"""MIP-based optimal placement (Almoghathawi et al., 2024) via CBC/pulp.

Minimise  sum_j sum_t ( c_jt*z_jt + r_jt*y_jt )
  z_jt = build site j in period t (one-time CAPEX)
  y_jt = site j active in period t (per-period OPEX)
subject to single-build, coverage, activation, unique-assignment, implies-active,
capacity (<= delta_j), and SINR QoS (>= sinr_min, via Walfisch-Ikegami feasibility).

Falls back to the heuristic on infeasibility / solver timeout.
"""
from __future__ import annotations

import logging
from typing import Any

import candidates as C
import demand as D
from geo import haversine_m, predicted_sinr_db

log = logging.getLogger("planning.mip")

# per-site UE/channel capacity (delta_j) — sum of its sector max_ues, approximated
SITE_CAPACITY = 1900


def _feasible(site_meta: dict[str, Any], cl: dict[str, Any], sinr_min: float) -> bool:
    d = haversine_m(site_meta["lat"], site_meta["lon"], cl["lat"], cl["lon"])
    # n78 (3500 MHz) as the limiting deployed carrier for QoS feasibility
    return predicted_sinr_db(d, 3500.0) >= sinr_min and d <= 1500.0


def solve(
    bands: list[str],
    deployment_budget: float | None,
    period_clusters: list[list[str]],
    sinr_min_db: float = 10.0,
    time_limit_sec: int = 120,
) -> dict[str, Any] | None:
    """Return {selected_sites, build_schedule, period_assignments, cost} or None on failure."""
    try:
        import pulp
    except Exception as exc:  # noqa: BLE001
        log.warning("pulp unavailable (%s) — MIP disabled", exc)
        return None

    meta = C.site_meta()
    sites = list(meta)
    cmap = D.cluster_map()
    periods = list(range(len(period_clusters)))

    prob = pulp.LpProblem("bs_placement", pulp.LpMinimize)
    z = {(j, t): pulp.LpVariable(f"z_{j}_{t}", cat="Binary") for j in sites for t in periods}
    y = {(j, t): pulp.LpVariable(f"y_{j}_{t}", cat="Binary") for j in sites for t in periods}
    x = {}  # assignment demand i -> site j in period t (only feasible pairs)
    for t in periods:
        for cid in period_clusters[t]:
            for j in sites:
                if _feasible(meta[j], cmap[cid], sinr_min_db):
                    x[(cid, j, t)] = pulp.LpVariable(f"x_{cid}_{j}_{t}", cat="Binary")

    # objective: CAPEX (build) + OPEX (active)
    prob += pulp.lpSum(meta[j]["install_cost"] * z[(j, t)] for j in sites for t in periods) + \
        pulp.lpSum(meta[j]["op_cost"] * y[(j, t)] for j in sites for t in periods)

    for j in sites:
        # (2) single-build across all periods
        prob += pulp.lpSum(z[(j, t)] for t in periods) <= 1
        for t in periods:
            # (4) activation: active only if built in this or an earlier period
            prob += y[(j, t)] <= pulp.lpSum(z[(j, s)] for s in periods if s <= t)

    for t in periods:
        for cid in period_clusters[t]:
            feas = [j for j in sites if (cid, j, t) in x]
            if not feas:
                log.warning("cluster %s has no feasible site in period %d", cid, t)
                return None
            # (3)+(5) coverage + unique assignment
            prob += pulp.lpSum(x[(cid, j, t)] for j in feas) == 1
            for j in feas:
                # (6) implies-active
                prob += x[(cid, j, t)] <= y[(j, t)]
        for j in sites:
            # (7) capacity
            served = [cid for cid in period_clusters[t] if (cid, j, t) in x]
            if served:
                prob += pulp.lpSum(cmap[cid]["rho"] * x[(cid, j, t)] for cid in served) <= SITE_CAPACITY

    if deployment_budget is not None:
        prob += pulp.lpSum(meta[j]["install_cost"] * z[(j, t)] for j in sites for t in periods) <= deployment_budget

    status = prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit_sec))
    if pulp.LpStatus[status] not in ("Optimal", "Not Solved", "Integer Feasible"):
        log.warning("MIP status=%s — falling back", pulp.LpStatus[status])
        return None

    selected = sorted({j for (j, t) in z if z[(j, t)].value() and z[(j, t)].value() > 0.5})
    if not selected:
        return None
    build_schedule = [{"site": j, "period": t} for (j, t) in z if z[(j, t)].value() and z[(j, t)].value() > 0.5]
    period_assignments = {
        t: {cid: j for cid in period_clusters[t] for j in sites if (cid, j, t) in x and x[(cid, j, t)].value() and x[(cid, j, t)].value() > 0.5}
        for t in periods
    }
    cost = pulp.value(prob.objective)
    return {
        "selected_sites": selected,
        "build_schedule": sorted(build_schedule, key=lambda b: (b["period"], b["site"])),
        "period_assignments": period_assignments,
        "cost": round(cost, 2) if cost else 0.0,
        "status": pulp.LpStatus[status],
    }
