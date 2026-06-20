"""Agent 1 — LLM Orchestrator (:8082).

Resolves an LLM backend by priority at startup, injects live network context on every
request, runs a multi-step tool-calling loop, and streams the response as text/plain.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import requests
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import backends
import tools as T

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("orchestrator")

CONTROLLER_URL = os.environ.get("CONTROLLER_URL", "http://controller:8080")

SYSTEM_PROMPT = (
    "You are the operator assistant for an O-RAN 4G/5G NSA network in Malleswaram, North "
    "Bangalore: 30 cells across 10 macro sites (3 sectors each), 3 DUs under 1 CU (CU-MLS), "
    "vendors Nokia/Ericsson/Samsung/ZTE. Cell naming is MLS_<SITE>_<SECTOR>. Deployed bands: "
    "n78 (3500), n41 (2500), B40 (2300), B3 (1800); n28 is supported but not deployed. "
    "Capacity vs demand — distinguish these clearly when asked: CONCURRENT CAPACITY is "
    "16,500 UEs (sum of per-cell max_ues: 900x10 n78 + 700x5 n41 + 300x5 B40 + 250x10 B3) = "
    "the most UEs connectable at one instant; the DESIGN BUSY-HOUR PEAK is 18,400 active UEs "
    "(46,000 effective population x 40% market share). Peak demand (18,400) intentionally "
    "exceeds concurrent capacity (16,500); the ~1,900 gap is absorbed by Erlang-C blocking "
    "(~2%) since not all busy-hour users are connected simultaneously. Do not conflate the "
    "two: 16,500 = max concurrent capacity, 18,400 = peak busy-hour demand. "
    "You have 14 tools to query and modify the live network. Confirm before destructive "
    "actions, flag overloaded cells, and summarise results as short bullet points."
)

BACKEND = backends.resolve_backend()
SESSIONS: dict[str, Any] = {}

app = FastAPI(title="O-RAN Orchestrator", version="1.0.0")


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


def build_network_context() -> str:
    try:
        net = requests.get(f"{CONTROLLER_URL}/network", timeout=10).json()
    except Exception as exc:  # noqa: BLE001
        return f"[live network context unavailable: {exc}]"
    lines = []
    for c in net.get("cells", []):
        k = c.get("kpi", {})
        lines.append(
            f"{c['cell_id']} ({c.get('area')}) -> DU={c.get('du_id')} | UEs={k.get('connected_ues', '-')}"
            f" | PRB={k.get('prb_dl_pct', '-')}% | SINR={k.get('sinr_db', '-')}dB | Power={k.get('power_w', '-')}W"
        )
    return "CURRENT LIVE NETWORK:\n" + "\n".join(lines) if lines else "CURRENT LIVE NETWORK: (no cells)"


def chat_turn(message: str, session_id: str):
    """Synchronous generator — Starlette runs it in a threadpool."""
    context = build_network_context()
    try:
        for chunk in BACKEND.turn(session_id, message, SESSIONS, SYSTEM_PROMPT, context):
            yield chunk
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "429" in msg or "quota" in msg.lower() or "ResourceExhausted" in msg:
            yield "\n\n[Error] LLM quota/rate limit reached. Try again shortly."
        else:
            yield f"\n\n[Error] {msg}"


def _normalize_history(session_id: str) -> list[dict[str, str]]:
    hist = SESSIONS.get(session_id, [])
    out = []
    for item in hist:
        if isinstance(item, dict):
            role = item.get("role", "")
            content = item.get("content", "")
            if isinstance(content, list):  # tool_result / tool_use blocks
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        out.append({"role": "assistant", "content": f"[Calling {b.get('name')}]"})
                    elif isinstance(b, dict) and b.get("type") == "tool_result":
                        out.append({"role": "tool", "content": f"[Tool result] {str(b.get('content'))[:200]}"})
                    elif isinstance(b, dict) and b.get("type") == "text":
                        out.append({"role": role, "content": b.get("text", "")})
            else:
                out.append({"role": role, "content": str(content)[:1000]})
        else:  # gemini types.Content
            role = getattr(item, "role", "model")
            text = " ".join(getattr(p, "text", "") or (f"[Calling {p.function_call.name}]" if getattr(p, "function_call", None) else "")
                            for p in getattr(item, "parts", []))
            out.append({"role": role, "content": text.strip()[:1000]})
    return out


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "model": BACKEND.model, "backend": BACKEND.name}


@app.get("/tools")
def get_tools() -> list[dict[str, str]]:
    return [{"name": t["name"], "description": t["description"]} for t in T.TOOL_SCHEMAS]


@app.post("/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    return StreamingResponse(chat_turn(req.message, req.session_id), media_type="text/plain")


@app.get("/history")
def get_history(session_id: str = Query("default")) -> dict[str, Any]:
    return {"session_id": session_id, "history": _normalize_history(session_id)}


@app.delete("/history")
def clear_history(session_id: str = Query("default")) -> dict[str, Any]:
    SESSIONS.pop(session_id, None)
    return {"status": "cleared", "session_id": session_id}
