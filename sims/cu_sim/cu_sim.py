"""CU simulator (CU-MLS).

Aggregates RRC/PDCP-level KPIs across all DUs/cells under the CU and streams cu_kpi.
Estimates connected UEs from the same diurnal load model the DUs use.

Env: CU_ID (default CU-MLS), TOPOLOGY_FILE, INFLUX_*, STREAM_INTERVAL_SEC, SEED.
"""
from __future__ import annotations

import logging
import os
import random
import time
from datetime import datetime, timezone

from influxdb_client import Point

from simlib.influx_writer import connect, write_points
from simlib.load_model import load_factor
from simlib.physics import generate_cell_kpi, pick_live_class
from simlib.topology import all_cells, load_topology, profile_for

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("cu_sim")

CU_ID = os.environ.get("CU_ID", "CU-MLS")
INTERVAL = float(os.environ.get("STREAM_INTERVAL_SEC", "10"))


def run() -> None:
    rng = random.Random(int(os.environ["SEED"]) if os.environ.get("SEED") else None)
    client, write_api = connect()
    log.info("CU simulator started for %s", CU_ID)

    while True:
        cycle_start = time.time()
        topo = load_topology()
        cells = [c for c in all_cells(topo) if c.get("cu_id") == CU_ID]
        dus = {c.get("du_id") for c in cells}
        ts = datetime.now(timezone.utc)
        hour = ts.hour + ts.minute / 60.0
        weekday = ts.weekday()

        total_ues = 0
        pdcp_dl = 0.0
        pdcp_ul = 0.0
        for cell in cells:
            load = load_factor(hour, weekday, profile_for(cell.get("site", "")), rng)
            kpi = generate_cell_kpi(cell, load, pick_live_class(load, rng), rng)
            total_ues += int(kpi["connected_ues"])
            pdcp_dl += float(kpi["dl_throughput_mbps"])
            pdcp_ul += float(kpi["ul_throughput_mbps"])

        rrc_connected = total_ues
        rrc_idle = int(total_ues * rng.uniform(0.15, 0.4))
        point = (
            Point("cu_kpi").tag("cu_id", CU_ID)
            .field("du_count", float(len(dus)))
            .field("rrc_connected", float(rrc_connected))
            .field("rrc_idle", float(rrc_idle))
            .field("rrc_setup_rate", round(rrc_connected * rng.uniform(0.02, 0.08), 1))
            .field("inter_du_ho_rate", round(rng.uniform(0.5, 8.0), 2))
            .field("pdcp_dl_gbps", round(pdcp_dl / 1000.0, 3))
            .field("pdcp_ul_gbps", round(pdcp_ul / 1000.0, 3))
            .field("f1_latency_ms", round(rng.uniform(0.1, 1.5), 2))
            .field("n2_latency_ms", round(rng.uniform(1, 8), 2))
            .field("n3_latency_ms", round(rng.uniform(1, 6), 2))
            .field("e1_latency_ms", round(rng.uniform(0.1, 2), 2))
            .field("cpu_pct", round(min(99.0, 25 + rrc_connected / max(1, len(cells)) * 0.02 + rng.uniform(-3, 3)), 1))
            .field("memory_pct", round(rng.uniform(35, 75), 1))
            .time(ts)
        )

        try:
            write_points(write_api, [point])
            log.info("%s: rrc_connected=%d pdcp_dl=%.2fGbps dus=%d",
                     CU_ID, rrc_connected, pdcp_dl / 1000.0, len(dus))
        except Exception as exc:  # noqa: BLE001
            log.warning("write failed: %s", exc)

        time.sleep(max(0.0, INTERVAL - (time.time() - cycle_start)))


if __name__ == "__main__":
    run()
