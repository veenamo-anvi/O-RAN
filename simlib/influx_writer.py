"""InfluxDB connection + write helpers for simulators (connect-with-retry)."""
from __future__ import annotations

import logging
import os
import time

log = logging.getLogger("simlib.influx")

INFLUX_URL = os.environ.get("INFLUX_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN", "telecom-super-secret-auth-token-2026")
INFLUX_ORG = os.environ.get("INFLUX_ORG", "telecom")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "telecom_metrics")


def connect(retries: int = 19, delay: float = 6.0):
    """Return (client, write_api). Retries until InfluxDB is reachable."""
    from influxdb_client import InfluxDBClient
    from influxdb_client.client.write_api import SYNCHRONOUS

    last = None
    for attempt in range(1, retries + 1):
        try:
            client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=10_000)
            if client.ping():
                log.info("connected to InfluxDB at %s", INFLUX_URL)
                return client, client.write_api(write_options=SYNCHRONOUS)
        except Exception as exc:  # noqa: BLE001
            last = exc
        log.warning("InfluxDB not ready (%d/%d): %s", attempt, retries, last)
        time.sleep(delay)
    raise RuntimeError(f"InfluxDB unreachable after {retries} attempts: {last}")


def write_points(write_api, points) -> None:
    if not points:
        return
    write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=points)
