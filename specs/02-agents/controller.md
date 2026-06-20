# 02.3 — Agent 2: Controller (`agents/controller/`)

> **Parent:** [Agent Architecture](./spec.md) › [Root Spec](../spec.md)

FastAPI service on port 8080. The single control plane for the live network — all topology
mutations go through the Controller. No other service writes to `topology.json`.

## Internal flow

```
POST /move/cell  {"cell_id": "MLS_RWS_01", "to_du_id": "DU-MLS-2"}
      │
      ├─► load topology.json
      ├─► validate cell_id and to_du_id exist
      ├─► update cell["du_id"] in-memory
      ├─► write topology.json atomically (.tmp → rename)
      ├─► write topology_event to InfluxDB
      └─► return {"status": "ok", "cell_id": ..., "from_du": ..., "to_du": ...}

DU/CU simulators poll topology.json every TOPO_POLL_SEC (5 s) → reconfigure live.
```

## KPI merging

`GET /network` and `GET /cells` merge live KPI data from InfluxDB into each cell record. The
Controller queries `cell_kpi` (last 3 min) via Flux and joins on `cell_id`. The response shape
for each cell includes both config fields (`vendor`, `band`, `du_id`, etc.) and a nested `kpi`
dict (`connected_ues`, `prb_dl_pct`, `sinr_db`, `power_w`, `dl_throughput_mbps`, etc.).

`GET /cells/{cell_id}` returns the cell config plus a 30-minute time series: one record per
InfluxDB data point, sorted ascending by time.

## PCI auto-assignment

`POST /cells/add` automatically assigns a PCI if the request body sends `pci: 0`. It finds the
smallest PCI value (starting from 1) not already used by any existing cell. The cell is
inserted into `topology.json` and the DU simulator picks it up within `TOPO_POLL_SEC`.

## Congestion scoring

`GET /congestion` returns every cell ranked by a composite congestion score derived from live
KPIs (last 3 min), so the orchestrator's `optimize_congestion` tool can surface the worst
cells:

```
score = 0.40·(PRB_dl/100) + 0.20·(1 − SINR/25) + 0.20·(BLER/20) + 0.20·(latency/150)
        (each term clamped to [0,1])
level = CRITICAL > 0.75 · HIGH > 0.55 · MODERATE > 0.35 · LOW ≤ 0.35
```

Response: `{cells:[{cell_id, area, du_id, band, congestion_score, level, prb_dl_pct, sinr_db,
bler_pct, latency_ms, connected_ues}], summary:{CRITICAL,HIGH,MODERATE,LOW}, total_cells}`,
sorted by `congestion_score` descending. Read-only — it recommends; it does not move cells.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `INFLUX_URL` | `http://influxdb:8086` | KPI merging on /network and /cells |
| `INFLUX_TOKEN` | `telecom-super-secret-auth-token-2026` | InfluxDB auth |
| `INFLUX_ORG` | `telecom` | InfluxDB org |
| `INFLUX_BUCKET` | `telecom_metrics` | KPI bucket |
| `TOPOLOGY_FILE` | `/config/topology.json` | Path to topology source of truth |

## Routes

```
GET  /health
GET  /topology                          raw topology.json (no KPI merge)
GET  /network                           full state: all cells + DUs + CUs with live KPIs
GET  /cells?area=&du_id=&cu_id=         filtered cell list with live KPIs
GET  /cells/{cell_id}                   cell config + 30-min KPI time series
GET  /dus                               DU list with live KPIs
GET  /cus                               CU list with live KPIs
GET  /neighbors/{cell_id}?max_neighbors=6  Haversine geographic neighbour list
GET  /congestion                        per-cell congestion score + severity ranking

POST /move/cell   {"cell_id": "...", "to_du_id": "..."}
POST /move/du     {"du_id": "...", "to_cu_id": "..."}
POST /son/pci-reopt  {"cell_id": "...", "du_id": "..."}
     └── re-assigns PCI for the cell (and its Haversine neighbours) collision/confusion-free;
         writes a topology_event; closes the SINR_LOW SON loop.
POST /topology/replace  {"cus": {...}, "dus": {...}, "cells": {...}}
     └── full topology swap; used by plan/apply; validates structure before writing

POST /cells/add   {cell_id, du_id, area, lat, lon, generation, band, vendor,
                   freq_mhz, pci, hardware_model, antenna_config, peak_dl_mbps,
                   tx_power_w, idle_power_w, max_ues}
     └── pci=0 → auto-assigned; DU picks up within TOPO_POLL_SEC

DELETE /cells/{cell_id}
     └── removes cell from topology.json; DU deregisters within TOPO_POLL_SEC
```

## Design decisions

- **File, not DB**: runtime topology lives in `topology.json`. Atomic writes (`.tmp` → rename)
  prevent partial reads by simulator pollers.
- **LLM never writes directly**: Gemini calls typed tools; tools call the Controller or
  Planning API over HTTP. The Controller is the only writer.
- **InfluxDB for time-series only**: topology is the Controller's domain; KPIs are InfluxDB's
  domain. The Controller merges them at query time.
