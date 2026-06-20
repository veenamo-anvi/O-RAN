# Implementation Plan — Telecom Network Automation (O-RAN Multi-Agent System)

> Derived from the hierarchical spec tree under [`specs/`](./specs/spec.md). This plan builds
> the system from scratch as a Docker-Compose dev environment (12 containers). Target
> deployment: Malleswaram, North Bangalore — 30 cells, 10 macro sites × 3 sectors, 4 vendors
> at 25% each.

## Spec Map (parent → child)

The specification is split into a hierarchy. Each build phase below maps to one or more
child specs:

| Spec | Covers | Drives plan phase |
|---|---|---|
| [specs/spec.md](./specs/spec.md) | Root: high-level idea + index | — |
| [01-architecture/spec.md](./specs/01-architecture/spec.md) | System architecture diagram | A |
| └ [network-topology.md](./specs/01-architecture/network-topology.md) | Malleswaram CU/DU/cell layout, bands | A.2 |
| └ [vendor-distribution.md](./specs/01-architecture/vendor-distribution.md) | Per-vendor hardware specs | A.2 |
| [02-agents/spec.md](./specs/02-agents/spec.md) | Agent overview | C–F |
| └ [orchestrator.md](./specs/02-agents/orchestrator.md) | Agent 1 — Orchestrator (:8082) | E |
| └ [chat-cli.md](./specs/02-agents/chat-cli.md) | chat.py CLI client | E.7 |
| └ [controller.md](./specs/02-agents/controller.md) | Agent 2 — Controller (:8080) | A.3 |
| └ [planning-engine.md](./specs/02-agents/planning-engine.md) | Agent 3 — Planning (:8081) | C |
| └ [kpi-agent.md](./specs/02-agents/kpi-agent.md) | Agent 4 — KPI/SON agent | D |
| └ [map-server.md](./specs/02-agents/map-server.md) | Agent 5 — Map Server (:8083) | F |
| [03-dev-environment/spec.md](./specs/03-dev-environment/spec.md) | Runtime env | A, B, F, G |
| └ [containers.md](./specs/03-dev-environment/containers.md) | 12 containers | G.1 |
| └ [influxdb-measurements.md](./specs/03-dev-environment/influxdb-measurements.md) | Measurement schema | A.1 |
| └ [grafana-dashboards.md](./specs/03-dev-environment/grafana-dashboards.md) | 5 dashboards | F.4 |
| [04-task-list/spec.md](./specs/04-task-list/spec.md) | Phase 0–7 task tracking | all |
| [05-reference/spec.md](./specs/05-reference/spec.md) | Input params, API quick-ref | all |

---

## 0. Guiding Principles

- **Single source of truth for topology** — only the Controller writes `topology.json`;
  everything else polls or queries it. Atomic writes (`.tmp` → rename).
- **Single source of truth for KPIs** — InfluxDB holds all time-series; topology config
  lives in `topology.json`. Services merge the two at query time, never store both.
- **LLM never mutates state directly** — the orchestrator calls typed tools; tools hit
  the Controller / Planning API / InfluxDB over HTTP.
- **The cross-cutting invariants in §4 are non-negotiable constraints.**
- **Build inner-out**: data + Controller first, then simulators, then planning, then
  KPI agent, then orchestrator, then map/dashboards.

---

## 1. Repository Layout

```
O-RAN/
├── docker-compose.yml
├── .env / .env.example             # LLM credentials (env_file for orchestrator; .env git-ignored)
├── .gitignore
├── README.md  ·  RUNBOOK.md  ·  plan.md  ·  specs/
├── chat.py                         # operator CLI REPL (stdlib only)
├── dev-env/
│   ├── gen_topology.py  ·  SCHEMA.md
│   └── config/topology.json        # 30-cell Malleswaram source of truth
├── simlib/                         # shared sim physics (load curve, KPI gen, influx I/O)
├── agents/
│   ├── controller/                 # :8080  topology control plane
│   ├── planning/                   # :8081  planning engine (heuristic + MIP)
│   ├── kpi_agent/                  # background BiLSTM SON agent (+ kpi_model.pt)
│   ├── orchestrator/               # :8082  LLM chat + 14 tools (4 backends)
│   └── map_server/                 # :8083  Leaflet.js map + proxy (+ static/index.html)
├── sims/
│   ├── du_sim/                     # 3× DU simulators (4G+5G RAN)
│   ├── cu_sim/                     # 1× CU simulator (RRC/PDCP)
│   └── core_sim/                   # AMF/SMF/UPF
├── grafana/
│   └── provisioning/               # datasource + 5 dashboards (+ gen_dashboards.py)
├── tools/dataset_generator.py      # 50,400-row synthetic CSV
├── data/dataset.csv                # generated training dataset
├── scripts/demo.py                 # scripted end-to-end chat demo
└── tests/                          # test_units.py · integration_test.py
```

---

## 2. Build Phases (ordered)

### Phase A — Foundation: Schema, Topology, Controller
**Goal:** the live control plane and data model exist and are queryable.

1. **Data schema** — define the 9 InfluxDB measurements (`cell_kpi`, `du_kpi`, `cu_kpi`,
   `core_kpi`, `ue_mobility`, `ue_usage`, `alerts`, `son_actions`, `topology_event`)
   with the exact tag/field sets from the spec.
2. **`topology.json`** — author the 30-cell Malleswaram deployment:
   - 10 macro sites × 3 sectors; CU-MLS over DU-MLS-1 (12 cells), DU-MLS-2 (9), DU-MLS-3 (9).
   - Sector mix per site type (high-traffic vs residential) exactly as the spec tables.
   - Vendor distribution 25% each (Nokia / Ericsson / Samsung / ZTE), full hardware metadata
     per cell (`vendor`, `hardware_model`, `generation`, `antenna_config`, `tx_power_w`,
     `idle_power_w`, `peak_dl_mbps`, `freq_mhz`, `pci`, `max_ues`).
   - No `n28` anywhere. Deployed bands: `n78`, `n41`, `B3`, `B40`.
3. **Controller FastAPI (:8080)** — implement all routes:
   - `GET /health /topology /network /cells /cells/{id} /dus /cus /neighbors/{id} /congestion`
   - `POST /move/cell /move/du /son/pci-reopt /topology/replace /cells/add`, `DELETE /cells/{id}`
   - KPI merge from `cell_kpi` (last 3 min) joined on `cell_id`.
   - `GET /cells/{id}` → config + 30-min time series (ascending by time).
   - PCI auto-assign on `/cells/add` when `pci:0` (smallest unused ≥ 1).
   - `GET /congestion` composite scorer:
     `0.40·PRB + 0.20·(1−SINR/25) + 0.20·(BLER/20) + 0.20·(latency/150)`, each term
     clamped [0,1]; levels CRITICAL>0.75 / HIGH>0.55 / MODERATE>0.35 / LOW≤0.35; sorted desc.
   - `POST /son/pci-reopt` — re-assign PCI for cell + Haversine neighbours
     collision/confusion-free, write `topology_event`.
   - Atomic topology writes; `topology_event` written on every mutation.

**Exit criteria:** Controller boots, serves `/network` against the seeded topology,
mutations persist atomically and emit `topology_event`.

### Phase B — Digital Twin: Simulators + Dataset
**Goal:** synthetic, physically-plausible telemetry flows into InfluxDB.

1. **DU simulator** (×3) — read `topology.json`, poll every `TOPO_POLL_SEC` (5 s),
   reconfigure live without restart. Emit `cell_kpi` (full field set incl. the 7 extended
   fields: `rsrq_db, cqi, mcs, bler_pct, latency_ms, jitter_ms, interference_dbm`) +
   `du_kpi` + `ue_mobility` + `ue_usage`. Diurnal load curve + `WEEKEND_FACTOR=0.75`.
   COST-231-Hata for coverage/SINR. Stream every ~10 s.
2. **CU simulator** (×1) — emit `cu_kpi` (RRC/PDCP, F1/N2/N3/E1 latencies).
3. **Core simulator** — emit `core_kpi` for AMF / SMF / UPF (field set varies by component).
4. **`dataset_generator.py`** — standalone; 50,400 rows (70 days × 24 h × 30 cells), 32
   columns, class mix 70/15/8/5/2; CLI `--days --seed --out`. Used to train the BiLSTM.

**Exit criteria:** Grafana shows live KPIs; dataset CSV generates with correct class
distribution.

### Phase C — Planning Engine (:8081)
**Goal:** generate complete network plans from high-level parameters.

1. **10-step `generate_plan()` pipeline**: select_cells → assign_pcis (graph-colouring,
   collision+confusion free) → assign_dus → assign_cus → centroids → timing_sync →
   allocate_slices (eMBB/URLLC/mMTC PRB split) → fronthaul_routing → `plan_to_topology()`
   (preserve ALL hardware fields) → store in `_plans` keyed by UUID.
2. **Heuristic placement** — density-weighted Haversine candidate scoring.
3. **MIP placement** (`mip_placer.py`, Almoghathawi et al. 2024) — CBC via `pulp`;
   objective `Σ c_jt·z_jt + r_jt·y_jt`; constraints (2)–(8) incl. linearised SINR QoS;
   COST-231-Walfisch-Ikegami NLOS path loss; falls back to heuristic on timeout/infeasible.
4. **Demand clusters** — 10 Bangalore clusters (Tutschku demand-node concept).
5. **Multi-period** — Case A (phased/expanding) + Case B (temporary/shifting); BS reuse.
6. **Routes:** `GET /health /candidates /demand-clusters /plan/{id}`,
   `POST /plan /plan/multi-period /plan/apply`.
   - Default `spectrum_bands=["n78","n41","B3","B40"]`; accept `n28` only if passed
     explicitly; never inject it into defaults/candidates/topology.
   - `mip_time_limit_sec` is a request field (default 120), not an env var.
   - `/plan/apply` → `POST /topology/replace` on Controller.

**Exit criteria:** `/plan` returns a valid plan; `/plan/apply` deploys it live; DU sims
pick up the new topology within `TOPO_POLL_SEC`.

### Phase D — KPI Monitoring & SON Agent (background)
**Goal:** autonomous anomaly detection + corrective actions.

1. **BiLSTM `KPIClassifier`** (`model.py`) — 2-layer bidirectional, hidden=64, dropout=0.25;
   input `(batch, SEQ_LEN=6, N_FEATURES=9)`; head 128→64→ReLU→Dropout→64→5; classes
   NORMAL/OVERLOAD/UNDERLOAD/SINR_LOW/POWER_WASTE; per-feature min/range normalisation
   spanning 4G+5G ranges.
2. **`train.py`** — train from dataset (70/15/8/5/2), `WeightedRandomSampler`; save
   `kpi_model.pt`. `load_or_train()` trains on first boot if weights absent.
3. **Monitor loop** — `connect_influx()` (19×6 s retries); every `POLL_SEC`:
   `query_latest_cell_kpis()` (9 fields) → per-cell deque(maxlen=SEQ_LEN) → infer when full,
   else rule-based fallback (conf=-1.0). Act when rule-based OR conf ≥ `MIN_CONFIDENCE` (0.70).
4. **SON actions** (write `alerts` + `son_actions`):
   - OVERLOAD → `LOAD_BALANCE`, `POST /move/cell` to lightest DU, 3-cycle cooldown (`_last_moved`).
   - UNDERLOAD → `TRAFFIC_STEER` (recommend; enable sleep/DTX).
   - SINR_LOW → `PCI_REOPT_REQUEST` + `POST /son/pci-reopt`.
   - POWER_WASTE → `DTX_RECOMMEND` (~35% watt saving estimate).
   - `POLL_INTERVAL_SEC` code default `10`, Docker override `30`.

**Exit criteria:** agent loads/ trains model, classifies live cells, and dispatches SON
actions that appear in `alerts`/`son_actions` and move cells via the Controller.

### Phase E — Orchestrator (:8082) + CLI
**Goal:** natural-language control with multi-backend LLM + 14 tools.

1. **Tool layer (`tools.py`)** — all **14** tool schemas in Anthropic-style JSON
   (incl. `optimize_congestion` → `GET /congestion`). `TOOL_MAP` executes each over HTTP.
2. **Backends** — fixed priority: Claude CLI → Anthropic API → Gemini → Mock.
   - Claude CLI (`CustomAnthropicClient` spawning `claude -p`), schemas as-is.
   - Anthropic API (native SDK tool loop), schemas as-is.
   - Gemini (`google-genai`, `_clean_params()` strips `default` + empty `enum`).
   - Mock (deterministic keyword→tool router, no creds).
   - `ANTHROPIC_MODEL_NAME` (default `sonnet`) is the single source of truth —
     the spawned model and `/health.model` MUST be identical. The direct Anthropic API
     requires concrete ids, so the alias is resolved for that backend (`sonnet` →
     `claude-sonnet-4-6`) and `/health` reports the resolved id.
   - Credentials supplied via repo-root `.env` (compose `env_file`); `.env.example` is the
     template. No key set → Mock backend.
3. **Request flow** — `build_network_context()` (GET /network) appended to `SYSTEM_PROMPT`
   each request; `while True` tool-calling loop; multiple tools per turn; JSON-sanitise
   results before re-injection.
4. **Streaming** — `POST /chat` returns `StreamingResponse` over a sync generator
   (`chat_turn`); emit `*[calling tool: name...]*`; quota/429 error handling.
5. **Sessions** — `_gemini_sessions` / `_claude_sessions` per `session_id`; `GET /history`
   normalises both; `DELETE /history` clears.
6. **Routes** — `POST /chat`, `GET/DELETE /history`, `GET /tools` (14), `GET /health`.
7. **`chat.py`** — stdlib-only REPL; `/status /alerts /cells /plan /son /ue /history /clear
   /tools`; `--url --session`; health banner on start.

**Exit criteria:** `chat.py` drives an end-to-end command (e.g. "/status") through a
backend and tool calls; `/health` reports the true active model and backend.

### Phase F — Map Server (:8083) + Dashboards
**Goal:** live visualisation + operator dashboards.

1. **Map server** — `GET /api/cells` (GET /network + `compute_coverage_radius_m` per cell,
   prefer live radius within 2× of model estimate); proxy `POST /api/chat`,
   `GET/DELETE /api/history`, `GET /api/tools`, `GET /api/orch-health` (503 if orch down).
2. **Leaflet UI** — vendor colours (Nokia blue / Ericsson green / Samsung purple / ZTE
   orange); 5G solid vs 4G faded; overload/SINR status overlays; click popups; gen+vendor
   filters; 30 s auto-refresh; right-side AI chat panel (Fetch `ReadableStream`, random
   `map-xxxxxxx` session). Conversational chat UX: message bubbles, in-stream tool-call
   chips, typing indicator, backend badge, shortcut buttons, a New-chat reset, an
   expand/collapse toggle (docks chat to a header bar; persisted), a drag handle to resize
   the panel width (300–800 px, persisted), and a multi-line auto-growing composer
   (Enter sends, Shift+Enter newline).
3. **`compute_coverage_radius_m`** — COST-231-Hata inversion with the spec's constants
   (efficiencies 5G 22% / 4G 32%; 64T64R 24 dBi / 4T4R 17 dBi).
4. **Grafana** — datasource provisioning + 5 dashboards (`network_overview`, `cell_kpi`,
   `ue_analytics`, `son_alerts`, `du_cu_performance`).

**Exit criteria:** map renders all 30 cells with live KPIs; chat panel streams; 5
dashboards load against InfluxDB.

### Phase G — Compose, Testing & Demo
1. **`docker-compose.yml`** — 12 containers with the spec's env vars/ports/mounts;
   `topology.json` mounted RW to Controller, RO to simulators; Docker overrides
   (`CLAUDE_CLI_PATH=/usr/bin/claude`, `GEMINI_MODEL=gemini-2.5-flash`,
   `POLL_INTERVAL_SEC=30`). Orchestrator loads LLM credentials from `env_file: .env`
   (`.env.example` template; `.env` git-ignored). Plus `README.md` and `RUNBOOK.md`.
2. **Unit tests** — placement, PCI graph-colouring, slice allocation, congestion scorer.
3. **Integration test** — orchestrator → planning → controller → DU reconfigures.
4. **Demo script** — deploy Bangalore network from scratch via chat.
5. **Deployment runbook**.

---

## 3. Container & Port Map (12 total)

| Container | Port | Phase |
|---|---|---|
| influxdb | 8086 | A |
| grafana | 3000 | F |
| core-sim | — | B |
| cu-mls | — | B |
| du-mls-1/2/3 | — | B |
| controller | 8080 | A |
| planning-api | 8081 | C |
| kpi-agent | — | D |
| orchestrator | 8082 | E |
| map-server | 8083 | F |

---

## 4. Critical Cross-Cutting Invariants

- 14 tools everywhere (system prompt, `GET /tools`, API quick-ref, docs).
- `/congestion` is read-only — recommends, never moves cells.
- `n28` supported-but-not-deployed; explicit-only, never in defaults/candidates/topology.
- 4-backend priority order fixed at startup; first available wins.
- Model reported == model spawned (`ANTHROPIC_MODEL_NAME`).
- KPI poll code default 10, Docker 30.
- `/son/pci-reopt` is implemented (re-optimises PCI for cell + neighbours).
- Cell naming `MLS_<SITE>_<SECTOR>`; PCI collision- AND confusion-free throughout.

---

## 5. Suggested Sequencing & Dependencies

```
A (schema+controller+topology)
 └─► B (simulators+dataset)  ──► Grafana data available
      ├─► C (planning) ──────────► depends on Controller /topology/replace
      ├─► D (KPI agent) ─────────► depends on cell_kpi stream + Controller moves
      └─► E (orchestrator) ──────► depends on Controller, Planning, InfluxDB
            └─► F (map+dashboards) ► depends on Controller + Orchestrator
                  └─► G (compose, tests, demo)
```

Phases C, D, E can proceed in parallel once A+B are stable, since they each depend only on
the Controller's HTTP surface and InfluxDB.

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| InfluxDB lag causing SON thrash | 3-cycle move cooldown (`_last_moved`) per cell. |
| Stale KPI radius after topology swap | Prefer live radius only within 2× of model estimate. |
| MIP solver timeout/infeasible | Fall back to heuristic placement automatically. |
| Backend model mismatch | Construct client with resolved name; assert in `/health`. |
| `n28` leaking into defaults | Centralise default band list; unit-test exclusion. |
| First-boot with no model weights | `load_or_train()` trains from dataset then saves. |

---

## 7. Definition of Done

- 12 containers come up under `docker compose up`; all `/health` endpoints green.
- Map renders 30 cells with live KPIs; 5 Grafana dashboards populate.
- `chat.py` deploys/queries/reorganises the network end-to-end via an LLM backend.
- KPI agent autonomously load-balances an induced overload and logs SON actions.
- All cross-cutting invariants (§4) verified by tests.
