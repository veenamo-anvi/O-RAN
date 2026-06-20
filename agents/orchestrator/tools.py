"""Tool layer — 14 tool schemas (Anthropic-style JSON) + executors.

Schemas are native Anthropic format (name/description/input_schema). The Claude CLI and
Anthropic backends use them as-is; the Gemini backend translates them via _clean_params().
TOOL_MAP[name](args) executes the tool over HTTP against the Controller / Planning / InfluxDB.
"""
from __future__ import annotations

import os
from typing import Any, Callable

import requests

import influx_tools as IT

CONTROLLER_URL = os.environ.get("CONTROLLER_URL", "http://controller:8080")
PLANNING_URL = os.environ.get("PLANNING_URL", "http://planning-api:8081")
HTTP_TIMEOUT = 30


# --------------------------------------------------------------------------- executors
def _get(url: str, params: dict | None = None) -> Any:
    r = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
    return r.json() if r.headers.get("content-type", "").startswith("application/json") else {"status_code": r.status_code, "text": r.text}


def _post(url: str, body: dict) -> Any:
    r = requests.post(url, json=body, timeout=HTTP_TIMEOUT)
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {"status_code": r.status_code, "text": r.text}


def query_network(args): return _get(f"{CONTROLLER_URL}/network")
def list_cells(args): return _get(f"{CONTROLLER_URL}/cells", {k: v for k, v in args.items() if v})
def query_cell(args): return _get(f"{CONTROLLER_URL}/cells/{args['cell_id']}")
def move_cell(args): return _post(f"{CONTROLLER_URL}/move/cell", {"cell_id": args["cell_id"], "to_du_id": args["to_du_id"]})
def move_du(args): return _post(f"{CONTROLLER_URL}/move/du", {"du_id": args["du_id"], "to_cu_id": args["to_cu_id"]})
def optimize_congestion(args):
    data = _get(f"{CONTROLLER_URL}/congestion")
    top = args.get("top_n")
    if isinstance(data, dict) and top:
        data = dict(data); data["cells"] = data.get("cells", [])[: int(top)]
    return data
def plan_network(args): return _post(f"{PLANNING_URL}/plan", args)
def plan_network_multi_period(args): return _post(f"{PLANNING_URL}/plan/multi-period", args)
def apply_plan(args): return _post(f"{PLANNING_URL}/plan/apply", {"plan_id": args["plan_id"]})
def add_cell(args): return _post(f"{CONTROLLER_URL}/cells/add", args)
def remove_cell(args):
    r = requests.delete(f"{CONTROLLER_URL}/cells/{args['cell_id']}", timeout=HTTP_TIMEOUT)
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {"status_code": r.status_code}
def get_alerts(args): return IT.get_alerts(minutes=int(args.get("minutes", 60)))
def query_ue(args): return IT.query_ue(ue_id=args.get("ue_id"), cell_id=args.get("cell_id"), minutes=int(args.get("minutes", 30)))
def get_son_status(args): return IT.get_son_status()


TOOL_MAP: dict[str, Callable[[dict], Any]] = {
    "query_network": query_network, "list_cells": list_cells, "query_cell": query_cell,
    "move_cell": move_cell, "move_du": move_du, "plan_network": plan_network,
    "plan_network_multi_period": plan_network_multi_period, "apply_plan": apply_plan,
    "get_alerts": get_alerts, "query_ue": query_ue, "get_son_status": get_son_status,
    "add_cell": add_cell, "remove_cell": remove_cell, "optimize_congestion": optimize_congestion,
}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {"name": "query_network", "description": "Full topology + live KPIs for all 30 cells.",
     "input_schema": _obj({})},
    {"name": "list_cells", "description": "Filtered cell list with live KPIs.",
     "input_schema": _obj({"area": {"type": "string"}, "du_id": {"type": "string"}, "cu_id": {"type": "string"}})},
    {"name": "query_cell", "description": "Single cell config + 30-min KPI time series.",
     "input_schema": _obj({"cell_id": {"type": "string"}}, ["cell_id"])},
    {"name": "move_cell", "description": "Reassign a cell to a different DU.",
     "input_schema": _obj({"cell_id": {"type": "string"}, "to_du_id": {"type": "string"}}, ["cell_id", "to_du_id"])},
    {"name": "move_du", "description": "Reassign a DU to a different CU.",
     "input_schema": _obj({"du_id": {"type": "string"}, "to_cu_id": {"type": "string"}}, ["du_id", "to_cu_id"])},
    {"name": "plan_network", "description": "Heuristic or MIP-optimal placement + PCI + slice planning.",
     "input_schema": _obj({"geographic_area": {"type": "string"}, "spectrum_bands": {"type": "array", "items": {"type": "string"}},
                           "deployment_budget": {"type": "number"}, "use_mip": {"type": "boolean"},
                           "sinr_min_db": {"type": "number"}, "traffic_profile": {"type": "object"}})},
    {"name": "plan_network_multi_period", "description": "Multi-period MIP (Case A phased rollout / Case B diurnal shift).",
     "input_schema": _obj({"demand_mode": {"type": "string", "enum": ["permanent", "temporary"]},
                           "spectrum_bands": {"type": "array", "items": {"type": "string"}},
                           "deployment_budget": {"type": "number"}, "sinr_min_db": {"type": "number"}})},
    {"name": "apply_plan", "description": "Push an accepted plan to the Controller as live topology.",
     "input_schema": _obj({"plan_id": {"type": "string"}}, ["plan_id"])},
    {"name": "get_alerts", "description": "Recent KPI anomaly alerts tagged by severity and type.",
     "input_schema": _obj({"minutes": {"type": "integer"}})},
    {"name": "query_ue", "description": "UE-level usage and mobility data (filter by ue_id or cell_id).",
     "input_schema": _obj({"ue_id": {"type": "string"}, "cell_id": {"type": "string"}, "minutes": {"type": "integer"}})},
    {"name": "get_son_status", "description": "SON action summary + counts by type, last 10 actions, active alert severity.",
     "input_schema": _obj({})},
    {"name": "add_cell", "description": "Deploy a new cell via chat; auto-assigns PCI if not provided.",
     "input_schema": _obj({"cell_id": {"type": "string"}, "du_id": {"type": "string"}, "area": {"type": "string"},
                           "lat": {"type": "number"}, "lon": {"type": "number"}, "generation": {"type": "string"},
                           "band": {"type": "string"}, "vendor": {"type": "string"}, "pci": {"type": "integer"}},
                          ["cell_id", "du_id"])},
    {"name": "remove_cell", "description": "Decommission a cell and remove it from DU assignment.",
     "input_schema": _obj({"cell_id": {"type": "string"}}, ["cell_id"])},
    {"name": "optimize_congestion", "description": "Ranked per-cell congestion scores (top-N); surfaces the worst cells to act on.",
     "input_schema": _obj({"top_n": {"type": "integer"}})},
]

assert len(TOOL_SCHEMAS) == 14, "expected 14 tools"
assert set(t["name"] for t in TOOL_SCHEMAS) == set(TOOL_MAP), "schema/executor mismatch"


def gemini_tools() -> list[dict[str, Any]]:
    """Translate Anthropic-style schemas to Gemini function_declarations (_clean_params)."""
    def clean(schema: dict) -> dict:
        out = {}
        for k, v in schema.items():
            if k == "default":
                continue
            if k == "enum" and not v:
                continue
            if isinstance(v, dict):
                out[k] = clean(v)
            elif isinstance(v, list):
                out[k] = [clean(i) if isinstance(i, dict) else i for i in v]
            else:
                out[k] = v
        return out

    decls = []
    for t in TOOL_SCHEMAS:
        params = clean(t["input_schema"])
        if not params.get("properties"):
            params = {"type": "object", "properties": {}}
        decls.append({"name": t["name"], "description": t["description"], "parameters": params})
    return [{"function_declarations": decls}]
