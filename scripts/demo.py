#!/usr/bin/env python3
"""Demo: drive the Malleswaram network from scratch via the orchestrator chat API.

Assumes the stack is running (`docker compose up`). Sends a scripted sequence of operator
messages and prints the streamed responses.

    python scripts/demo.py [--url http://localhost:8082]
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request

STEPS = [
    ("Network status", "What is the current status of all cells, DUs, and CUs? Summarise."),
    ("Worst congestion", "Show me the worst congestion hotspots."),
    ("Recent alerts", "Show me all recent KPI alerts from the last 60 minutes."),
    ("SON actions", "Show me the recent SON autonomous actions and their outcomes."),
    ("UE activity", "Show me UE usage and mobility events from the last 30 minutes."),
    ("Plan (MIP)", "Generate an MIP-optimal network plan for Malleswaram and summarise it."),
    ("Multi-period plan", "Generate a multi-period plan with diurnal demand shift."),
]


def chat(url: str, message: str, session: str) -> str:
    body = json.dumps({"message": message, "session_id": session}).encode()
    req = urllib.request.Request(url + "/chat", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read().decode()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8082")
    args = ap.parse_args()
    url = args.url.rstrip("/")

    try:
        h = json.loads(urllib.request.urlopen(url + "/health", timeout=10).read().decode())
        print(f"== Orchestrator: model={h.get('model')} backend={h.get('backend')} ==")
    except Exception as exc:  # noqa: BLE001
        print(f"[fatal] orchestrator not reachable at {url}: {exc}")
        return

    for i, (title, msg) in enumerate(STEPS, 1):
        print(f"\n{'=' * 60}\n[{i}/{len(STEPS)}] {title}\n  > {msg}\n{'-' * 60}")
        try:
            print(chat(url, msg, session="demo"))
        except Exception as exc:  # noqa: BLE001
            print(f"[error] {exc}")
        time.sleep(1)

    print(f"\n{'=' * 60}\nDemo complete. Open the live map at http://localhost:8083 "
          f"and Grafana at http://localhost:3000.")


if __name__ == "__main__":
    main()
