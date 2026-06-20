# 03 — Dev Environment

> **Parent:** [Root Spec](../spec.md)
> **Children:** [Containers](./containers.md) · [InfluxDB Measurements](./influxdb-measurements.md) ·
> [Grafana Dashboards](./grafana-dashboards.md)

The development environment runs as a Docker Compose stack. Detail is split across three child
specs:

- **[Containers](./containers.md)** — the 12 running containers, ports, and the topology
  source-of-truth mount.
- **[InfluxDB Measurements](./influxdb-measurements.md)** — the 9 time-series measurement
  schemas (tags + key fields).
- **[Grafana Dashboards](./grafana-dashboards.md)** — the 5 provisioned dashboards.

> **Topology source of truth**: `dev-env/config/topology.json` — mounted read-write to the
> controller, read-only to all DU/CU simulators. Controller writes atomically (`.tmp` →
> rename). Simulators poll every `TOPO_POLL_SEC` (default 5 s) and reconfigure live without
> restart.
