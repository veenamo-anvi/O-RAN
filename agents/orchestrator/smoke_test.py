"""Phase-E smoke test: backend resolution, 14 tools, tool-calling loop, streaming, sessions.

Uses the Mock backend (no creds) with tool executors monkeypatched to canned data, so it
runs fully offline without the Controller/Planning/InfluxDB services.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# force Mock backend: clear any real credentials before importing main
for var in ("CLAUDE_CLI_PATH", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
    os.environ.pop(var, None)

import tools as T  # noqa: E402

# monkeypatch executors with canned responses + call recorder
CALLS = []


def _fake(name, payload):
    def f(args):
        CALLS.append((name, args))
        return payload
    return f


T.TOOL_MAP["query_network"] = _fake("query_network", {"total_cells": 30, "dus": [1, 2, 3], "cus": [1], "cells": []})
T.TOOL_MAP["optimize_congestion"] = _fake("optimize_congestion", {"cells": [{"cell_id": "MLS_RWS_01", "level": "CRITICAL", "congestion_score": 0.82}], "summary": {}})
T.TOOL_MAP["get_alerts"] = _fake("get_alerts", {"window_minutes": 60, "count": 3, "by_severity": {"CRITICAL": 1}})
T.TOOL_MAP["plan_network"] = _fake("plan_network", {"plan_id": "p1", "selected_cell_count": 30, "mip_used": False, "cost_estimate": {"total": 100}})

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

c = TestClient(main.app)
fails = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


print("backend resolution / health")
h = c.get("/health").json()
check("backend == mock", h["backend"] == "mock")
check("model reported", h["model"] == "mock-intent-router")

print("tools")
tl = c.get("/tools").json()
check("14 tools listed", len(tl) == 14)
check("optimize_congestion present", any(t["name"] == "optimize_congestion" for t in tl))

print("gemini tool translation (no 'default'/empty enum)")
gt = T.gemini_tools()
decls = gt[0]["function_declarations"]
check("14 gemini declarations", len(decls) == 14)


def _no_default(obj):
    if isinstance(obj, dict):
        if "default" in obj:
            return False
        return all(_no_default(v) for v in obj.values())
    if isinstance(obj, list):
        return all(_no_default(v) for v in obj)
    return True


check("no 'default' keys after clean", _no_default(decls))

print("chat: tool-calling loop + streaming markers")
CALLS.clear()
r = c.post("/chat", json={"message": "what is the network status?", "session_id": "s1"})
body = r.text
check("query_network called", any(n == "query_network" for n, _ in CALLS))
check("tool marker streamed", "*[calling tool: query_network...]*" in body)
check("summary streamed", "Network:" in body)
check("mock notice streamed", "Mock backend" in body)

CALLS.clear()
c.post("/chat", json={"message": "show me the worst congestion hotspots", "session_id": "s1"})
check("optimize_congestion called", any(n == "optimize_congestion" for n, _ in CALLS))

CALLS.clear()
c.post("/chat", json={"message": "generate a network plan with mip", "session_id": "s2"})
check("plan_network called with use_mip", ("plan_network", {"use_mip": True}) in CALLS)

print("history normalisation + clear")
hist = c.get("/history", params={"session_id": "s1"}).json()["history"]
check("history has entries", len(hist) > 0 and all("role" in e and "content" in e for e in hist))
check("user message recorded", any(e["role"] == "user" for e in hist))
cl = c.delete("/history", params={"session_id": "s1"}).json()
check("history cleared", cl["status"] == "cleared")
check("history empty after clear", c.get("/history", params={"session_id": "s1"}).json()["history"] == [])

print("context degrades gracefully when controller down")
ctx = main.build_network_context()
check("context unavailable string", "unavailable" in ctx or "CURRENT LIVE NETWORK" in ctx)

print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
