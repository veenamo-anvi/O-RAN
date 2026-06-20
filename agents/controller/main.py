"""Agent 2 — Controller (:8080).

The single control plane for the live network. Owns topology.json (only writer),
merges live KPIs from InfluxDB at query time, and exposes topology CRUD + SON routes.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

import congestion
import topology_store as store
from geo import haversine_m
from influx_io import InfluxIO

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("controller")

app = FastAPI(title="O-RAN Controller", version="1.0.0")
influx = InfluxIO()


# --------------------------------------------------------------------------- models
class MoveCell(BaseModel):
    cell_id: str
    to_du_id: str


class MoveDU(BaseModel):
    du_id: str
    to_cu_id: str


class PciReopt(BaseModel):
    cell_id: str
    du_id: Optional[str] = None


class TopologyReplace(BaseModel):
    cus: dict[str, Any]
    dus: dict[str, Any]
    cells: dict[str, Any]


class AddCell(BaseModel):
    cell_id: str
    du_id: str
    area: str = ""
    lat: float = 0.0
    lon: float = 0.0
    generation: str = "5G"
    band: str = "n78"
    vendor: str = ""
    freq_mhz: float = 0.0
    pci: int = 0
    hardware_model: str = ""
    antenna_config: str = ""
    peak_dl_mbps: float = 0.0
    tx_power_w: float = 0.0
    idle_power_w: float = 0.0
    max_ues: int = 0


# --------------------------------------------------------------------------- helpers
def _merge_kpi(cell: dict[str, Any], snapshot: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out = dict(cell)
    out["kpi"] = snapshot.get(cell["cell_id"], {})
    return out


def _du_kpi_rollup(du_id: str, cells: dict[str, Any], snapshot: dict[str, dict[str, Any]]) -> dict[str, Any]:
    members = [c for c in cells.values() if c.get("du_id") == du_id]
    ues = sum(float(snapshot.get(c["cell_id"], {}).get("connected_ues", 0) or 0) for c in members)
    prbs = [float(snapshot.get(c["cell_id"], {}).get("prb_dl_pct", 0) or 0) for c in members]
    return {
        "cell_count": len(members),
        "active_ues": int(ues),
        "avg_prb_dl_pct": round(sum(prbs) / len(prbs), 2) if prbs else 0.0,
    }


# --------------------------------------------------------------------------- read routes
@app.get("/health")
def health() -> dict[str, Any]:
    topo = store.load()
    return {
        "status": "ok",
        "service": "controller",
        "cells": len(topo["cells"]),
        "dus": len(topo["dus"]),
        "cus": len(topo["cus"]),
    }


@app.get("/topology")
def get_topology() -> dict[str, Any]:
    """Raw topology.json — no KPI merge."""
    return store.load()


@app.get("/network")
def get_network() -> dict[str, Any]:
    topo = store.load()
    snap = influx.kpi_snapshot()
    cells = [_merge_kpi(c, snap) for c in topo["cells"].values()]
    dus = []
    for du_id, du in topo["dus"].items():
        d = dict(du)
        d["kpi"] = _du_kpi_rollup(du_id, topo["cells"], snap)
        dus.append(d)
    cus = list(topo["cus"].values())
    return {"cus": cus, "dus": dus, "cells": cells, "total_cells": len(cells)}


@app.get("/cells")
def get_cells(
    area: Optional[str] = Query(None),
    du_id: Optional[str] = Query(None),
    cu_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    topo = store.load()
    snap = influx.kpi_snapshot()
    out = []
    for c in topo["cells"].values():
        if area and c.get("area") != area:
            continue
        if du_id and c.get("du_id") != du_id:
            continue
        if cu_id and c.get("cu_id") != cu_id:
            continue
        out.append(_merge_kpi(c, snap))
    return {"cells": out, "total": len(out)}


@app.get("/cells/{cell_id}")
def get_cell(cell_id: str) -> dict[str, Any]:
    topo = store.load()
    cell = topo["cells"].get(cell_id)
    if cell is None:
        raise HTTPException(status_code=404, detail=f"unknown cell_id {cell_id}")
    return {"cell": cell, "series": influx.cell_series(cell_id, minutes=30)}


@app.get("/dus")
def get_dus() -> dict[str, Any]:
    topo = store.load()
    snap = influx.kpi_snapshot()
    dus = []
    for du_id, du in topo["dus"].items():
        d = dict(du)
        d["kpi"] = _du_kpi_rollup(du_id, topo["cells"], snap)
        dus.append(d)
    return {"dus": dus, "total": len(dus)}


@app.get("/cus")
def get_cus() -> dict[str, Any]:
    topo = store.load()
    return {"cus": list(topo["cus"].values()), "total": len(topo["cus"])}


@app.get("/neighbors/{cell_id}")
def get_neighbors(cell_id: str, max_neighbors: int = Query(6, ge=1, le=30)) -> dict[str, Any]:
    topo = store.load()
    cell = topo["cells"].get(cell_id)
    if cell is None:
        raise HTTPException(status_code=404, detail=f"unknown cell_id {cell_id}")
    others = []
    for cid, c in topo["cells"].items():
        if cid == cell_id:
            continue
        dist = haversine_m(cell["lat"], cell["lon"], c["lat"], c["lon"])
        others.append({"cell_id": cid, "distance_m": round(dist, 1), "pci": c.get("pci"), "du_id": c.get("du_id")})
    others.sort(key=lambda r: r["distance_m"])
    return {"cell_id": cell_id, "neighbors": others[:max_neighbors]}


@app.get("/congestion")
def get_congestion() -> dict[str, Any]:
    topo = store.load()
    snap = influx.kpi_snapshot()
    return congestion.rank(topo["cells"], snap)


# --------------------------------------------------------------------------- write routes
@app.post("/move/cell")
def move_cell(req: MoveCell) -> dict[str, Any]:
    with store.lock():
        topo = store.load()
        cell = topo["cells"].get(req.cell_id)
        if cell is None:
            raise HTTPException(status_code=404, detail=f"unknown cell_id {req.cell_id}")
        if req.to_du_id not in topo["dus"]:
            raise HTTPException(status_code=404, detail=f"unknown du_id {req.to_du_id}")
        from_du = cell.get("du_id")
        if from_du == req.to_du_id:
            return {"status": "noop", "cell_id": req.cell_id, "du_id": from_du}
        cell["du_id"] = req.to_du_id
        cell["cu_id"] = topo["dus"][req.to_du_id].get("cu_id", cell.get("cu_id"))
        # keep DU membership lists consistent
        if from_du in topo["dus"] and req.cell_id in topo["dus"][from_du].get("cell_ids", []):
            topo["dus"][from_du]["cell_ids"].remove(req.cell_id)
        topo["dus"][req.to_du_id].setdefault("cell_ids", []).append(req.cell_id)
        store.save(topo)
    influx.write_event("CELL_MOVE", cell_id=req.cell_id, from_du=from_du, to_du=req.to_du_id)
    return {"status": "ok", "cell_id": req.cell_id, "from_du": from_du, "to_du": req.to_du_id}


@app.post("/move/du")
def move_du(req: MoveDU) -> dict[str, Any]:
    with store.lock():
        topo = store.load()
        du = topo["dus"].get(req.du_id)
        if du is None:
            raise HTTPException(status_code=404, detail=f"unknown du_id {req.du_id}")
        if req.to_cu_id not in topo["cus"]:
            raise HTTPException(status_code=404, detail=f"unknown cu_id {req.to_cu_id}")
        from_cu = du.get("cu_id")
        du["cu_id"] = req.to_cu_id
        for cid in du.get("cell_ids", []):
            if cid in topo["cells"]:
                topo["cells"][cid]["cu_id"] = req.to_cu_id
        if from_cu in topo["cus"] and req.du_id in topo["cus"][from_cu].get("du_ids", []):
            topo["cus"][from_cu]["du_ids"].remove(req.du_id)
        topo["cus"][req.to_cu_id].setdefault("du_ids", []).append(req.du_id)
        store.save(topo)
    influx.write_event("DU_MOVE", du_id=req.du_id, from_cu=from_cu, to_cu=req.to_cu_id)
    return {"status": "ok", "du_id": req.du_id, "from_cu": from_cu, "to_cu": req.to_cu_id}


@app.post("/son/pci-reopt")
def son_pci_reopt(req: PciReopt) -> dict[str, Any]:
    """Re-assign PCI for the cell and its Haversine neighbours collision/confusion-free."""
    with store.lock():
        topo = store.load()
        cells = topo["cells"]
        cell = cells.get(req.cell_id)
        if cell is None:
            raise HTTPException(status_code=404, detail=f"unknown cell_id {req.cell_id}")
        # nearest 6 neighbours define the local PCI conflict set
        neigh = sorted(
            (c for cid, c in cells.items() if cid != req.cell_id),
            key=lambda c: haversine_m(cell["lat"], cell["lon"], c["lat"], c["lon"]),
        )[:6]
        forbidden = {int(c.get("pci", 0)) for c in neigh}
        # also avoid the neighbours-of-neighbours PCIs (confusion-free)
        for n in neigh:
            for cid, c in cells.items():
                if cid == n["cell_id"]:
                    continue
                if haversine_m(n["lat"], n["lon"], c["lat"], c["lon"]) < 600:
                    forbidden.add(int(c.get("pci", 0)))
        old_pci = int(cell.get("pci", 0))
        new_pci = 1
        while new_pci in forbidden or new_pci == old_pci:
            new_pci += 1
        cell["pci"] = new_pci
        store.save(topo)
    influx.write_event("PCI_REOPT", cell_id=req.cell_id, from_pci=old_pci, to_pci=new_pci)
    return {"status": "ok", "cell_id": req.cell_id, "from_pci": old_pci, "to_pci": new_pci}


@app.post("/topology/replace")
def topology_replace(req: TopologyReplace) -> dict[str, Any]:
    if not req.cells:
        raise HTTPException(status_code=400, detail="cells must not be empty")
    # minimal structural validation: every cell's du must exist; every du's cu must exist
    for cid, c in req.cells.items():
        if c.get("du_id") not in req.dus:
            raise HTTPException(status_code=400, detail=f"cell {cid} references unknown du {c.get('du_id')}")
    for did, d in req.dus.items():
        if d.get("cu_id") not in req.cus:
            raise HTTPException(status_code=400, detail=f"du {did} references unknown cu {d.get('cu_id')}")
    topo = {"cus": req.cus, "dus": req.dus, "cells": req.cells}
    with store.lock():
        store.save(topo)
    influx.write_event("TOPOLOGY_REPLACE", cells=len(req.cells), dus=len(req.dus), cus=len(req.cus))
    return {"status": "ok", "cells": len(req.cells), "dus": len(req.dus), "cus": len(req.cus)}


@app.post("/cells/add")
def add_cell(req: AddCell) -> dict[str, Any]:
    with store.lock():
        topo = store.load()
        if req.cell_id in topo["cells"]:
            raise HTTPException(status_code=409, detail=f"cell_id {req.cell_id} already exists")
        if req.du_id not in topo["dus"]:
            raise HTTPException(status_code=404, detail=f"unknown du_id {req.du_id}")
        cell = req.model_dump()
        if int(cell.get("pci", 0)) == 0:
            cell["pci"] = store.next_free_pci(topo["cells"], start=1)
        cell["cu_id"] = topo["dus"][req.du_id].get("cu_id")
        topo["cells"][req.cell_id] = cell
        topo["dus"][req.du_id].setdefault("cell_ids", []).append(req.cell_id)
        store.save(topo)
    influx.write_event("CELL_ADD", cell_id=req.cell_id, du_id=req.du_id, pci=cell["pci"])
    return {"status": "ok", "cell_id": req.cell_id, "pci": cell["pci"], "du_id": req.du_id}


@app.delete("/cells/{cell_id}")
def remove_cell(cell_id: str) -> dict[str, Any]:
    with store.lock():
        topo = store.load()
        cell = topo["cells"].pop(cell_id, None)
        if cell is None:
            raise HTTPException(status_code=404, detail=f"unknown cell_id {cell_id}")
        du_id = cell.get("du_id")
        if du_id in topo["dus"] and cell_id in topo["dus"][du_id].get("cell_ids", []):
            topo["dus"][du_id]["cell_ids"].remove(cell_id)
        store.save(topo)
    influx.write_event("CELL_REMOVE", cell_id=cell_id, du_id=du_id)
    return {"status": "ok", "cell_id": cell_id, "du_id": du_id}
