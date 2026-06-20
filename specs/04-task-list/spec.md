# 04 — Task List (Due: 15 June 2026)

> **Parent:** [Root Spec](../spec.md)

## Phase 0 — Digital Twin & Dataset ✅ COMPLETE
- [x] **DU simulator extended** — 7 new KPI fields: rsrq_db, cqi, mcs, bler_pct, latency_ms, jitter_ms, interference_dbm (physics-based, correlated with SINR/load)
- [x] **Day-of-week traffic variation** — `WEEKEND_FACTOR = 0.75`; Saturday/Sunday load scaled down in `load_factor()`
- [x] **`dataset_generator.py`** — standalone script; 50,400-row CSV (70 days × 24 h × 30 cells); 32 columns; realistic class distribution (70% NORMAL / 15% OVERLOAD / 8% UNDERLOAD / 5% SINR_LOW / 2% POWER_WASTE); CLI: `--days`, `--seed`, `--out`
- [x] KPI values grounded in 4 reference Kaggle datasets (suraj520/cellular-network-performance-data, srikumarnayak/5g-network-kpi-dataset, praveenaparimi/telecom-network-dataset, suraj520/cellular-network-analysis-dataset)

## Phase 1 — Foundation ✅ COMPLETE
- [x] Define data schema (InfluxDB measurements + topology.json with vendor/hardware metadata)
- [x] Build Controller Agent (GET/POST endpoints, atomic topology CRUD)
- [x] 30-cell Malleswaram deployment: 10 macro sites × 3 sectors; Nokia/Ericsson/Samsung/ZTE 25% each; active_ues_peak 18,400; streaming every 10 s
  - High-traffic sites (RWS, 18C, SNK, SPG, 10C): 5G n78 3500 MHz + 5G n41 2500 MHz + 4G B3 1800 MHz
  - Residential sites (BEL, 3MN, MGR, CHD, 6CR): 5G n78 3500 MHz + 4G B40 2300 MHz + 4G B3 1800 MHz
  - 700 MHz (n28) excluded: 8.4 km coverage radius extends beyond Malleswaram to Peenya
- [x] Deploy dev environment (12 containers: InfluxDB, Grafana, Core, 1×CU, 3×DU, Controller, Planning, KPI, Orchestrator, Map)

## Phase 2 — Planning Engine ✅ COMPLETE + Extended
- [x] Cell placement algorithm (density-weighted heuristic, Haversine distance)
- [x] DU/CU grouping (geographic proximity, configurable max cells/DU and DUs/CU)
- [x] PCI planning (graph-coloring, collision and confusion free)
- [x] Slice allocation (PRB budget per slice from traffic profile)
- [x] Fronthaul/midhaul routing (distance-based latency estimate)
- [x] Planning FastAPI on port 8081 with `/plan` and `/plan/apply` endpoints
- [x] **COST-231 Walfisch-Ikegami NLOS propagation model** (`mip_placer.py`) — urban NLOS path loss for MIP link budget
- [x] **MIP-based optimal placement** (Almoghathawi et al. 2024) — minimises CAPEX+OPEX subject to coverage, capacity, and SINR constraints; solver: CBC via pulp
- [x] **Multi-period planning** — Case A (phased rollout, expanding demand) and Case B (temporary/event-driven demand shift); BS reuse across periods
- [x] **Demand node concept** — 10 Bangalore demand clusters separating traffic demand from infrastructure candidates
- [x] **SINR quality constraint at planning time** — MIP enforces SINR ≥ threshold at each demand cluster (linearised constraint 8 from paper)
- [x] **Installation vs. operational cost split** — one-time CAPEX (c_jt) vs. per-period OPEX (r_jt)
- [x] `/plan/multi-period` endpoint; `use_mip` flag on `/plan`; `plan_network_multi_period` Orchestrator tool

## Phase 3 — Deployment Agent ✅ COMPLETE
- [x] Topology manifest generation from planning outputs (topology.json format)
- [x] Topology propagation: Controller writes atomically to `topology.json`; DU/CU simulators poll every `TOPO_POLL_SEC` (5 s) and reconfigure live — no explicit acknowledgement needed
- [x] **`POST /topology/replace`** added to Controller — `plan/apply` now deploys plans live
- [x] **`plan_to_topology()` fixed** — vendor, hardware_model, generation, antenna_config, tx_power_w, idle_power_w, peak_dl_mbps propagated through CANDIDATE_CELLS and preserved
- [x] **`POST /cells/add`** — conversational single-cell deployment via `add_cell` orchestrator tool
- [x] **`DELETE /cells/{id}`** — remove a cell via `remove_cell` orchestrator tool
- [x] **`GET /neighbors/{cell_id}`** — geographic neighbor lookup for SON ANR
- [ ] Helm/K8s manifest generation (prod — post-demo)
- [ ] SMO northbound API registration (prod — post-demo)

## Phase 4 — KPI Monitoring & Optimization Agent ✅ COMPLETE
- [x] KPI telemetry pipeline (InfluxDB, polled every 30 s)
- [x] Bidirectional LSTM anomaly classifier: NORMAL / OVERLOAD / UNDERLOAD / SINR_LOW / POWER_WASTE
- [x] **9-feature BiLSTM** — added cqi, bler_pct, latency_ms; updated FEATURE_NORM, train.py class specs, and kpi_agent.py extract_features()
- [x] **Realistic training distribution** — 70% NORMAL / 15% OVERLOAD / 8% UNDERLOAD / 5% SINR_LOW / 2% POWER_WASTE; WeightedRandomSampler for balanced training; separate 4G/5G feature specs
- [x] Overload detection (PRB > 85%) → automatic cell-move to lightest DU + `LOAD_BALANCE` written to `alerts` and `son_actions`; 3-cycle per-cell move cooldown prevents InfluxDB-lag thrash
- [x] Underload detection → `TRAFFIC_STEER` SON action written to `son_actions` (recommend handing UEs to least-loaded other DU to enable sleep/DTX)
- [x] SINR degradation → `PCI_REOPT_REQUEST` SON action + best-effort `/son/pci-reopt` Controller call
- [x] Power waste detection → `DTX_RECOMMEND` SON action with estimated watt savings
- [x] Rule-based fallback for first 60 s; AI inference thereafter with confidence gate
- [x] Alert writes to InfluxDB `alerts` measurement with `ai_confidence` field
- [x] SON action writes to InfluxDB `son_actions` measurement with `action_type`, `confidence` fields
- [ ] Reinforcement learning-based power optimizer (future sprint)

## Phase 5 — Orchestrator Agent ✅ COMPLETE
- [x] LLM chat interface (FastAPI POST /chat, streaming via sync generator + StreamingResponse)
- [x] Tool-calling loop: multi-step while loop; all **14** tools wired; tool results JSON-sanitised before re-injection
- [x] Anthropic→Gemini tool schema translation at startup (`_clean_params` strips `default` and empty `enum`)
- [x] Context injection: `build_network_context()` polls Controller `/network` on every request
- [x] Conversation history: per-session in-memory `_sessions` dict of `types.Content` lists
- [x] `chat.py` CLI client: terminal REPL with `/status`, `/alerts`, `/cells`, `/plan`, `/son`, `/ue`, `/history`, `/clear`, `/tools` shortcuts; named sessions via `--session`; no external dependencies
- [x] **4 new tools** — `query_ue` (UE usage/mobility lookup), `get_son_status` (SON action summary), `add_cell` (deploy new cell via chat), `remove_cell` (decommission cell via chat)
- [ ] End-to-end integration test suite

## Phase 6 — Map Visualization & Dashboards ✅ COMPLETE
- [x] Leaflet.js live cell map (port 8083)
- [x] Colour-coded markers: vendor colour + 5G/4G opacity + status (overloaded/SINR low)
- [x] Click popup: vendor, hardware, band, DU/CU, KPIs, coverage radius
- [x] Filter controls: show/hide by generation and vendor
- [x] Auto-refresh every 30 s; status bar with aggregate counts
- [x] AI chat panel integrated in map UI (right-side panel); shortcuts: `/status`, `/alerts`, `/cells`, `/plan`, `/son`, `/ue`
- [x] **5 Grafana dashboards** provisioned via `grafana/provisioning/dashboards/default.yaml`:
  - `network_overview.json` — total UEs, active cells, avg DL/SINR, overloaded cells, total power; UE/PRB/SINR/power timeseries
  - `cell_kpi.json` — per-cell PRB, SINR, RSRP, throughput, power, CQI, BLER+latency; generation filter variable
  - `ue_analytics.json` — UE slice distribution (donut), latency/jitter/bytes by slice, HO event rate and duration
  - `son_alerts.json` — CRITICAL/WARNING counts, SON action counts by type, AI confidence timeseries, SON action log
  - `du_cu_performance.json` — DU CPU/memory/fronthaul latency/F1 msg rate, CU PDCP throughput, core registered UEs, UPF throughput

## Phase 7 — Testing & Demo ✅ COMPLETE
- [x] Unit tests for planning algorithms (placement, PCI, slicing) — `tests/test_units.py` (+ congestion scorer)
- [x] Integration tests (orchestrator → planning → controller → topology reconfigures) — `tests/integration_test.py` (live HTTP across 3 services)
- [x] Demo script: deploy Bangalore network from scratch via chat — `scripts/demo.py`
- [x] Deployment runbook — `RUNBOOK.md`
- [x] Per-service smoke tests for every agent (`agents/*/smoke_test.py`, `sims/smoke_test.py`)
- [x] `docker-compose.yml` — 12-service stack (validated)

> **Build status:** all 8 phases (0–7) implemented and verified — 8 test suites, 127 checks
> green. See [`../../plan.md`](../../plan.md) for the phase-by-phase implementation plan and
> [`../../RUNBOOK.md`](../../RUNBOOK.md) to run the stack.

## Future / Outsource
- [ ] Replace the custom tool-schema layer in `tools.py` with an MCP server so any MCP-compatible LLM (Claude, Gemini, GPT-4o) can discover and call the orchestrator tools without per-provider translation.
