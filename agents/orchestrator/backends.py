"""LLM backends, resolved at startup by fixed priority:
   1 Claude CLI  2 Anthropic API  3 Gemini  4 Mock.

Each backend exposes:  name, model, turn(session_id, message, sessions, system, context)
-> a generator of text chunks. The tool-calling loop yields `*[calling tool: name...]*`
markers before each execution and JSON-sanitises results before feeding them back.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from typing import Any, Iterator

import tools as T

log = logging.getLogger("orchestrator.backend")

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL_NAME", "sonnet")

# The Claude CLI accepts short aliases (sonnet/haiku/opus); the direct Anthropic Messages API
# requires concrete model ids. Resolve aliases for the API backend so /health reports the
# model actually used.
ANTHROPIC_ALIASES = {
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5-20251001",
    "opus": "claude-opus-4-8",
}


def _exec_tool(name: str, args: dict) -> tuple[str, Any]:
    try:
        result = T.TOOL_MAP[name](args)
        return json.dumps(result, default=str), result
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)}), {"error": str(exc)}


# =========================================================================== Mock
class MockBackend:
    name = "mock"

    def __init__(self) -> None:
        self.model = "mock-intent-router"

    def _route(self, msg: str) -> list[tuple[str, dict]]:
        m = msg.lower()
        calls: list[tuple[str, dict]] = []

        mv = re.search(r"move cell\s+(\S+)\s+to\s+(\S+)", m)
        if mv:
            calls.append(("move_cell", {"cell_id": mv.group(1).upper(), "to_du_id": mv.group(2).upper()}))
        rm = re.search(r"(?:remove|delete) cell\s+(\S+)", m)
        if rm:
            calls.append(("remove_cell", {"cell_id": rm.group(1).upper()}))

        if "multi" in m and "period" in m:
            calls.append(("plan_network_multi_period", {"demand_mode": "temporary" if "shift" in m or "diurnal" in m else "permanent"}))
        elif "plan" in m:
            calls.append(("plan_network", {"use_mip": "mip" in m or "optimal" in m}))
        if "apply" in m and "plan" in m:
            pid = re.search(r"([0-9a-f]{8}-[0-9a-f-]{27})", m)
            if pid:
                calls.append(("apply_plan", {"plan_id": pid.group(1)}))
        if any(k in m for k in ("congestion", "worst", "overload", "hotspot")):
            calls.append(("optimize_congestion", {"top_n": 5}))
        if "alert" in m:
            calls.append(("get_alerts", {"minutes": 60}))
        if "son" in m:
            calls.append(("get_son_status", {}))
        if any(k in m for k in ("ue ", "mobility", "usage", "handover")):
            calls.append(("query_ue", {"minutes": 30}))
        if "list" in m and "cell" in m:
            calls.append(("list_cells", {}))
        if not calls:
            calls.append(("query_network", {}))
        return calls

    @staticmethod
    def _summarize(name: str, result: Any) -> str:
        if not isinstance(result, dict):
            return f"{name}: {str(result)[:200]}"
        if name == "query_network":
            return f"Network: {result.get('total_cells', '?')} cells, {len(result.get('dus', []))} DUs, {len(result.get('cus', []))} CUs."
        if name == "optimize_congestion":
            top = result.get("cells", [])[:5]
            lines = [f"  - {c['cell_id']} ({c.get('level')}, score={c.get('congestion_score')})" for c in top]
            return "Top congested cells:\n" + "\n".join(lines) if lines else "No congestion data."
        if name == "get_alerts":
            return f"Alerts (last {result.get('window_minutes')}m): {result.get('count')} total, by severity {result.get('by_severity')}."
        if name == "get_son_status":
            return f"SON: {result.get('total_actions')} actions, by type {result.get('counts_by_type')}, active severity {result.get('active_alert_severity')}."
        if name in ("plan_network", "plan_network_multi_period"):
            return f"Plan {result.get('plan_id')}: {result.get('selected_cell_count')} cells, mip_used={result.get('mip_used')}, cost={result.get('cost_estimate', {}).get('total')}."
        if name == "list_cells":
            return f"{result.get('total', 0)} cells."
        if name in ("move_cell", "move_du", "add_cell", "remove_cell", "apply_plan"):
            return f"{name}: {result.get('status', result)}"
        return f"{name}: {json.dumps(result, default=str)[:200]}"

    def turn(self, session_id, message, sessions, system, context) -> Iterator[str]:
        history = sessions.setdefault(session_id, [])
        history.append({"role": "user", "content": message})
        parts = []
        for name, args in self._route(message):
            yield f"\n\n*[calling tool: {name}...]*\n"
            sanitized, result = _exec_tool(name, args)
            history.append({"role": "tool", "content": f"[{name}] {sanitized[:1500]}"})
            parts.append(self._summarize(name, result))
        text = "\n".join(parts) + "\n\n_(Mock backend — set GOOGLE_API_KEY or CLAUDE_CLI_PATH for real LLM reasoning.)_"
        history.append({"role": "assistant", "content": text})
        yield text


# =================================================================== Anthropic-style
def _anthropic_loop(client, model, session_id, message, sessions, system, context) -> Iterator[str]:
    """Shared native tool-calling loop for the Anthropic SDK + Claude CLI backends."""
    history = sessions.setdefault(session_id, [])
    history.append({"role": "user", "content": message})
    full_system = system + "\n\n" + context
    while True:
        resp = client.create(model=model, system=full_system, messages=history, tools=T.TOOL_SCHEMAS)
        assistant_content = resp["content"]
        history.append({"role": "assistant", "content": assistant_content})
        tool_uses = [b for b in assistant_content if b.get("type") == "tool_use"]
        for b in assistant_content:
            if b.get("type") == "text" and b.get("text"):
                yield b["text"]
        if not tool_uses:
            break
        tool_results = []
        for tu in tool_uses:
            yield f"\n\n*[calling tool: {tu['name']}...]*\n"
            sanitized, _ = _exec_tool(tu["name"], tu.get("input", {}))
            tool_results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": sanitized})
        history.append({"role": "user", "content": tool_results})


class AnthropicBackend:
    name = "anthropic-api"

    def __init__(self) -> None:
        import anthropic
        self.model = ANTHROPIC_ALIASES.get(DEFAULT_MODEL, DEFAULT_MODEL)
        self._sdk = anthropic.Anthropic()

    class _Client:
        def __init__(self, sdk):
            self._sdk = sdk

        def create(self, model, system, messages, tools):
            msg = self._sdk.messages.create(model=model, max_tokens=2048, system=system,
                                            messages=messages, tools=[{"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]} for t in tools])
            return {"content": [b.model_dump() for b in msg.content]}

    def turn(self, session_id, message, sessions, system, context):
        return _anthropic_loop(self._Client(self._sdk), self.model, session_id, message, sessions, system, context)


class ClaudeCLIBackend:
    """Spawns `claude -p` and adapts its output to the native Anthropic tool loop."""
    name = "claude-cli"

    def __init__(self, cli_path: str) -> None:
        self.model = DEFAULT_MODEL
        self.cli_path = cli_path

    class _Client:
        def __init__(self, cli_path, model):
            self.cli_path = cli_path
            self.model = model

        def create(self, model, system, messages, tools):
            prompt = json.dumps({"system": system, "messages": messages})
            proc = subprocess.run([self.cli_path, "-p", "--model", model, "--output-format", "json"],
                                  input=prompt, capture_output=True, text=True, timeout=120)
            try:
                data = json.loads(proc.stdout)
                content = data.get("content") or [{"type": "text", "text": data.get("result", proc.stdout)}]
            except Exception:  # noqa: BLE001
                content = [{"type": "text", "text": proc.stdout.strip() or proc.stderr.strip()}]
            return {"content": content}

    def turn(self, session_id, message, sessions, system, context):
        return _anthropic_loop(self._Client(self.cli_path, self.model), self.model, session_id, message, sessions, system, context)


# =========================================================================== Gemini
class GeminiBackend:
    name = "gemini"

    def __init__(self) -> None:
        from google import genai
        self.model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        self._genai = genai
        self._client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        self._gtools = T.gemini_tools()

    def turn(self, session_id, message, sessions, system, context) -> Iterator[str]:
        from google.genai import types
        history = sessions.setdefault(session_id, [])
        history.append(types.Content(role="user", parts=[types.Part(text=message)]))
        cfg = types.GenerateContentConfig(system_instruction=system + "\n\n" + context, tools=self._gtools)
        while True:
            resp = self._client.models.generate_content(model=self.model, contents=history, config=cfg)
            cand = resp.candidates[0].content
            history.append(cand)
            calls = [p.function_call for p in cand.parts if getattr(p, "function_call", None)]
            for p in cand.parts:
                if getattr(p, "text", None):
                    yield p.text
            if not calls:
                break
            responses = []
            for fc in calls:
                yield f"\n\n*[calling tool: {fc.name}...]*\n"
                sanitized, result = _exec_tool(fc.name, dict(fc.args or {}))
                responses.append(types.Part.from_function_response(name=fc.name, response={"result": result}))
            history.append(types.Content(role="user", parts=responses))


# =========================================================================== resolve
def resolve_backend():
    cli = os.environ.get("CLAUDE_CLI_PATH", "")
    if cli and os.path.exists(cli):
        log.info("backend: Claude CLI (%s)", cli)
        return ClaudeCLIBackend(cli)
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            b = AnthropicBackend(); log.info("backend: Anthropic API"); return b
        except Exception as exc:  # noqa: BLE001
            log.warning("Anthropic backend init failed: %s", exc)
    if os.environ.get("GOOGLE_API_KEY"):
        try:
            b = GeminiBackend(); log.info("backend: Gemini (%s)", b.model); return b
        except Exception as exc:  # noqa: BLE001
            log.warning("Gemini backend init failed: %s", exc)
    log.info("backend: Mock (no credentials)")
    return MockBackend()
