# 03.1 — Running Containers

> **Parent:** [Dev Environment](./spec.md) › [Root Spec](../spec.md)

| Container | Port | Purpose |
|---|---|---|
| `influxdb` | 8086 | Time-series KPI storage |
| `grafana` | 3000 | Dashboards (data source provisioned; dashboards manual import) |
| `core-sim` | — | AMF + SMF + UPF simulator |
| `cu-mls` | — | CU-MLS simulator (RRC / PDCP, Malleswaram) |
| `du-mls-1` | — | DU simulator — north sites: RWS, 18C, BEL, SNK (12 cells) |
| `du-mls-2` | — | DU simulator — central sites: SPG, 3MN, 10C (9 cells) |
| `du-mls-3` | — | DU simulator — south-west sites: MGR, CHD, 6CR (9 cells) |
| `controller` | 8080 | Topology control plane |
| `planning-api` | 8081 | Network planning engine |
| `kpi-agent` | — | KPI monitoring + BiLSTM anomaly detection |
| `orchestrator` | 8082 | Gemini LLM chat agent |
| `map-server` | 8083 | Leaflet.js live cell map |

**Total: 12 containers**

> **Topology source of truth**: `dev-env/config/topology.json` — mounted read-write to the
> controller, read-only to all DU/CU simulators. Controller writes atomically (`.tmp` →
> rename). Simulators poll every `TOPO_POLL_SEC` (default 5 s) and reconfigure live without
> restart.
