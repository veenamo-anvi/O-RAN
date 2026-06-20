# 03.3 — Grafana Dashboards

> **Parent:** [Dev Environment](./spec.md) › [Root Spec](../spec.md)

Five dashboards provisioned via `grafana/provisioning/dashboards/default.yaml`:

| Dashboard | File | Content |
|---|---|---|
| Network Overview | `network_overview.json` | Total UEs, active cells, avg DL/SINR, overloaded cells, total power; UE/PRB/SINR/power timeseries |
| Cell KPI | `cell_kpi.json` | Per-cell PRB, SINR, RSRP, throughput, power, CQI, BLER+latency; `${generation}` template variable filter |
| UE Analytics | `ue_analytics.json` | UE slice distribution (donut), latency/jitter/bytes by slice, HO event rate and duration |
| SON Alerts | `son_alerts.json` | CRITICAL/WARNING counts, SON action counts by type (LOAD_BALANCE, TRAFFIC_STEER, PCI_REOPT_REQUEST, DTX_RECOMMEND), AI confidence timeseries, SON action log |
| DU/CU Performance | `du_cu_performance.json` | DU CPU/memory/fronthaul latency/F1 msg rate, CU PDCP throughput, core registered UEs, UPF throughput |
