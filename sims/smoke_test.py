"""Phase-B smoke test: physics class templates, sim imports, dataset generation.

No InfluxDB required — validates the synthetic-telemetry logic offline.
"""
import importlib
import os
import random
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from simlib.physics import CLASSES, generate_cell_kpi
from simlib.topology import load_topology

fails = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


REQUIRED_FIELDS = {
    "connected_ues", "prb_dl_pct", "prb_ul_pct", "sinr_db", "rsrp_dbm", "rsrq_db",
    "dl_throughput_mbps", "ul_throughput_mbps", "power_w", "packet_loss_pct",
    "cqi", "mcs", "bler_pct", "latency_ms", "jitter_ms", "interference_dbm",
}

# representative 5G n78 cell (high power so POWER_WASTE can exceed 500 W)
CELL_5G = {"max_ues": 900, "peak_dl_mbps": 3800, "tx_power_w": 1000, "idle_power_w": 300,
           "generation": "5G", "site": "RWS", "band": "n78"}

print("physics: field completeness")
rng = random.Random(1)
sample = generate_cell_kpi(CELL_5G, 0.5, "NORMAL", rng)
check("all 16 cell_kpi fields present", set(sample) == REQUIRED_FIELDS)

print("physics: class templates honour KPI-agent thresholds")
rng = random.Random(7)
agg = {c: [] for c in CLASSES}
for _ in range(400):
    for cls in CLASSES:
        agg[cls].append(generate_cell_kpi(CELL_5G, 0.5, cls, rng))

check("OVERLOAD prb_dl > 85", all(s["prb_dl_pct"] > 85 for s in agg["OVERLOAD"]))
check("UNDERLOAD prb_dl < 20", all(s["prb_dl_pct"] < 20 for s in agg["UNDERLOAD"]))
check("SINR_LOW sinr < 5", all(s["sinr_db"] < 5 for s in agg["SINR_LOW"]))
check("POWER_WASTE power > 500 & ues < 15",
      all(s["power_w"] > 500 and s["connected_ues"] < 15 for s in agg["POWER_WASTE"]))
check("NORMAL prb in (0,85)", all(0 <= s["prb_dl_pct"] <= 85 for s in agg["NORMAL"]))

print("sim modules import cleanly")
for mod in ("sims.du_sim.du_sim", "sims.cu_sim.cu_sim", "sims.core_sim.core_sim"):
    try:
        importlib.import_module(mod)
        check(f"import {mod}", True)
    except Exception as exc:  # noqa: BLE001
        check(f"import {mod} ({exc})", False)

print("topology present")
topo = load_topology(os.path.join(ROOT, "dev-env", "config", "topology.json"))
check("30 cells in topology", len(topo.get("cells", {})) == 30)

print("dataset_generator: 2-day run")
with tempfile.TemporaryDirectory() as td:
    out = os.path.join(td, "ds.csv")
    res = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "dataset_generator.py"),
         "--days", "2", "--seed", "42", "--out", out],
        capture_output=True, text=True,
    )
    print(res.stdout.strip())
    if res.returncode != 0:
        print(res.stderr.strip())
    with open(out, encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split(",")
        data = [ln for ln in f.read().splitlines() if ln]
    check("32 columns", len(header) == 32)
    check("1440 rows (2x24x30)", len(data) == 1440)
    labels = [ln.split(",")[-1] for ln in data]
    check("5 label classes", set(labels) == set(CLASSES))
    normal_frac = labels.count("NORMAL") / len(labels)
    check(f"NORMAL ~70% (got {normal_frac:.0%})", 0.60 <= normal_frac <= 0.80)

print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
