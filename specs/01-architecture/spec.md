# 01 — System Architecture

> **Parent:** [Root Spec](../spec.md)
> **Children:** [Network Topology](./network-topology.md) · [Vendor Distribution](./vendor-distribution.md)

```
┌──────────────────────────────────────────────────────────────┐
│               Orchestrator Agent  :8082                      │
│       LLM backend (Gemini / Claude CLI)  +  tool-calling     │
└────────┬───────────────┬───────────────┬─────────────────────┘
         │               │               │
  ┌──────▼──────┐  ┌─────▼──────┐  ┌────▼──────────┐
  │ Planning    │  │ Controller │  │  KPI Agent    │
  │ Agent :8081 │  │ Agent :8080│  │  (background) │
  │ /plan       │  │ /network   │  │  BiLSTM model │
  │ /plan/apply │  │ /move/cell │  │  + alerting   │
  └──────┬──────┘  └─────┬──────┘  └────┬──────────┘
         │               │              │
  ┌──────▼───────────────▼──────────────▼──────────┐
  │                 InfluxDB  :8086                 │
  │  cell_kpi | du_kpi | cu_kpi | core_kpi         │
  │  ue_mobility | ue_usage | alerts | son_actions  │
  └──────────────────────┬─────────────────────────┘
                         │  topology.json
           ┌─────────────┼───────────────────┐
     ┌─────▼──────┐ ┌────▼──────┐ ┌──────────▼────┐
     │  3× DU sims│ │ 1× CU sim │ │  Core sim     │
     │ (4G+5G RAN)│ │(RRC/PDCP) │ │  AMF/SMF/UPF  │
     └────────────┘ └───────────┘ └───────────────┘
                         │
                  ┌──────▼──────┐
                  │ Map Server  │
                  │   :8083     │
                  │ Leaflet.js  │
                  └─────────────┘
```

The architecture is detailed across two child specs:

- **[Network Topology](./network-topology.md)** — the Malleswaram population model, CU/DU/cell
  layout, sector mix, and band plan (incl. `n28`).
- **[Vendor Distribution](./vendor-distribution.md)** — per-vendor 4G/5G hardware models, max
  UEs, peak DL, and system power.

See also the runtime view in [03 — Dev Environment](../03-dev-environment/spec.md).
