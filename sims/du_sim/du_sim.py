"""DU simulator (one container per DU).

Polls topology.json (read-only) for its cells, generates physics-based synthetic
telemetry on a diurnal load curve, and streams cell_kpi + du_kpi + ue_usage + ue_mobility
to InfluxDB. Reconfigures live as the Controller mutates the topology.

Env: DU_ID, TOPOLOGY_FILE, INFLUX_*, STREAM_INTERVAL_SEC (default 10), SEED (optional).
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
from simlib.topology import cells_for_du, load_topology, profile_for

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("du_sim")

DU_ID = os.environ.get("DU_ID", "DU-MLS-1")
INTERVAL = float(os.environ.get("STREAM_INTERVAL_SEC", "10"))
SLICES = ["eMBB", "URLLC", "mMTC"]


def cell_kpi_point(cell, kpi, ts) -> Point:
    p = (
        Point("cell_kpi")
        .tag("cell_id", cell["cell_id"]).tag("area", cell.get("area", ""))
        .tag("band", cell.get("band", "")).tag("pci", str(cell.get("pci", 0)))
        .tag("du_id", cell.get("du_id", "")).tag("cu_id", cell.get("cu_id", ""))
        .tag("vendor", cell.get("vendor", "")).tag("generation", cell.get("generation", ""))
        .time(ts)
    )
    for k, v in kpi.items():
        p = p.field(k, float(v))
    return p


def run() -> None:
    rng = random.Random(int(os.environ["SEED"]) if os.environ.get("SEED") else None)
    client, write_api = connect()
    log.info("DU simulator started for %s (interval=%ss)", DU_ID, INTERVAL)

    while True:
        cycle_start = time.time()
        topo = load_topology()
        cells = cells_for_du(topo, DU_ID)
        ts = datetime.now(timezone.utc)
        hour = ts.hour + ts.minute / 60.0
        weekday = ts.weekday()

        points: list[Point] = []
        active_ues = 0
        prb_vals: list[float] = []

        for cell in cells:
            load = load_factor(hour, weekday, profile_for(cell.get("site", "")), rng)
            cls = pick_live_class(load, rng)
            kpi = generate_cell_kpi(cell, load, cls, rng)
            active_ues += int(kpi["connected_ues"])
            prb_vals.append(kpi["prb_dl_pct"])
            points.append(cell_kpi_point(cell, kpi, ts))

            # sample a UE usage record for this cell
            if rng.random() < 0.6:
                points.append(
                    Point("ue_usage")
                    .tag("ue_id", f"UE-{rng.randint(0, 99999):05d}")
                    .tag("cell_id", cell["cell_id"])
                    .tag("slice_type", rng.choice(SLICES))
                    .field("dl_bytes", float(rng.randint(1_000, 50_000_000)))
                    .field("ul_bytes", float(rng.randint(1_000, 10_000_000)))
                    .field("latency_ms", float(kpi["latency_ms"]))
                    .field("jitter_ms", float(kpi["jitter_ms"]))
                    .field("packet_loss", float(kpi["packet_loss_pct"]))
                    .time(ts)
                )

        # occasional inter-cell handover event
        if len(cells) >= 2 and rng.random() < 0.4:
            src, tgt = rng.sample(cells, 2)
            points.append(
                Point("ue_mobility")
                .tag("ue_id", f"UE-{rng.randint(0, 99999):05d}")
                .tag("source_cell", src["cell_id"]).tag("target_cell", tgt["cell_id"])
                .tag("event_type", "handover")
                .field("rsrp_source", float(rng.uniform(-115, -90)))
                .field("rsrp_target", float(rng.uniform(-105, -80)))
                .field("ho_duration_ms", float(rng.uniform(20, 120)))
                .field("velocity_kmh", float(rng.uniform(0, 60)))
                .time(ts)
            )

        avg_prb = sum(prb_vals) / len(prb_vals) if prb_vals else 0.0
        points.append(
            Point("du_kpi").tag("du_id", DU_ID).tag("cu_id", cells[0].get("cu_id") if cells else "")
            .field("active_ues", float(active_ues))
            .field("cell_count", float(len(cells)))
            .field("cpu_pct", round(min(99.0, 20 + avg_prb * 0.7 + rng.uniform(-3, 3)), 1))
            .field("memory_pct", round(min(99.0, 30 + avg_prb * 0.5 + rng.uniform(-3, 3)), 1))
            .field("fronthaul_latency_us", round(rng.uniform(50, 150), 1))
            .field("processing_delay_ms", round(rng.uniform(0.5, 3.0), 2))
            .field("f1_msg_per_sec", round(active_ues * rng.uniform(0.5, 2.0), 1))
            .time(ts)
        )

        try:
            write_points(write_api, points)
            log.info("%s: wrote %d points (%d cells, %d UEs, avgPRB=%.1f)",
                     DU_ID, len(points), len(cells), active_ues, avg_prb)
        except Exception as exc:  # noqa: BLE001
            log.warning("write failed: %s", exc)

        time.sleep(max(0.0, INTERVAL - (time.time() - cycle_start)))


if __name__ == "__main__":
    run()
