#!/usr/bin/env python3
"""Operator CLI client for the O-RAN Orchestrator.

Pure stdlib terminal REPL — no LLM logic, just formats requests and prints responses.

    py chat.py                               # localhost:8082, session "default"
    py chat.py --url http://host:8082        # remote orchestrator
    py chat.py --session ops-team            # named (isolated) session
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

SHORTCUTS = {
    "/status": "What is the current status of all cells, DUs, and CUs? Summarise in a table.",
    "/alerts": "Show me all recent KPI alerts from the last 60 minutes.",
    "/cells": "List all cells with their current connected UEs, PRB utilisation, and DU assignment.",
    "/plan": "Generate a network plan for Malleswaram with default parameters and show me a summary.",
    "/son": "Show me the recent SON autonomous actions and their outcomes.",
    "/ue": "Show me UE usage and mobility events from the last 30 minutes.",
}


def _get(url: str):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())


def _delete(url: str):
    req = urllib.request.Request(url, method="DELETE")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _chat(url: str, message: str, session_id: str) -> str:
    body = json.dumps({"message": message, "session_id": session_id}).encode()
    req = urllib.request.Request(url + "/chat", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read().decode()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8082")
    ap.add_argument("--session", default="default")
    args = ap.parse_args()
    url, session = args.url.rstrip("/"), args.session

    try:
        h = _get(url + "/health")
        print(f"Connected to {url} | model={h.get('model')} backend={h.get('backend')} | session={session}")
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] orchestrator not reachable at {url}: {exc} (continuing)")

    print("Type a command, a shortcut (/status /alerts /cells /plan /son /ue), or 'quit'.")
    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if not line:
            continue
        if line in ("quit", "exit", "q"):
            break
        if line == "/history":
            for t in _get(f"{url}/history?session_id={session}").get("history", []):
                print(f"  [{t['role']}] {t['content'][:200]}")
            continue
        if line == "/clear":
            print(_delete(f"{url}/history?session_id={session}")); continue
        if line == "/tools":
            for t in _get(url + "/tools"):
                print(f"  {t['name']}: {t['description']}")
            continue
        message = SHORTCUTS.get(line, line)
        try:
            print(_chat(url, message, session))
        except urllib.error.URLError as exc:
            print(f"[error] {exc}")


if __name__ == "__main__":
    main()
