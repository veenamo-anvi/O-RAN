# 02.2 — chat.py Operator CLI Client

> **Parent:** [Agent Architecture](./spec.md) › [Root Spec](../spec.md)
> **Related:** [Orchestrator](./orchestrator.md)

`chat.py` (project root) is a standalone terminal REPL that connects to the orchestrator's
REST API. It contains no LLM logic — it is a pure UI layer that formats requests and prints
responses.

## Usage

```bash
py chat.py                                    # default: localhost:8082, session "default"
py chat.py --url http://remote-host:8082      # remote orchestrator
py chat.py --session ops-team                 # named session (isolated history)
```

On startup it calls `GET /health` and prints a banner showing the active model name and
orchestrator URL. If the orchestrator is unreachable, it prints a warning but continues
(useful when starting before `docker compose up` is finished).

## Built-in commands

| Command | Action |
|---|---|
| `/status` | Expands → *"What is the current status of all cells, DUs, and CUs? Summarise in a table."* |
| `/alerts` | Expands → *"Show me all recent KPI alerts from the last 60 minutes."* |
| `/cells` | Expands → *"List all cells with their current connected UEs, PRB utilisation, and DU assignment."* |
| `/plan` | Expands → *"Generate a network plan for Malleswaram with default parameters and show me a summary."* |
| `/son` | Expands → *"Show me the recent SON autonomous actions and their outcomes."* |
| `/ue` | Expands → *"Show me UE usage and mobility events from the last 30 minutes."* |
| `/history` | `GET /history?session_id=...` — prints past turns (role + first 200 chars) |
| `/clear` | `DELETE /history?session_id=...` — resets server-side conversation |
| `/tools` | `GET /tools` — lists all available agent tools with short descriptions |
| `quit` / `exit` / `q` | Exits the CLI |

Any other input is sent as-is to `POST /chat` with the current `session_id`.

## Transport

Pure Python stdlib (`urllib.request`, `urllib.error`) — no external dependencies beyond the
standard library. The `/chat` call is **synchronous** (blocks until the server closes the
response body), so the full response appears at once rather than token-by-token. For live
streaming output, use the map server's built-in chat panel (which uses the browser Fetch API
with `ReadableStream`).

## Session semantics

`--session` sets the `session_id` field in every request. Multiple operators can run separate
`chat.py` instances with different `--session` names against the same orchestrator without
sharing context or history. The map server's integrated chat panel uses a randomised session
ID (`map-xxxxxxx`) per page load to avoid cross-contamination with CLI sessions.
