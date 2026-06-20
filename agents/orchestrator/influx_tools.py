"""Direct InfluxDB Flux queries for the get_alerts / query_ue / get_son_status tools.

Degrade gracefully: return an empty/structured payload (never raise) if InfluxDB is down,
so the LLM gets a usable answer instead of a tool error.
"""
from __future__ import annotations

import logging
import os
from collections import Counter
from typing import Any, Optional

log = logging.getLogger("orchestrator.influx")

INFLUX_URL = os.environ.get("INFLUX_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN", "telecom-super-secret-auth-token-2026")
INFLUX_ORG = os.environ.get("INFLUX_ORG", "telecom")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "telecom_metrics")

try:
    from influxdb_client import InfluxDBClient
    _client: Optional[Any] = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=8_000)
except Exception:  # noqa: BLE001
    _client = None


def _query(flux: str):
    if _client is None:
        return []
    try:
        return _client.query_api().query(flux, org=INFLUX_ORG)
    except Exception as exc:  # noqa: BLE001
        log.warning("flux query failed: %s", exc)
        return []


def _records(measurement: str, minutes: int, extra_filter: str = ""):
    flux = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{minutes}m)
  |> filter(fn: (r) => r._measurement == "{measurement}"){extra_filter}
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: true)
'''
    rows = []
    for table in _query(flux):
        for rec in table.records:
            row = {k: v for k, v in rec.values.items() if not k.startswith("_") or k == "_time"}
            row["time"] = rec.get_time().isoformat() if rec.get_time() else None
            row.pop("_time", None)
            rows.append(row)
    return rows


def get_alerts(minutes: int = 60) -> dict[str, Any]:
    rows = _records("alerts", minutes)
    by_sev = Counter(r.get("severity") for r in rows)
    return {"window_minutes": minutes, "count": len(rows),
            "by_severity": dict(by_sev), "alerts": rows[:50]}


def query_ue(ue_id: Optional[str] = None, cell_id: Optional[str] = None, minutes: int = 30) -> dict[str, Any]:
    filt = ""
    if ue_id:
        filt = f' |> filter(fn: (r) => r.ue_id == "{ue_id}")'
    elif cell_id:
        filt = f' |> filter(fn: (r) => r.cell_id == "{cell_id}")'
    usage = _records("ue_usage", minutes, filt)
    mob_filt = ""
    if ue_id:
        mob_filt = f' |> filter(fn: (r) => r.ue_id == "{ue_id}")'
    mobility = _records("ue_mobility", minutes, mob_filt)
    return {"window_minutes": minutes, "usage": usage[:50], "mobility": mobility[:50],
            "usage_count": len(usage), "mobility_count": len(mobility)}


def get_son_status() -> dict[str, Any]:
    actions = _records("son_actions", 120)
    by_type = Counter(r.get("action_type") for r in actions)
    alerts = _records("alerts", 60)
    sev = Counter(a.get("severity") for a in alerts)
    active_sev = "CRITICAL" if sev.get("CRITICAL") else ("WARNING" if sev.get("WARNING") else "INFO")
    return {"total_actions": len(actions), "counts_by_type": dict(by_type),
            "last_10_actions": actions[:10], "active_alert_severity": active_sev}
