"""Agent 4 — KPI Monitoring & SON (background, no HTTP port).

Polls InfluxDB cell_kpi, keeps a per-cell sliding window, classifies with the BiLSTM
(rule-based fallback until the window fills / when confidence is low), and dispatches
autonomous SON actions, writing alerts + son_actions and calling the Controller.
"""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from model import CLASSES, FEATURES, SEQ_LEN, normalize

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("kpi_agent")

POLL_SEC = float(os.environ.get("POLL_INTERVAL_SEC", "10"))        # [R6] code default 10
MODEL_PATH = os.environ.get("MODEL_PATH", "kpi_model.pt")
MIN_CONFIDENCE = float(os.environ.get("MIN_CONFIDENCE", "0.70"))
CONTROLLER_URL = os.environ.get("CONTROLLER_URL", "http://controller:8080")

OVERLOAD_PRB = float(os.environ.get("OVERLOAD_PRB_PCT", "85"))
UNDERLOAD_PRB = float(os.environ.get("UNDERLOAD_PRB_PCT", "20"))
SINR_MIN = float(os.environ.get("SINR_MIN_DB", "5"))
POWER_WASTE_W = float(os.environ.get("POWER_WASTE_W", "500"))
POWER_WASTE_MIN_UES = float(os.environ.get("POWER_WASTE_MIN_UES", "15"))

MOVE_COOLDOWN_CYCLES = 3

INFLUX_URL = os.environ.get("INFLUX_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN", "telecom-super-secret-auth-token-2026")
INFLUX_ORG = os.environ.get("INFLUX_ORG", "telecom")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "telecom_metrics")


# --------------------------------------------------------------------------- features
def extract_features(kpi: dict[str, Any]) -> list[float]:
    return [float(kpi.get(name, 0.0) or 0.0) for name in FEATURES]


def classify_rule(kpi: dict[str, Any]) -> str:
    prb = float(kpi.get("prb_dl_pct", 0) or 0)
    sinr = float(kpi.get("sinr_db", 99) or 99)
    power = float(kpi.get("power_w", 0) or 0)
    ues = float(kpi.get("connected_ues", 0) or 0)
    if prb > OVERLOAD_PRB:
        return "OVERLOAD"
    if sinr < SINR_MIN:
        return "SINR_LOW"
    if power > POWER_WASTE_W and ues < POWER_WASTE_MIN_UES:
        return "POWER_WASTE"
    if prb < UNDERLOAD_PRB:
        return "UNDERLOAD"
    return "NORMAL"


# --------------------------------------------------------------------------- model
def load_or_train():
    """Load kpi_model.pt; train from scratch on first boot if absent."""
    import torch
    from model import KPIClassifier

    if not os.path.exists(MODEL_PATH):
        log.info("model %s not found — training from scratch", MODEL_PATH)
        import train
        train.train(train._default_dataset(), MODEL_PATH, epochs=8)

    ckpt = torch.load(MODEL_PATH, map_location="cpu")
    model = KPIClassifier()
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model, ckpt.get("norm", {})


def infer(model, norm, window: list[list[float]]) -> tuple[str, float]:
    import torch
    x = torch.tensor([[normalize(step, norm) for step in window]], dtype=torch.float32)
    with torch.no_grad():
        probs = torch.softmax(model(x), dim=1)[0]
    idx = int(torch.argmax(probs).item())
    return CLASSES[idx], float(probs[idx].item())


# --------------------------------------------------------------------------- influx
def connect_influx(retries: int = 19, delay: float = 6.0):
    from influxdb_client import InfluxDBClient
    last = None
    for attempt in range(1, retries + 1):
        try:
            client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=10_000)
            if client.ping():
                log.info("connected to InfluxDB")
                return client
        except Exception as exc:  # noqa: BLE001
            last = exc
        log.warning("InfluxDB not ready (%d/%d): %s", attempt, retries, last)
        time.sleep(delay)
    raise RuntimeError(f"InfluxDB unreachable: {last}")


def query_latest_cell_kpis(client) -> dict[str, dict[str, Any]]:
    flux = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -3m)
  |> filter(fn: (r) => r._measurement == "cell_kpi")
  |> group(columns: ["cell_id", "_field"])
  |> last()
  |> pivot(rowKey: ["cell_id"], columnKey: ["_field"], valueColumn: "_value")
'''
    out: dict[str, dict[str, Any]] = {}
    for table in client.query_api().query(flux, org=INFLUX_ORG):
        for rec in table.records:
            cid = rec.values.get("cell_id")
            if cid:
                kpi = {k: v for k, v in rec.values.items() if not k.startswith("_") and v is not None}
                kpi["du_id"] = rec.values.get("du_id")
                out[cid] = kpi
    return out


# --------------------------------------------------------------------------- SON
ACTION_FOR_CLASS = {
    "OVERLOAD": ("WARNING", "LOAD_BALANCE"),
    "UNDERLOAD": ("INFO", "TRAFFIC_STEER"),
    "SINR_LOW": ("CRITICAL", "PCI_REOPT_REQUEST"),
    "POWER_WASTE": ("WARNING", "DTX_RECOMMEND"),
}


class SonDispatcher:
    """Executes SON actions: writes alerts + son_actions and calls the Controller.

    Injectable `write_api` / `http` make the decision path unit-testable offline.
    """

    def __init__(self, write_api=None, http=requests, controller_url: str = CONTROLLER_URL) -> None:
        self.write_api = write_api
        self.http = http
        self.controller_url = controller_url
        self._last_moved: dict[str, int] = {}

    def _write(self, measurement: str, tags: dict[str, str], fields: dict[str, Any]) -> None:
        if self.write_api is None:
            return
        from influxdb_client import Point
        p = Point(measurement)
        for k, v in tags.items():
            p = p.tag(k, str(v))
        for k, v in fields.items():
            p = p.field(k, v)
        p = p.time(datetime.now(timezone.utc))
        self.write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=p)

    def lightest_du(self, du_loads: dict[str, float], exclude: Optional[str]) -> Optional[str]:
        cand = {d: l for d, l in du_loads.items() if d != exclude}
        return min(cand, key=cand.get) if cand else None

    def dispatch(self, cell_id: str, du_id: str, cls: str, conf: float,
                 kpi: dict[str, Any], du_loads: dict[str, float], cycle: int) -> Optional[dict[str, Any]]:
        if cls == "NORMAL" or cls not in ACTION_FOR_CLASS:
            return None
        severity, action = ACTION_FOR_CLASS[cls]
        msg = f"{cls} detected on {cell_id}"
        ai_conf = round(conf, 3) if conf >= 0 else -1.0

        self._write("alerts",
                    {"severity": severity, "cell_id": cell_id, "du_id": du_id, "alert_type": cls},
                    {"message": msg, "metric_value": float(kpi.get("prb_dl_pct", 0) or 0),
                     "threshold": OVERLOAD_PRB, "ai_confidence": ai_conf})
        self._write("son_actions",
                    {"cell_id": cell_id, "du_id": du_id, "action_type": action},
                    {"message": msg, "confidence": ai_conf})

        result: dict[str, Any] = {"cell_id": cell_id, "class": cls, "action": action, "confidence": ai_conf}

        if cls == "OVERLOAD":
            # also log LOAD_BALANCE to alerts (INFO) so it appears in both feeds
            self._write("alerts",
                        {"severity": "INFO", "cell_id": cell_id, "du_id": du_id, "alert_type": "LOAD_BALANCE"},
                        {"message": f"LOAD_BALANCE on {cell_id}", "ai_confidence": ai_conf})
            if cycle - self._last_moved.get(cell_id, -999) >= MOVE_COOLDOWN_CYCLES:
                target = self.lightest_du(du_loads, exclude=du_id)
                if target:
                    try:
                        self.http.post(f"{self.controller_url}/move/cell",
                                       json={"cell_id": cell_id, "to_du_id": target}, timeout=10)
                        self._last_moved[cell_id] = cycle
                        result["moved_to"] = target
                    except Exception as exc:  # noqa: BLE001
                        log.warning("move/cell failed: %s", exc)
            else:
                result["cooldown"] = True
        elif cls == "SINR_LOW":
            try:
                self.http.post(f"{self.controller_url}/son/pci-reopt",
                               json={"cell_id": cell_id, "du_id": du_id}, timeout=10)
                result["pci_reopt"] = True
            except Exception as exc:  # noqa: BLE001
                log.warning("son/pci-reopt failed: %s", exc)
        elif cls == "POWER_WASTE":
            result["est_watt_saving"] = round(float(kpi.get("power_w", 0) or 0) * 0.35, 1)
        return result


# --------------------------------------------------------------------------- main loop
def analyse(model, norm, cells, buffers, dispatcher, cycle) -> list[dict[str, Any]]:
    du_loads: dict[str, list[float]] = defaultdict(list)
    for cid, kpi in cells.items():
        du_loads[kpi.get("du_id")].append(float(kpi.get("prb_dl_pct", 0) or 0))
    du_avg = {d: (sum(v) / len(v) if v else 0.0) for d, v in du_loads.items()}

    actions = []
    for cid, kpi in cells.items():
        buffers[cid].append(extract_features(kpi))
        if model is not None and len(buffers[cid]) == SEQ_LEN:
            cls, conf = infer(model, norm, list(buffers[cid]))
            act = conf >= MIN_CONFIDENCE
        else:
            cls, conf = classify_rule(kpi), -1.0
            act = True
        if act:
            res = dispatcher.dispatch(cid, kpi.get("du_id"), cls, conf, kpi, du_avg, cycle)
            if res:
                actions.append(res)
    return actions


def main() -> None:
    from influxdb_client.client.write_api import SYNCHRONOUS

    model, norm = load_or_train()
    client = connect_influx()
    dispatcher = SonDispatcher(write_api=client.write_api(write_options=SYNCHRONOUS))
    buffers: dict[str, deque] = defaultdict(lambda: deque(maxlen=SEQ_LEN))
    log.info("KPI agent started (poll=%ss, min_conf=%.2f)", POLL_SEC, MIN_CONFIDENCE)

    cycle = 0
    while True:
        start = time.time()
        try:
            cells = query_latest_cell_kpis(client)
            acts = analyse(model, norm, cells, buffers, dispatcher, cycle)
            if acts:
                log.info("cycle %d: %d SON actions: %s", cycle, len(acts),
                         [f"{a['class']}:{a['cell_id']}" for a in acts])
        except Exception as exc:  # noqa: BLE001
            log.warning("cycle %d failed: %s", cycle, exc)
        cycle += 1
        time.sleep(max(0.0, POLL_SEC - (time.time() - start)))


if __name__ == "__main__":
    main()
