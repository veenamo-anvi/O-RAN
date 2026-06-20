"""Composite per-cell congestion scoring (read-only).

    score = 0.40*(PRB_dl/100) + 0.20*(1 - SINR/25) + 0.20*(BLER/20) + 0.20*(latency/150)
    each term clamped to [0, 1]
    level = CRITICAL >0.75 | HIGH >0.55 | MODERATE >0.35 | LOW <=0.35

Recommends; never moves cells.
"""
from __future__ import annotations

from typing import Any


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def _level(score: float) -> str:
    if score > 0.75:
        return "CRITICAL"
    if score > 0.55:
        return "HIGH"
    if score > 0.35:
        return "MODERATE"
    return "LOW"


def score_cell(kpi: dict[str, Any]) -> float:
    prb = _clamp01(float(kpi.get("prb_dl_pct", 0.0)) / 100.0)
    sinr = _clamp01(1.0 - float(kpi.get("sinr_db", 25.0)) / 25.0)
    bler = _clamp01(float(kpi.get("bler_pct", 0.0)) / 20.0)
    latency = _clamp01(float(kpi.get("latency_ms", 0.0)) / 150.0)
    return round(0.40 * prb + 0.20 * sinr + 0.20 * bler + 0.20 * latency, 4)


def rank(cells: dict[str, Any], snapshot: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    summary = {"CRITICAL": 0, "HIGH": 0, "MODERATE": 0, "LOW": 0}
    for cid, cfg in cells.items():
        kpi = snapshot.get(cid, {})
        score = score_cell(kpi)
        lvl = _level(score)
        summary[lvl] += 1
        rows.append({
            "cell_id": cid,
            "area": cfg.get("area"),
            "du_id": cfg.get("du_id"),
            "band": cfg.get("band"),
            "congestion_score": score,
            "level": lvl,
            "prb_dl_pct": kpi.get("prb_dl_pct"),
            "sinr_db": kpi.get("sinr_db"),
            "bler_pct": kpi.get("bler_pct"),
            "latency_ms": kpi.get("latency_ms"),
            "connected_ues": kpi.get("connected_ues"),
        })
    rows.sort(key=lambda r: r["congestion_score"], reverse=True)
    return {"cells": rows, "summary": summary, "total_cells": len(rows)}
