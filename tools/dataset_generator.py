"""Standalone synthetic dataset generator for BiLSTM training.

Produces one labelled row per (day, hour, cell). Defaults: 70 days x 24 h x 30 cells =
50,400 rows, 32 columns, class mix 70% NORMAL / 15% OVERLOAD / 8% UNDERLOAD /
5% SINR_LOW / 2% POWER_WASTE.

Usage:
    python tools/dataset_generator.py --days 70 --seed 42 --out dataset.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

# allow running from anywhere — make repo root importable for `simlib`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simlib.load_model import load_factor  # noqa: E402
from simlib.physics import generate_cell_kpi, pick_dataset_class  # noqa: E402
from simlib.topology import load_topology, profile_for  # noqa: E402

META_COLS = [
    "timestamp", "day", "hour", "weekday",
    "cell_id", "site", "area", "du_id", "cu_id",
    "vendor", "generation", "band", "freq_mhz", "pci", "max_ues",
]
KPI_COLS = [
    "connected_ues", "prb_dl_pct", "prb_ul_pct", "sinr_db", "rsrp_dbm", "rsrq_db",
    "dl_throughput_mbps", "ul_throughput_mbps", "power_w", "packet_loss_pct",
    "cqi", "mcs", "bler_pct", "latency_ms", "jitter_ms", "interference_dbm",
]
COLUMNS = META_COLS + KPI_COLS + ["label"]  # 15 + 16 + 1 = 32


def default_topology_path() -> str:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "dev-env", "config", "topology.json")


def generate(days: int, seed: int, out: str, topology_path: str) -> None:
    rng = random.Random(seed)
    topo = load_topology(topology_path)
    cells = list(topo.get("cells", {}).values())
    if not cells:
        raise SystemExit(f"no cells found in {topology_path} — run dev-env/gen_topology.py first")

    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
    labels: Counter = Counter()
    rows = 0

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for day in range(days):
            date = start + timedelta(days=day)
            weekday = date.weekday()
            for hour in range(24):
                ts = date + timedelta(hours=hour)
                for cell in cells:
                    load = load_factor(hour, weekday, profile_for(cell.get("site", "")), rng)
                    cls = pick_dataset_class(rng)
                    kpi = generate_cell_kpi(cell, load, cls, rng)
                    labels[cls] += 1
                    rows += 1
                    meta = [
                        ts.isoformat(), day, hour, weekday,
                        cell["cell_id"], cell.get("site", ""), cell.get("area", ""),
                        cell.get("du_id", ""), cell.get("cu_id", ""),
                        cell.get("vendor", ""), cell.get("generation", ""), cell.get("band", ""),
                        cell.get("freq_mhz", ""), cell.get("pci", ""), cell.get("max_ues", ""),
                    ]
                    writer.writerow(meta + [kpi[c] for c in KPI_COLS] + [cls])

    print(f"wrote {out}: {rows} rows, {len(COLUMNS)} columns")
    print("label distribution:")
    for cls in ["NORMAL", "OVERLOAD", "UNDERLOAD", "SINR_LOW", "POWER_WASTE"]:
        n = labels[cls]
        print(f"  {cls:12s} {n:7d}  ({100 * n / rows:.1f}%)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic cell-KPI training dataset")
    ap.add_argument("--days", type=int, default=70)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="dataset.csv")
    ap.add_argument("--topology", default=default_topology_path())
    args = ap.parse_args()
    generate(args.days, args.seed, args.out, args.topology)


if __name__ == "__main__":
    main()
