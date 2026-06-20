# 02.5 — Agent 4: KPI Monitoring Agent (`agents/kpi_agent/`)

> **Parent:** [Agent Architecture](./spec.md) › [Root Spec](../spec.md)

Background process (no HTTP port). Polls InfluxDB on a fixed cadence, maintains a per-cell
sliding window, classifies cell state with a BiLSTM model, and takes autonomous SON actions
without operator involvement.

## Internal flow

```
main()
  │
  ├─► load_or_train()
  │     └── loads kpi_model.pt if exists; else trains from scratch via train.py
  │         and saves weights before returning
  │
  ├─► connect_influx()  (up to 19 attempts × 6 s delay)
  │
  └─► loop every POLL_SEC:
        │
        ├─► query_latest_cell_kpis()
        │     └── Flux: cell_kpi last 3 min → last() per cell → pivot
        │         Returns 9 fields per cell (prb_dl_pct, sinr_db, connected_ues,
        │         power_w, packet_loss_pct, dl_throughput_mbps, cqi, bler_pct, latency_ms)
        │
        └─► analyse(model, cells, buffers, write_api, cycle)
              │
              ├─► build DU load map: du_avg[du_id] = mean(prb_dl_pct of cells on DU)
              │
              └─► per cell:
                    ├─► extract_features() → append to deque(maxlen=SEQ_LEN)
                    │
                    ├─► if buffer full: infer(model, buf) → (class, confidence)
                    │   else: rule-based fallback → (class, conf=-1.0)
                    │
                    └─► if act (rule-based OR conf ≥ MIN_CONFIDENCE):
                            dispatch SON action (see below)
```

## BiLSTM model (`model.py` — `KPIClassifier`)

- 2-layer **bidirectional** LSTM, `hidden=64`, `dropout=0.25`
- Input: `(batch, SEQ_LEN=6, N_FEATURES=9)` — 60 s of history per cell
- Head: Linear(128→64) → ReLU → Dropout(0.25) → Linear(64→5)
- 5 output classes: NORMAL (0), OVERLOAD (1), UNDERLOAD (2), SINR_LOW (3), POWER_WASTE (4)
- Feature normalisation: per-feature min-value and range (covers both 4G and 5G hardware
  ranges)
- Trained on synthetic data (70% NORMAL / 15% OVERLOAD / 8% UNDERLOAD / 5% SINR_LOW /
  2% POWER_WASTE); `WeightedRandomSampler` for balanced mini-batches

## SON actions

| Detected class | Alert written | SON action written | Autonomous action |
|---|---|---|---|
| OVERLOAD | `alerts` WARNING/OVERLOAD | `son_actions` LOAD_BALANCE | `POST /move/cell` to lightest DU; 3-cycle cooldown gate (`_last_moved`) prevents thrashing while InfluxDB data catches up |
| UNDERLOAD | `alerts` INFO/UNDERLOAD | `son_actions` TRAFFIC_STEER | Recommends handing UEs to least-loaded other DU (enable sleep/DTX) |
| SINR_LOW | `alerts` CRITICAL/SINR_DEGRADATION | `son_actions` PCI_REOPT_REQUEST | `POST /son/pci-reopt` on Controller — re-optimises PCI for the cell and its neighbours |
| POWER_WASTE | `alerts` WARNING/POWER_WASTE | `son_actions` DTX_RECOMMEND | Recommends DTX/sleep; estimates 35% watt saving |

The OVERLOAD branch writes LOAD_BALANCE to both `alerts` (INFO) and `son_actions` so the
action appears in both the KPI alert feed and the SON dashboard panel.

## Rule-based fallback thresholds

| Threshold | Default | Override env var |
|---|---|---|
| Overload PRB | 85% | `OVERLOAD_PRB_PCT` |
| Underload PRB | 20% | `UNDERLOAD_PRB_PCT` |
| Min SINR | 5 dB | `SINR_MIN_DB` |
| Power waste W | 500 W | `POWER_WASTE_W` |
| Power waste min UEs | 15 | `POWER_WASTE_MIN_UES` |

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `INFLUX_URL` | `http://influxdb:8086` | KPI polling and alert/SON writes |
| `INFLUX_TOKEN` / `INFLUX_ORG` / `INFLUX_BUCKET` | — | InfluxDB auth |
| `CONTROLLER_URL` | `http://controller:8080` | `move_cell` HTTP call for OVERLOAD action |
| `POLL_INTERVAL_SEC` | `10` (code) / `30` (Docker) | Poll cadence; window fills in `SEQ_LEN × POLL_SEC`. Code default is **10**; Docker overrides to `30` |
| `MODEL_PATH` | `kpi_model.pt` | LSTM weights; trains from scratch on first boot if absent |
| `MIN_CONFIDENCE` | `0.70` | Minimum softmax confidence to act on a model prediction |
