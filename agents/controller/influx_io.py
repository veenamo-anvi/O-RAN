"""InfluxDB I/O for the Controller.

Two responsibilities:
  1. Read live KPIs (cell_kpi) to merge into /network, /cells, /congestion responses.
  2. Write topology_event points on every topology mutation (audit trail).

All reads degrade gracefully: if InfluxDB is unreachable the Controller still serves
topology config (with an empty `kpi` dict) instead of failing. The Controller owns
topology; KPIs are InfluxDB's domain and are joined at query time.
"""
from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger("controller.influx")

INFLUX_URL = os.environ.get("INFLUX_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN", "telecom-super-secret-auth-token-2026")
INFLUX_ORG = os.environ.get("INFLUX_ORG", "telecom")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "telecom_metrics")

# numeric cell_kpi fields the Controller surfaces in the merged `kpi` dict
KPI_FIELDS = [
    "connected_ues", "dl_throughput_mbps", "ul_throughput_mbps",
    "rsrp_dbm", "rsrq_db", "sinr_db", "power_w",
    "prb_dl_pct", "prb_ul_pct", "packet_loss_pct",
    "cqi", "mcs", "bler_pct", "latency_ms", "jitter_ms", "interference_dbm",
]

try:
    from influxdb_client import InfluxDBClient, Point
    from influxdb_client.client.write_api import SYNCHRONOUS
    _HAVE_INFLUX = True
except Exception:  # pragma: no cover - lib optional for offline unit runs
    InfluxDBClient = None  # type: ignore
    Point = None  # type: ignore
    SYNCHRONOUS = None  # type: ignore
    _HAVE_INFLUX = False


class InfluxIO:
    def __init__(self) -> None:
        self._client = None
        if _HAVE_INFLUX:
            try:
                self._client = InfluxDBClient(
                    url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=5_000
                )
            except Exception as exc:  # pragma: no cover
                log.warning("InfluxDB client init failed: %s", exc)
                self._client = None

    # ----- reads -------------------------------------------------------------
    def kpi_snapshot(self) -> dict[str, dict[str, Any]]:
        """Latest value of each cell_kpi field per cell over the last 3 minutes.

        Returns {cell_id: {field: value, ...}}. Empty dict on any failure.
        """
        if self._client is None:
            return {}
        flux = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -3m)
  |> filter(fn: (r) => r._measurement == "cell_kpi")
  |> group(columns: ["cell_id", "_field"])
  |> last()
  |> pivot(rowKey: ["cell_id"], columnKey: ["_field"], valueColumn: "_value")
'''
        try:
            tables = self._client.query_api().query(flux, org=INFLUX_ORG)
        except Exception as exc:
            log.warning("kpi_snapshot query failed: %s", exc)
            return {}
        out: dict[str, dict[str, Any]] = {}
        for table in tables:
            for rec in table.records:
                cid = rec.values.get("cell_id")
                if not cid:
                    continue
                kpi = {k: v for k, v in rec.values.items() if k in KPI_FIELDS and v is not None}
                out[cid] = kpi
        return out

    def cell_series(self, cell_id: str, minutes: int = 30) -> list[dict[str, Any]]:
        """30-minute cell_kpi time series for one cell, ascending by time."""
        if self._client is None:
            return []
        flux = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{minutes}m)
  |> filter(fn: (r) => r._measurement == "cell_kpi" and r.cell_id == "{cell_id}")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])
'''
        try:
            tables = self._client.query_api().query(flux, org=INFLUX_ORG)
        except Exception as exc:
            log.warning("cell_series query failed: %s", exc)
            return []
        series: list[dict[str, Any]] = []
        for table in tables:
            for rec in table.records:
                row: dict[str, Any] = {"time": rec.get_time().isoformat() if rec.get_time() else None}
                for k, v in rec.values.items():
                    if k in KPI_FIELDS and v is not None:
                        row[k] = v
                series.append(row)
        return series

    # ----- writes ------------------------------------------------------------
    def write_event(self, event_type: str, **fields: Any) -> None:
        """Best-effort topology_event write. Never raises into the request path."""
        if self._client is None or Point is None:
            return
        try:
            point = Point("topology_event").tag("event_type", event_type)
            for k, v in fields.items():
                if v is None:
                    continue
                point = point.field(k, str(v))
            self._client.write_api(write_options=SYNCHRONOUS).write(
                bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point
            )
        except Exception as exc:  # pragma: no cover
            log.warning("write_event(%s) failed: %s", event_type, exc)
