# Deployment Runbook — O-RAN Telecom Network Automation

12-container dev stack simulating a 4G/5G NSA O-RAN network in Malleswaram, North Bangalore
(1 CU → 3 DUs → 30 cells). See [`plan.md`](./plan.md) and [`specs/`](./specs/spec.md).

## Prerequisites
- Docker + Docker Compose
- (optional) `GOOGLE_API_KEY` or `ANTHROPIC_API_KEY` or a mounted `claude` binary for a real
  LLM backend. With none, the orchestrator runs the deterministic **Mock** backend.

## Bring the stack up
```bash
docker compose up --build
```
This starts 12 containers. The Controller seeds from `dev-env/config/topology.json`; the
simulators begin streaming KPIs to InfluxDB within ~10 s; the KPI agent loads the pre-trained
BiLSTM (`kpi_model.pt`) — or trains from the baked dataset on first boot if absent.

| Service | URL |
|---|---|
| Map (Leaflet) | http://localhost:8083 |
| Grafana (anon) | http://localhost:3000 |
| Orchestrator | http://localhost:8082 |
| Planning API | http://localhost:8081 |
| Controller | http://localhost:8080 |
| InfluxDB | http://localhost:8086 |

## Smoke-check after boot
```bash
curl localhost:8080/health      # controller: 30 cells / 3 dus / 1 cu
curl localhost:8081/health      # planning
curl localhost:8082/health      # orchestrator: {"model","backend"}
curl localhost:8083/health      # map server
curl localhost:8080/congestion  # live congestion ranking (after sims warm up)
```

## Drive it
```bash
py chat.py                      # operator REPL  (/status /alerts /cells /plan /son /ue)
python scripts/demo.py          # scripted end-to-end demo via chat
```
Or open the map (http://localhost:8083) and use the right-side AI chat panel.

## Enable a real LLM backend
Priority order: Claude CLI → Anthropic API → Gemini → Mock. In `docker-compose.yml` under
`orchestrator`:
- **Gemini**: set `GOOGLE_API_KEY` (uses `GEMINI_MODEL=gemini-2.5-flash`).
- **Anthropic API**: set `ANTHROPIC_API_KEY` (model = `ANTHROPIC_MODEL_NAME`, default `sonnet`).
- **Claude CLI**: set `CLAUDE_CLI_PATH=/usr/bin/claude` and mount the binary.
`GET /health.model` always reports the model actually in use.

## Tests (no Docker needed)
```bash
python agents/controller/smoke_test.py     # Phase A
python sims/smoke_test.py                  # Phase B
python agents/planning/smoke_test.py       # Phase C
python agents/kpi_agent/smoke_test.py      # Phase D
python agents/orchestrator/smoke_test.py   # Phase E
python agents/map_server/smoke_test.py     # Phase F
python tests/test_units.py                 # Phase G unit tests
python tests/integration_test.py           # Phase G cross-service integration
```

## Regenerate artifacts
```bash
python dev-env/gen_topology.py                       # rebuild topology.json
python tools/dataset_generator.py --days 70 --out data/dataset.csv
python agents/kpi_agent/train.py --epochs 6          # retrain BiLSTM
python grafana/gen_dashboards.py                     # rebuild 5 dashboards
```

## Troubleshooting
- **Sims show no KPIs / map empty**: InfluxDB still initialising — sims retry 19×6 s; wait ~1 min.
- **Controller serves cells but `kpi` empty**: InfluxDB unreachable; topology still served
  (graceful degradation). Check the `influxdb` container is healthy.
- **Orchestrator backend = mock unexpectedly**: no LLM credentials resolved; check env vars.
- **KPI agent slow first boot**: training from dataset if `kpi_model.pt` absent (~1 min).
- **Topology change not reflected in sims**: simulators poll every `TOPO_POLL_SEC` (5 s); wait a cycle.

## Architecture invariants
- Only the **Controller** writes `topology.json` (atomic `.tmp`→rename); sims poll read-only.
- `topology.json` = config/ratings; **InfluxDB** = live time-series. Joined at query time.
- 14 orchestrator tools; `/congestion` is read-only; `n28` deploy only if explicitly requested.
- KPI poll: code default 10 s, Docker override 30 s.
