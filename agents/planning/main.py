"""Agent 3 — Planning Engine (:8081)."""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import candidates as C
import demand as D
import pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("planning")

CONTROLLER_URL = os.environ.get("CONTROLLER_URL", "http://controller:8080")

app = FastAPI(title="O-RAN Planning Engine", version="1.0.0")


class PlanRequest(BaseModel):
    geographic_area: str = "Malleswaram, North Bangalore"
    expected_user_density: Optional[float] = None
    traffic_profile: Optional[dict[str, float]] = None
    spectrum_bands: list[str] = Field(default_factory=lambda: list(C.DEFAULT_BANDS))
    latency_constraints: Optional[dict[str, float]] = None
    compute_resources: Optional[dict[str, Any]] = None
    deployment_budget: Optional[float] = None
    use_mip: bool = False
    sinr_min_db: float = 10.0
    mip_time_limit_sec: int = 120


class MultiPeriodRequest(BaseModel):
    demand_mode: str = "permanent"  # "permanent" | "temporary"
    time_periods: Optional[list[list[str]]] = None
    traffic_profile: Optional[dict[str, float]] = None
    spectrum_bands: list[str] = Field(default_factory=lambda: list(C.DEFAULT_BANDS))
    deployment_budget: Optional[float] = None
    sinr_min_db: float = 10.0
    mip_time_limit_sec: int = 120


class ApplyRequest(BaseModel):
    plan_id: str


def _strip_internal(plan: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in plan.items() if not k.startswith("_")}


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "planning",
            "candidate_sites": len(C.CANDIDATE_SITES), "demand_clusters": len(D.DEMAND_CLUSTERS)}


@app.get("/candidates")
def get_candidates() -> dict[str, Any]:
    meta = C.site_meta()
    return {"sites": [{"site": s, **meta[s]} for s in meta], "total": len(meta)}


@app.get("/demand-clusters")
def get_demand_clusters() -> dict[str, Any]:
    return {"clusters": D.clusters(), "period_profiles": D.PERIOD_PROFILES, "total": len(D.DEMAND_CLUSTERS)}


@app.post("/plan")
def post_plan(req: PlanRequest) -> dict[str, Any]:
    plan = pipeline.generate_plan(req.model_dump())
    return _strip_internal(plan)


@app.post("/plan/multi-period")
def post_multi_period(req: MultiPeriodRequest) -> dict[str, Any]:
    plan = pipeline.generate_multi_period(req.model_dump())
    return _strip_internal(plan)


@app.get("/plan/{plan_id}")
def get_plan(plan_id: str) -> dict[str, Any]:
    plan = pipeline.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"unknown plan_id {plan_id}")
    return _strip_internal(plan)


@app.post("/plan/apply")
def post_apply(req: ApplyRequest) -> dict[str, Any]:
    plan = pipeline.get_plan(req.plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"unknown plan_id {req.plan_id}")
    topo = plan["_topology"]
    try:
        resp = requests.post(f"{CONTROLLER_URL}/topology/replace", json=topo, timeout=15)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"controller unreachable: {exc}")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=f"controller rejected plan: {resp.text}")
    return {"status": "applied", "plan_id": req.plan_id, "controller": resp.json()}
