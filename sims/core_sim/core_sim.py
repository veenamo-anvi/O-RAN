"""Core simulator (AMF + SMF + UPF).

Streams core_kpi with one point per component (component tag), field sets varying by
component. Network-wide UE/session counts are estimated from the diurnal load model.

Env: TOPOLOGY_FILE, INFLUX_*, STREAM_INTERVAL_SEC, SEED.
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
log = logging.getLogger("core_sim")

INTERVAL = float(os.environ.get("STREAM_INTERVAL_SEC", "10"))


def run() -> None:
    rng = random.Random(int(os.environ["SEED"]) if os.environ.get("SEED") else None)
    client, write_api = connect()
    log.info("Core simulator started (AMF/SMF/UPF)")

    while True:
        cycle_start = time.time()
        topo = load_topology()
        cells = all_cells(topo)
        ts = datetime.now(timezone.utc)
        hour = ts.hour + ts.minute / 60.0
        weekday = ts.weekday()

        total_ues = 0
        total_dl = 0.0
        total_ul = 0.0
        for cell in cells:
            load = load_factor(hour, weekday, profile_for(cell.get("site", "")), rng)
            kpi = generate_cell_kpi(cell, load, pick_live_class(load, rng), rng)
            total_ues += int(kpi["connected_ues"])
            total_dl += float(kpi["dl_throughput_mbps"])
            total_ul += float(kpi["ul_throughput_mbps"])

        sessions = int(total_ues * rng.uniform(0.9, 1.3))
        amf = (
            Point("core_kpi").tag("component", "AMF").tag("instance_id", "amf-1")
            .field("registered_ues", float(total_ues))
            .field("active_sessions", float(sessions))
            .field("nas_msg_per_sec", round(total_ues * rng.uniform(0.05, 0.2), 1))
            .field("paging_per_sec", round(total_ues * rng.uniform(0.01, 0.05), 1))
            .field("handover_per_sec", round(rng.uniform(1, 20), 1))
            .time(ts)
        )
        smf = (
            Point("core_kpi").tag("component", "SMF").tag("instance_id", "smf-1")
            .field("active_pdu_sessions", float(sessions))
            .field("session_setup_rate", round(sessions * rng.uniform(0.02, 0.08), 1))
            .field("ip_pool_utilization_pct", round(min(99.0, sessions / 200.0 + rng.uniform(0, 5)), 1))
            .time(ts)
        )
        upf = (
            Point("core_kpi").tag("component", "UPF").tag("instance_id", "upf-1")
            .field("dl_throughput_gbps", round(total_dl / 1000.0, 3))
            .field("ul_throughput_gbps", round(total_ul / 1000.0, 3))
            .field("active_tunnels", float(sessions))
            .field("packet_drop_rate", round(rng.uniform(0, 0.5), 3))
            .time(ts)
        )

        try:
            write_points(write_api, [amf, smf, upf])
            log.info("core: registered_ues=%d sessions=%d dl=%.2fGbps", total_ues, sessions, total_dl / 1000.0)
        except Exception as exc:  # noqa: BLE001
            log.warning("write failed: %s", exc)

        time.sleep(max(0.0, INTERVAL - (time.time() - cycle_start)))


if __name__ == "__main__":
    run()
