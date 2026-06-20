"""Read-only topology polling for simulators.

Simulators NEVER write topology.json — they poll it (the Controller is the only writer)
and reconfigure live. This module loads the file and infers each site's traffic profile.
"""
from __future__ import annotations

import json
import os
from typing import Any

TOPOLOGY_FILE = os.environ.get("TOPOLOGY_FILE", "/config/topology.json")

# high-traffic (transit / commercial) sites vs residential — drives the diurnal curve
HIGH_TRAFFIC_SITES = {"RWS", "18C", "SNK", "SPG", "10C"}


def profile_for(site: str) -> str:
    return "high" if site in HIGH_TRAFFIC_SITES else "res"


def load_topology(path: str | None = None) -> dict[str, Any]:
    p = path or TOPOLOGY_FILE
    if not os.path.exists(p):
        return {"cus": {}, "dus": {}, "cells": {}}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def cells_for_du(topology: dict[str, Any], du_id: str) -> list[dict[str, Any]]:
    return [c for c in topology.get("cells", {}).values() if c.get("du_id") == du_id]


def all_cells(topology: dict[str, Any]) -> list[dict[str, Any]]:
    return list(topology.get("cells", {}).values())
