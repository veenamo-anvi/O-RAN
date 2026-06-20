# 02.6 — Agent 5: Map Server (`agents/map_server/`)

> **Parent:** [Agent Architecture](./spec.md) › [Root Spec](../spec.md)

FastAPI service on port 8083. Serves a live Leaflet.js cell map and proxies all
chat/history/tools traffic to the Orchestrator.

## Internal flow

```
GET /api/cells
  ├─► GET /network on Controller
  ├─► for each cell:
  │     ├─► compute_coverage_radius_m(band, tx_power_w, generation, antenna_config)
  │     │     └── COST-231-Hata formula → radius in metres
  │     │         Uses live radius from KPI telemetry if within 2× of model estimate
  │     │         (guards against stale InfluxDB data from a previous topology)
  │     └─► append {id, area, lat, lon, vendor, hardware_model, generation, band,
  │                  pci, du_id, cu_id, coverage_radius_m, kpi{...}}
  └─► return {"cells": [...], "total": N}

POST /api/chat   ──► POST /chat on Orchestrator (120 s timeout)
GET  /api/history ──► GET  /history on Orchestrator
DELETE /api/history ──► DELETE /history on Orchestrator
GET  /api/tools  ──► GET  /tools on Orchestrator
GET  /api/orch-health ──► GET /health on Orchestrator
```

All Orchestrator proxy routes return HTTP 503 if the Orchestrator is unreachable, logging the
error without crashing.

## Map UI features

- **Colour by vendor**: Nokia=blue, Ericsson=green, Samsung=purple, ZTE=orange
- **Generation opacity**: solid circle = 5G NR; faded = 4G LTE
- **Status overlay**: red fill = overloaded (PRB > 85%); amber fill = SINR < 5 dB
- **Click popup**: vendor, hardware model, band, DU/CU assignment, PCI, connected UEs, PRB,
  SINR, RSRP, power, throughput, coverage radius
- **Filter controls**: show/hide by generation (4G/5G) and vendor
- **Auto-refresh**: every 30 s (browser `setInterval`)
- **AI chat panel**: right-side panel; uses browser Fetch API with `ReadableStream` for
  live-streaming LLM responses. Conversational UI: user/assistant **message bubbles**,
  in-stream **tool-call chips** (each `*[calling tool: name...]*` rendered as a pill),
  a **typing indicator** while streaming, light markdown (bold + bullet lists), a backend
  badge (shows the active model/backend from `/api/orch-health`), one-click **shortcut
  buttons** (`/status`, `/alerts`, `/cells`, `/plan`, `/son`, `/ue`), and a **New chat**
  reset that clears history and rotates the session. An **expand/collapse toggle** docks the
  chat to a header bar (hiding the message log, chips, and input) to give the map and filters
  more room; the collapsed state is persisted in `localStorage` across reloads. A **drag
  handle** between the map and the panel resizes the panel width left/right (300–800 px,
  persisted; the Leaflet map re-fits on release). The composer is a **multi-line auto-growing
  textarea** (starts ~3 rows / ~92 px, auto-grows to ~280 px, also manually drag-resizable) —
  Enter sends, Shift+Enter inserts a newline. Random session
  ID (`map-xxxxxxx`) per page load (and per reset). Dark theme to match the map basemap.

## Coverage radius computation

`compute_coverage_radius_m(band, tx_power_w, generation, antenna_config)` implements the
**COST-231-Hata** urban macro model (hb=25 m, hm=1.5 m, dense-urban +3 dB correction,
UE NF=7 dB, edge SNR=−3 dB):

1. Convert `tx_power_w` to RF power using generation efficiency (`5G: 22%`, `4G: 32%`)
2. Compute EIRP (dBm) = 10·log₁₀(rf_w × 1000) + antenna\_gain
3. Compute max allowable path loss: EIRP − (thermal\_noise − edge\_SNR) − penetration\_loss
4. Directly invert the COST-231-Hata formula: `d_km = 10^((pl_max − A) / B)`, return
   `d_km × 1000` m

Antenna gain constants: `64T64R = 24.0 dBi`, `4T4R = 17.0 dBi`. Live `coverage_radius_m` from
KPI telemetry is preferred when it is within 2× of the model estimate.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `CONTROLLER_URL` | `http://controller:8080` | Fetches cell list + KPIs for map |
| `ORCHESTRATOR_URL` | `http://orchestrator:8082` | Proxies all chat/history/tools requests |
