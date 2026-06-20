"""Phase-D smoke test: rule classifier, BiLSTM train/load/infer, SON dispatch.

No InfluxDB required — uses a tiny training run and fake write/HTTP clients.
"""
import os
import sys
import tempfile
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import kpi_agent as K  # noqa: E402
from model import SEQ_LEN  # noqa: E402

fails = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


# --------------------------------------------------------------- rule classifier
print("rule-based classifier")
check("OVERLOAD", K.classify_rule({"prb_dl_pct": 92, "sinr_db": 9, "power_w": 800, "connected_ues": 700}) == "OVERLOAD")
check("UNDERLOAD", K.classify_rule({"prb_dl_pct": 10, "sinr_db": 18, "power_w": 200, "connected_ues": 5}) == "UNDERLOAD")
check("SINR_LOW", K.classify_rule({"prb_dl_pct": 50, "sinr_db": 2, "power_w": 600, "connected_ues": 200}) == "SINR_LOW")
check("POWER_WASTE", K.classify_rule({"prb_dl_pct": 8, "sinr_db": 18, "power_w": 700, "connected_ues": 6}) == "POWER_WASTE")
check("NORMAL", K.classify_rule({"prb_dl_pct": 45, "sinr_db": 15, "power_w": 400, "connected_ues": 200}) == "NORMAL")

# --------------------------------------------------------------- SON dispatch (fakes)
print("SON dispatch (fake write_api + http)")


class FakeWrite:
    def __init__(self):
        self.lines = []

    def write(self, bucket=None, org=None, record=None):
        self.lines.append(record.to_line_protocol())


class FakeResp:
    status_code = 200

    def json(self):
        return {"status": "ok"}


class FakeHttp:
    def __init__(self):
        self.posts = []

    def post(self, url, json=None, timeout=None):
        self.posts.append((url, json))
        return FakeResp()


fw, fh = FakeWrite(), FakeHttp()
disp = K.SonDispatcher(write_api=fw, http=fh, controller_url="http://ctrl")
du_loads = {"DU-MLS-1": 90.0, "DU-MLS-2": 20.0, "DU-MLS-3": 55.0}

r = disp.dispatch("MLS_RWS_01", "DU-MLS-1", "OVERLOAD", 0.91,
                  {"prb_dl_pct": 92, "connected_ues": 700, "power_w": 800}, du_loads, cycle=0)
check("OVERLOAD action LOAD_BALANCE", r["action"] == "LOAD_BALANCE")
check("OVERLOAD moved to lightest DU (DU-MLS-2)", r.get("moved_to") == "DU-MLS-2")
check("OVERLOAD posted move/cell", any("move/cell" in u for u, _ in fh.posts))
check("alerts+son_actions written", any("son_actions" in l for l in fw.lines) and any("alerts" in l for l in fw.lines))

# cooldown: immediate re-dispatch should NOT move again
r2 = disp.dispatch("MLS_RWS_01", "DU-MLS-1", "OVERLOAD", 0.91,
                   {"prb_dl_pct": 92, "connected_ues": 700, "power_w": 800}, du_loads, cycle=1)
check("OVERLOAD cooldown blocks re-move", r2.get("cooldown") is True and "moved_to" not in r2)

fh2 = FakeHttp()
disp2 = K.SonDispatcher(write_api=FakeWrite(), http=fh2, controller_url="http://ctrl")
rs = disp2.dispatch("MLS_18C_01", "DU-MLS-1", "SINR_LOW", 0.88,
                    {"sinr_db": 2, "prb_dl_pct": 50}, du_loads, cycle=0)
check("SINR_LOW action PCI_REOPT_REQUEST", rs["action"] == "PCI_REOPT_REQUEST")
check("SINR_LOW posted son/pci-reopt", any("son/pci-reopt" in u for u, _ in fh2.posts))

rp = disp2.dispatch("MLS_BEL_01", "DU-MLS-1", "POWER_WASTE", 0.80,
                    {"power_w": 700, "connected_ues": 6}, du_loads, cycle=0)
check("POWER_WASTE action DTX_RECOMMEND + saving", rp["action"] == "DTX_RECOMMEND" and rp["est_watt_saving"] > 0)

ru = disp2.dispatch("MLS_MGR_01", "DU-MLS-3", "UNDERLOAD", 0.75,
                    {"prb_dl_pct": 10}, du_loads, cycle=0)
check("UNDERLOAD action TRAFFIC_STEER", ru["action"] == "TRAFFIC_STEER")

check("NORMAL -> no action", disp2.dispatch("x", "DU-MLS-1", "NORMAL", 0.99, {}, du_loads, 0) is None)

# --------------------------------------------------------------- BiLSTM train/load/infer
print("BiLSTM train (tiny) / load / infer")
import train  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    out = os.path.join(td, "kpi_model.pt")
    ds = train._default_dataset()
    if not os.path.exists(ds):
        check("dataset present", False)
    else:
        train.train(ds, out, epochs=1, limit_rows=9000)
        os.environ["MODEL_PATH"] = out
        import importlib
        importlib.reload(K)
        model, norm = K.load_or_train()
        check("model loaded", model is not None and isinstance(norm, dict) and len(norm) == 9)
        window = [K.extract_features({"prb_dl_pct": 92, "sinr_db": 8, "connected_ues": 700,
                                      "power_w": 850, "packet_loss_pct": 3, "dl_throughput_mbps": 1200,
                                      "cqi": 7, "bler_pct": 12, "latency_ms": 60})] * SEQ_LEN
        cls, conf = K.infer(model, norm, window)
        check("infer valid class + conf in [0,1]", cls in K.CLASSES and 0.0 <= conf <= 1.0)

        # analyse(): full window uses model path, returns action list without error
        buffers = {f"c{i}": deque([window[0]] * SEQ_LEN, maxlen=SEQ_LEN) for i in range(2)}
        cells = {"c0": {"du_id": "DU-MLS-1", "prb_dl_pct": 92, "sinr_db": 8, "connected_ues": 700,
                        "power_w": 850, "packet_loss_pct": 3, "dl_throughput_mbps": 1200,
                        "cqi": 7, "bler_pct": 12, "latency_ms": 60},
                 "c1": {"du_id": "DU-MLS-2", "prb_dl_pct": 40, "sinr_db": 16, "connected_ues": 150,
                        "power_w": 400, "packet_loss_pct": 1, "dl_throughput_mbps": 800,
                        "cqi": 11, "bler_pct": 3, "latency_ms": 20}}
        acts = K.analyse(model, norm, cells, buffers, K.SonDispatcher(write_api=FakeWrite(), http=FakeHttp()), cycle=0)
        check("analyse runs over model path", isinstance(acts, list))

print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
