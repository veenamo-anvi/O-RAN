# O-RAN Telecom Network Automation

A multi-agent Agentic-AI system that plans, deploys, and autonomously optimises an O-RAN
compliant **4G/5G NSA** network for **Malleswaram, North Bangalore**. The live network is
simulated as a digital twin: **1 CU → 3 DUs → 30 cells** (10 macro sites × 3 sectors), four
vendors (Nokia / Ericsson / Samsung / ZTE), serving 18,400 peak UEs.

```
            Operator (CLI / Map chat)
                     │
            Orchestrator :8082  ── LLM + 14 tools (Claude CLI → Anthropic → Gemini → Mock)
              │          │            │
   Planning :8081   Controller :8080   KPI Agent (BiLSTM + SON)
   (heuristic+MIP)  (topology truth)        │
              └──────────┴──────── InfluxDB :8086 ◄── 3 DU + CU + Core simulators
                                       │
                          Map :8083 (Leaflet) · Grafana :3000
```

## Quick start
```bash
docker compose up --build          # 12 containers
py chat.py                         # operator REPL
# or open the live map + AI chat at http://localhost:8083
python scripts/demo.py             # scripted end-to-end demo
```
No LLM key? The orchestrator falls back to a deterministic **Mock** backend, so the whole
system runs offline. See [`RUNBOOK.md`](./RUNBOOK.md) to enable Gemini / Anthropic / Claude CLI.

## The agents
| Agent | Port | Role |
|---|---|---|
| Orchestrator | 8082 | NL operator commands → tool-calling loop → streamed response |
| Controller | 8080 | Single source of truth for topology; live CRUD + KPI merge |
| Planning | 8081 | Cell placement (heuristic + MIP/CBC), PCI, slicing, multi-period |
| KPI Agent | — | BiLSTM anomaly detection + autonomous SON actions |
| Map Server | 8083 | Leaflet live map + orchestrator proxy |

## Key design rules
- Only the **Controller** writes `topology.json` (atomic); simulators poll read-only.
- `topology.json` = config/hardware ratings; **InfluxDB** = live time-series. Joined at query time.
- 14 orchestrator tools; `/congestion` is read-only; `n28` (700 MHz) deploys only if explicitly requested.

## Layout
```
agents/{controller,planning,kpi_agent,orchestrator,map_server}
sims/{du_sim,cu_sim,core_sim}   simlib/   tools/dataset_generator.py
dev-env/config/topology.json    data/dataset.csv    grafana/provisioning
tests/   scripts/demo.py   chat.py   docker-compose.yml
```

## Docs
- [`plan.md`](./plan.md) — implementation plan (phases A–G)
- [`specs/spec.md`](./specs/spec.md) — full hierarchical specification
- [`RUNBOOK.md`](./RUNBOOK.md) — deploy, operate, test, troubleshoot

## Tests
8 suites, 127 checks — all green (run any without Docker):
```bash
python tests/test_units.py            # planning/PCI/slicing/congestion units
python tests/integration_test.py      # orchestrator → planning → controller (live HTTP)
python agents/<service>/smoke_test.py # per-service smoke tests
```
