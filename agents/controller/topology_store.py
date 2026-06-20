"""Topology source-of-truth store.

The Controller is the ONLY writer of topology.json. All reads/writes funnel through
this module. Writes are atomic (.tmp -> os.replace) so DU/CU simulator pollers never
observe a partially written file. A process-level lock serialises concurrent mutations.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any

TOPOLOGY_FILE = os.environ.get("TOPOLOGY_FILE", "/config/topology.json")

_lock = threading.RLock()


def _empty() -> dict[str, Any]:
    return {"cus": {}, "dus": {}, "cells": {}}


def load() -> dict[str, Any]:
    """Read and parse topology.json. Returns an empty skeleton if the file is missing."""
    with _lock:
        if not os.path.exists(TOPOLOGY_FILE):
            return _empty()
        with open(TOPOLOGY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    data.setdefault("cus", {})
    data.setdefault("dus", {})
    data.setdefault("cells", {})
    return data


def save(topology: dict[str, Any]) -> None:
    """Atomically persist topology.json (.tmp -> rename)."""
    with _lock:
        os.makedirs(os.path.dirname(TOPOLOGY_FILE) or ".", exist_ok=True)
        tmp = f"{TOPOLOGY_FILE}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(topology, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, TOPOLOGY_FILE)


def lock() -> threading.RLock:
    return _lock


def next_free_pci(cells: dict[str, Any], start: int = 1) -> int:
    """Smallest PCI >= start not currently used by any cell."""
    used = {int(c.get("pci", 0)) for c in cells.values()}
    pci = start
    while pci in used:
        pci += 1
    return pci
