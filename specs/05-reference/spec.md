# 05 — Reference

> **Parent:** [Root Spec](../spec.md)

## A. Input Parameters

Parameters accepted by the planning engine and orchestrator to deploy or reorganise a network:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `hardware_resources` | Radio hardware model + capability | `Nokia AirScale MAA 64T64R` |
| `geographic_area` | City zone or GeoJSON polygon | `"ITPL & EPIP zone, Whitefield"` |
| `expected_user_density` | Users per km² | `50000` |
| `traffic_profile` | Slice mix + peak hour | `{"eMBB":0.7,"URLLC":0.2,"mMTC":0.1,"peak_hour":19}` |
| `fiber_availability` | Fiber map or site list | `["Koramangala","Whitefield",...]` |
| `spectrum_bands` | Licensed bands | `["n78","n28","B3","B40"]` |
| `latency_constraints` | E2E and fronthaul targets | `{"e2e_ms":10,"fronthaul_us":100}` |
| `compute_resources` | Per-site server capacity | `{"cpu_cores":32,"ram_gb":64}` |
| `deployment_budget` | CAPEX/OPEX envelope (USD) | `2000000` |

Input may be partial — the system will flag missing required fields or redundant ones.

## B. Resolved Decisions

| Question | Decision |
|---|---|
| RAN hardware | Docker containers simulating RU/DU/CU (dev); Nokia, Ericsson, Samsung, ZTE equipment specs (25% each); real O-RAN targets (prod) |
| KPI data source | Synthetic telemetry from DU/CU/Core simulators using real hardware specs (peak_dl_mbps, tx_power_w, band-specific SINR/RSRP) → InfluxDB |
| Geographic area | Malleswaram, North Bangalore — 30 cells across 10 macro sites; 40% operator share; active_ues_peak = 18,400 (40,000 residents + 15% commuter overhead × 40% market share) |
| LLM backend | Four backends, resolved by priority: Claude CLI (primary, Docker) → Anthropic API (dev opt-in) → Gemini (fallback) → Mock (no-creds dev/test). All share the same **14-tool** schema in Anthropic format. |
| RAN mode | 4G/5G NSA — LTE anchor + 5G NR secondary; shared AMF/SMF/UPF core |
| 5G architecture | Split CU/DU/RU throughout (planning engine groups DUs under CUs by proximity) |
| 4G architecture | 4G cell connected to 5G L2/L3 |
| Deployment target | Docker Compose (dev), Kubernetes Helm (prod) |
| SMO | Controller REST API (dev), O-RAN-compliant SMO (prod) |
| Live map | Leaflet.js map container (port 8083) showing all cells, vendor colours, live KPI status |

## C. API Quick Reference

**Controller (:8080)** — see [Controller](../02-agents/controller.md)

```
GET  /health | /topology | /network | /cells | /cells/{id} | /dus | /cus
GET  /neighbors/{cell_id}?max_neighbors=6
GET  /congestion                         ranked per-cell congestion scores
POST /move/cell     {"cell_id", "to_du_id"}
POST /move/du       {"du_id", "to_cu_id"}
POST /son/pci-reopt {"cell_id", "du_id"}  PCI re-optimisation (SINR_LOW SON loop)
POST /topology/replace  {"cus":{}, "dus":{}, "cells":{}}
POST /cells/add     {cell_id, du_id, area, lat, lon, generation, band, vendor, ...}
DELETE /cells/{cell_id}
```

**Planning API (:8081)** — see [Planning Engine](../02-agents/planning-engine.md)

```
GET  /health | /candidates | /demand-clusters | /plan/{id}
POST /plan           {geographic_area, expected_user_density, traffic_profile,
                      spectrum_bands, deployment_budget, use_mip, sinr_min_db}
POST /plan/multi-period  {demand_mode, spectrum_bands, deployment_budget, sinr_min_db}
POST /plan/apply     {"plan_id": "..."}
```

**Orchestrator (:8082)** — see [Orchestrator](../02-agents/orchestrator.md)

```
POST /chat           {"message", "session_id"}  → text/plain (streaming)
GET  /history?session_id=
DELETE /history?session_id=
GET  /tools          → [{"name", "description"}]  (14 tools)
GET  /health         → {"status": "ok", "model": "<name>",
                        "backend": "claude-cli"|"anthropic-api"|"gemini"|"mock"}
```

**Map Server (:8083)** — see [Map Server](../02-agents/map-server.md)

```
GET  /               Leaflet.js HTML map page
GET  /api/cells      Cell list + coverage radii + live KPIs
POST /api/chat       Proxy → Orchestrator /chat (120 s timeout)
GET  /api/history    Proxy → Orchestrator /history
DELETE /api/history  Proxy → Orchestrator /history
GET  /api/tools      Proxy → Orchestrator /tools
GET  /api/orch-health  Proxy → Orchestrator /health
GET  /health
```
