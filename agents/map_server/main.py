"""Agent 5 — Map Server (:8083).

Serves the Leaflet map and proxies all chat/history/tools traffic to the Orchestrator.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import requests
from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from coverage import radius_for_cell

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("map_server")

CONTROLLER_URL = os.environ.get("CONTROLLER_URL", "http://controller:8080")
ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8082")
HERE = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="O-RAN Map Server", version="1.0.0")


def _orch_unreachable(exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=503, content={"error": f"orchestrator unreachable: {exc}"})


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "map_server"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(HERE, "static", "index.html"))


@app.get("/api/cells")
def api_cells() -> Any:
    try:
        net = requests.get(f"{CONTROLLER_URL}/network", timeout=10).json()
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"error": f"controller unreachable: {exc}"})
    cells = []
    for c in net.get("cells", []):
        cells.append({
            "id": c["cell_id"], "area": c.get("area"), "lat": c.get("lat"), "lon": c.get("lon"),
            "vendor": c.get("vendor"), "hardware_model": c.get("hardware_model"),
            "generation": c.get("generation"), "band": c.get("band"), "pci": c.get("pci"),
            "du_id": c.get("du_id"), "cu_id": c.get("cu_id"),
            "coverage_radius_m": radius_for_cell(c), "kpi": c.get("kpi", {}),
        })
    return {"cells": cells, "total": len(cells)}


@app.post("/api/chat")
async def api_chat(request: Request) -> Any:
    body = await request.body()
    try:
        upstream = requests.post(f"{ORCHESTRATOR_URL}/chat", data=body,
                                 headers={"Content-Type": "application/json"}, stream=True, timeout=120)
    except Exception as exc:  # noqa: BLE001
        return _orch_unreachable(exc)
    return StreamingResponse(upstream.iter_content(chunk_size=None), media_type="text/plain")


@app.get("/api/history")
def api_history(session_id: str = Query("default")) -> Any:
    try:
        return requests.get(f"{ORCHESTRATOR_URL}/history", params={"session_id": session_id}, timeout=15).json()
    except Exception as exc:  # noqa: BLE001
        return _orch_unreachable(exc)


@app.delete("/api/history")
def api_history_clear(session_id: str = Query("default")) -> Any:
    try:
        return requests.delete(f"{ORCHESTRATOR_URL}/history", params={"session_id": session_id}, timeout=15).json()
    except Exception as exc:  # noqa: BLE001
        return _orch_unreachable(exc)


@app.get("/api/tools")
def api_tools() -> Any:
    try:
        return requests.get(f"{ORCHESTRATOR_URL}/tools", timeout=15).json()
    except Exception as exc:  # noqa: BLE001
        return _orch_unreachable(exc)


@app.get("/api/orch-health")
def api_orch_health() -> Any:
    try:
        return requests.get(f"{ORCHESTRATOR_URL}/health", timeout=10).json()
    except Exception as exc:  # noqa: BLE001
        return _orch_unreachable(exc)
