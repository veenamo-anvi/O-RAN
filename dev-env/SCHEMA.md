# Data Schema — Implementation Reference (Phase A, step 1)

Two stores, two kinds of data. The **Controller** owns `topology.json` (config); **InfluxDB**
owns the time-series telemetry. They are joined at query time.

## 1. `topology.json` (config — owned by Controller)

Shape: `{ "cus": {id: CU}, "dus": {id: DU}, "cells": {id: Cell} }`

**Cell** (static config + hardware ratings — NOT live measurements):

| Field | Example | Notes |
|---|---|---|
| `cell_id` | `MLS_RWS_01` | `MLS_<SITE>_<SECTOR>` |
| `du_id` / `cu_id` | `DU-MLS-1` / `CU-MLS` | hierarchy |
| `site` / `area` | `RWS` / `Railway Station` | |
| `lat` / `lon` | 13.0121 / 77.5705 | |
| `generation` | `5G` / `4G` | |
| `band` / `freq_mhz` | `n78` / 3500 | deployed: n78, n41, B3, B40 (no n28) |
| `vendor` / `hardware_model` | `Nokia` / `AirScale MAA 64T64R` | |
| `antenna_config` | `64T64R` / `4T4R` | |
| `pci` | 1 | collision/confusion-free |
| `peak_dl_mbps` | 3800 | hardware **max** (rating) |
| `tx_power_w` / `idle_power_w` | 1000 / 300 | rated power |
| `max_ues` | 900 | capacity **ceiling** (band-based: n78=900, n41=700, B40=300, B3=250) |

**DU**: `{du_id, cu_id, area, lat, lon, cell_ids[]}` ·
**CU**: `{cu_id, area, lat, lon, du_ids[]}`

## 2. InfluxDB measurements (telemetry — owned by InfluxDB)

The 9 measurements (written by the simulators / KPI agent in later phases; the Controller
**reads** `cell_kpi` and **writes** `topology_event`):

| Measurement | Tags | Key fields |
|---|---|---|
| `cell_kpi` | cell_id, area, band, pci, du_id, cu_id, vendor, generation | connected_ues, dl/ul_throughput_mbps, rsrp_dbm, rsrq_db, sinr_db, power_w, prb_dl/ul_pct, packet_loss_pct, cqi, mcs, bler_pct, latency_ms, jitter_ms, interference_dbm |
| `du_kpi` | du_id, cu_id | active_ues, cell_count, cpu_pct, memory_pct, fronthaul_latency_us, processing_delay_ms, f1_msg_per_sec |
| `cu_kpi` | cu_id | du_count, rrc_connected, rrc_idle, rrc_setup_rate, inter_du_ho_rate, pdcp_dl/ul_gbps, f1/n2/n3/e1_latency_ms, cpu_pct, memory_pct |
| `core_kpi` | component, instance_id | AMF/SMF/UPF field sets (vary by component) |
| `ue_mobility` | ue_id, source_cell, target_cell, event_type | rsrp_source, rsrp_target, ho_duration_ms, velocity_kmh |
| `ue_usage` | ue_id, cell_id, slice_type | dl_bytes, ul_bytes, latency_ms, jitter_ms, packet_loss |
| `alerts` | severity, cell_id, du_id, alert_type | message, metric_value, threshold, ai_confidence |
| `son_actions` | cell_id, du_id, action_type | message, confidence |
| `topology_event` | event_type | cell_id/du_id, from/to component |

**Live `cell_kpi` fields the Controller surfaces** in the merged `kpi` dict (last 3 min,
`last()` per field): see `agents/controller/influx_io.py:KPI_FIELDS`. These are the
*measurements* (e.g. `prb_dl_pct`, `sinr_db`, `connected_ues`) — distinct from the config
ratings above (`max_ues`, `peak_dl_mbps`, `tx_power_w`).
