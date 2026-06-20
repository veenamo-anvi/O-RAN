# 02.4 — Agent 3: Planning Engine (`agents/planning/`)

> **Parent:** [Agent Architecture](./spec.md) › [Root Spec](../spec.md)

FastAPI service on port 8081. Generates complete network plans from high-level deployment
parameters using a 10-step pipeline. Plans are stored in-memory until applied.

## Planning pipeline (`generate_plan()`)

```
1. select_cells (placement.py)
   └── heuristic: density-weighted Haversine candidate scoring
       OR MIP-optimal (mip_placer.py) if use_mip=true

2. assign_pcis (pci_planner.py)
   └── graph-coloring: assigns PCIs collision-free and confusion-free
       (no two adjacent cells share a PCI; no three-cell PCI confusion)

3. assign_dus
   └── geographic proximity grouping (Haversine); max cells/DU respected

4. assign_cus
   └── geographic proximity grouping; max DUs/CU respected

5. compute centroids
   └── per-DU and per-CU weighted geographic centroids for routing

6. timing_sync
   └── estimates fronthaul propagation delay per DU→CU link

7. allocate_slices (slice_allocator.py)
   └── PRB budget split: eMBB / URLLC / mMTC per traffic_profile fractions

8. fronthaul_routing
   └── distance-based latency estimate for each DU→CU midhaul link

9. plan_to_topology()
   └── converts plan to topology.json format; preserves all hardware fields:
       vendor, hardware_model, generation, antenna_config, tx_power_w,
       idle_power_w, peak_dl_mbps, freq_mhz, pci

10. store in _plans dict keyed by plan_id (UUID)
```

## Propagation models

| Model | Used by | Environment | Notes |
|---|---|---|---|
| COST-231-Hata | DU/CU simulators, Map Server | Urban macro, empirical | Coverage radius, KPI simulation |
| COST-231-Walfisch-Ikegami | MIP placer | Urban NLOS | Path loss for link-budget feasibility and SINR constraints |

## MIP-based placement (Almoghathawi et al., 2024)

Reference: Almoghathawi Y., Bin Obaid H., Selim S. — *"Optimal location of base stations for
cellular mobile network considering changes in users locations"*, Journal of Engineering
Research 13 (2025) 561–567. DOI: 10.1016/j.jer.2024.04.020

**Formulation** — Mixed integer programming minimising total network cost:

```
Minimise  Σ_j Σ_t ( c_jt·z_jt  +  r_jt·y_jt )
```

where `z_jt` = build BS at site j in period t (one-time CAPEX), `y_jt` = BS active in period t
(per-period OPEX).

Subject to:
- **(2) Single-build**: each candidate site built at most once across all periods
- **(3) Coverage**: every demand cluster served by a BS built in this or an earlier period
- **(4) Activation**: BS can operate only after it has been built
- **(5) Unique assignment**: each demand cluster assigned to exactly one BS per period
- **(6) Implies-active**: assigning demand to a site forces that site active
- **(7) Capacity**: channel demand at each BS ≤ δ_j (max UE capacity)
- **(8) SINR QoS**: received SINR at each demand cluster ≥ SINR_min; constraint linearised as:
  `α(i,t)·(1 + SINR_lin) ≥ SINR_lin·P_noise + SINR_lin·β(i,t)`

**Demand node concept** (Tutschku 1998): traffic in each area is represented as a finite set
of *demand clusters* D. Each cluster has a channel requirement ρ_i. Demand clusters are
separate from candidate sites S; 10 pre-defined Bangalore clusters, one per area.

**Multi-period modes**:
- **Case A — permanent/expanding**: each period adds new demand clusters (phased network
  rollout). BSs built in period 1 can serve demand in periods 2 and 3, avoiding redundant
  infrastructure spend.
- **Case B — temporary/shifting**: demand clusters shift between periods (diurnal patterns:
  residential peak → IT-hub business hours → evening commute). The solver minimises total cost
  across all scenarios.

**Cost model**:
- `install_cost` (c_jt): one-time CAPEX; incurred once when the site is built
- `op_cost` (r_jt): per-period OPEX; incurred every period the site is active

**Solver**: CBC (via `pulp`), open-source MIP solver. Falls back to heuristic placement on
timeout or infeasibility.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `CONTROLLER_URL` | `http://controller:8080` | `plan/apply` posts topology to Controller |

`mip_time_limit_sec` (default 120 s) is a **request field** on `POST /plan` and
`POST /plan/multi-period`, not a container env var.

## Routes

```
GET  /health
GET  /candidates               list all candidate cell sites with lat/lon and area
GET  /demand-clusters          list Bangalore demand clusters + preset period profiles

POST /plan
     Body: {geographic_area, expected_user_density, traffic_profile,
            spectrum_bands=["n78","n41","B3","B40"],   # deployed bands; n28 only if explicit
            latency_constraints, compute_resources,
            deployment_budget, use_mip=false, sinr_min_db=10.0,
            mip_time_limit_sec=120}
     Returns: {plan_id, cells[], dus{}, cus{}, slice_allocations{},
               timing_sync{}, cost_estimate{total, install_costs[], op_costs[]},
               mip_used, selected_cell_count}

POST /plan/multi-period
     Body: {demand_mode ("permanent"|"temporary"), time_periods[],
            spectrum_bands, deployment_budget,
            sinr_min_db=10.0, mip_time_limit_sec=120}
     Returns: same as /plan + {build_schedule[], period_assignments{}}

GET  /plan/{plan_id}           retrieve stored plan by ID

POST /plan/apply
     Body: {plan_id}
     Action: calls POST /topology/replace on Controller with plan topology
     Returns: Controller's topology/replace response
```
