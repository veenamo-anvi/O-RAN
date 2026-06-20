#!/usr/bin/env python3
"""Generate the 5 provisioned Grafana dashboards (valid JSON, Flux targets)."""
import json
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "provisioning", "dashboards")
DS = {"type": "influxdb", "uid": "influxdb"}
BUCKET = "telecom_metrics"


def flux(measurement, field, fn="mean", extra=""):
    return (f'from(bucket: "{BUCKET}")\n'
            f'  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
            f'  |> filter(fn: (r) => r._measurement == "{measurement}" and r._field == "{field}"){extra}\n'
            f'  |> aggregateWindow(every: v.windowPeriod, fn: {fn}, createEmpty: false)')


def target(measurement, field, fn="mean", extra="", ref="A"):
    return {"refId": ref, "datasource": DS, "query": flux(measurement, field, fn, extra)}


def panel(pid, title, ptype, x, y, w, h, targets, unit="short"):
    return {
        "id": pid, "title": title, "type": ptype,
        "datasource": DS, "targets": targets,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
        "options": {},
    }


def dashboard(uid, title, panels, templating=None):
    return {
        "uid": uid, "title": title, "schemaVersion": 39, "version": 1,
        "editable": True, "refresh": "30s",
        "time": {"from": "now-1h", "to": "now"},
        "templating": {"list": templating or []},
        "panels": panels,
    }


def write(name, dash):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(dash, f, indent=2)
    print("wrote", name)


# 1. Network Overview
write("network_overview.json", dashboard("oran-net-ov", "Network Overview", [
    panel(1, "Total Connected UEs", "stat", 0, 0, 6, 4, [target("cell_kpi", "connected_ues", "sum")]),
    panel(2, "Avg DL Throughput", "stat", 6, 0, 6, 4, [target("cell_kpi", "dl_throughput_mbps")], "Mbps"),
    panel(3, "Avg SINR", "stat", 12, 0, 6, 4, [target("cell_kpi", "sinr_db")], "dB"),
    panel(4, "Total Power", "stat", 18, 0, 6, 4, [target("cell_kpi", "power_w", "sum")], "watt"),
    panel(5, "Connected UEs", "timeseries", 0, 4, 12, 8, [target("cell_kpi", "connected_ues")]),
    panel(6, "PRB DL %", "timeseries", 12, 4, 12, 8, [target("cell_kpi", "prb_dl_pct")], "percent"),
    panel(7, "SINR (dB)", "timeseries", 0, 12, 12, 8, [target("cell_kpi", "sinr_db")], "dB"),
    panel(8, "Power (W)", "timeseries", 12, 12, 12, 8, [target("cell_kpi", "power_w")], "watt"),
]))

# 2. Cell KPI (with generation template var)
gen_var = {"name": "generation", "type": "custom", "label": "Generation",
           "query": "5G,4G", "current": {"text": "5G", "value": "5G"},
           "options": [{"text": "5G", "value": "5G", "selected": True}, {"text": "4G", "value": "4G", "selected": False}]}
gfilter = ' |> filter(fn: (r) => r.generation == "${generation}")'
write("cell_kpi.json", dashboard("oran-cell-kpi", "Cell KPI", [
    panel(1, "PRB DL %", "timeseries", 0, 0, 12, 7, [target("cell_kpi", "prb_dl_pct", "mean", gfilter)], "percent"),
    panel(2, "SINR", "timeseries", 12, 0, 12, 7, [target("cell_kpi", "sinr_db", "mean", gfilter)], "dB"),
    panel(3, "RSRP", "timeseries", 0, 7, 12, 7, [target("cell_kpi", "rsrp_dbm", "mean", gfilter)], "dBm"),
    panel(4, "DL Throughput", "timeseries", 12, 7, 12, 7, [target("cell_kpi", "dl_throughput_mbps", "mean", gfilter)], "Mbps"),
    panel(5, "Power", "timeseries", 0, 14, 8, 7, [target("cell_kpi", "power_w", "mean", gfilter)], "watt"),
    panel(6, "CQI", "timeseries", 8, 14, 8, 7, [target("cell_kpi", "cqi", "mean", gfilter)]),
    panel(7, "BLER % + Latency", "timeseries", 16, 14, 8, 7,
          [target("cell_kpi", "bler_pct", "mean", gfilter, "A"), target("cell_kpi", "latency_ms", "mean", gfilter, "B")]),
], [gen_var]))

# 3. UE Analytics
write("ue_analytics.json", dashboard("oran-ue", "UE Analytics", [
    panel(1, "UE Slice Distribution", "piechart", 0, 0, 8, 8,
          [{"refId": "A", "datasource": DS,
            "query": f'from(bucket: "{BUCKET}") |> range(start: v.timeRangeStart) '
                     f'|> filter(fn: (r) => r._measurement == "ue_usage" and r._field == "dl_bytes") '
                     f'|> group(columns: ["slice_type"]) |> count()'}]),
    panel(2, "Latency by Slice", "timeseries", 8, 0, 16, 8, [target("ue_usage", "latency_ms")], "ms"),
    panel(3, "Jitter by Slice", "timeseries", 0, 8, 12, 7, [target("ue_usage", "jitter_ms")], "ms"),
    panel(4, "HO Duration", "timeseries", 12, 8, 12, 7, [target("ue_mobility", "ho_duration_ms")], "ms"),
]))

# 4. SON Alerts
write("son_alerts.json", dashboard("oran-son", "SON Alerts", [
    panel(1, "Alerts by Severity", "timeseries", 0, 0, 12, 7,
          [{"refId": "A", "datasource": DS,
            "query": f'from(bucket: "{BUCKET}") |> range(start: v.timeRangeStart) '
                     f'|> filter(fn: (r) => r._measurement == "alerts" and r._field == "metric_value") '
                     f'|> group(columns: ["severity"]) |> aggregateWindow(every: v.windowPeriod, fn: count, createEmpty: false)'}]),
    panel(2, "SON Actions by Type", "timeseries", 12, 0, 12, 7,
          [{"refId": "A", "datasource": DS,
            "query": f'from(bucket: "{BUCKET}") |> range(start: v.timeRangeStart) '
                     f'|> filter(fn: (r) => r._measurement == "son_actions" and r._field == "confidence") '
                     f'|> group(columns: ["action_type"]) |> aggregateWindow(every: v.windowPeriod, fn: count, createEmpty: false)'}]),
    panel(3, "AI Confidence", "timeseries", 0, 7, 12, 7, [target("alerts", "ai_confidence")]),
    panel(4, "SON Action Log", "table", 12, 7, 12, 7,
          [{"refId": "A", "datasource": DS,
            "query": f'from(bucket: "{BUCKET}") |> range(start: v.timeRangeStart) '
                     f'|> filter(fn: (r) => r._measurement == "son_actions" and r._field == "message") '
                     f'|> keep(columns: ["_time", "action_type", "cell_id", "_value"]) |> sort(columns: ["_time"], desc: true) |> limit(n: 20)'}]),
]))

# 5. DU/CU Performance
write("du_cu_performance.json", dashboard("oran-ducu", "DU/CU Performance", [
    panel(1, "DU CPU %", "timeseries", 0, 0, 12, 7, [target("du_kpi", "cpu_pct")], "percent"),
    panel(2, "DU Memory %", "timeseries", 12, 0, 12, 7, [target("du_kpi", "memory_pct")], "percent"),
    panel(3, "DU Fronthaul Latency", "timeseries", 0, 7, 12, 7, [target("du_kpi", "fronthaul_latency_us")], "µs"),
    panel(4, "DU F1 msg/s", "timeseries", 12, 7, 12, 7, [target("du_kpi", "f1_msg_per_sec")]),
    panel(5, "CU PDCP DL Gbps", "timeseries", 0, 14, 8, 7, [target("cu_kpi", "pdcp_dl_gbps")], "Gbits"),
    panel(6, "Core Registered UEs", "timeseries", 8, 14, 8, 7, [target("core_kpi", "registered_ues")]),
    panel(7, "UPF DL Gbps", "timeseries", 16, 14, 8, 7, [target("core_kpi", "dl_throughput_gbps")], "Gbits"),
]))

print("done")
