# 02.1 — Agent 1: LLM Orchestrator (`agents/orchestrator/`)

> **Parent:** [Agent Architecture](./spec.md) › [Root Spec](../spec.md)

FastAPI service on port 8082. Accepts natural-language operator commands over HTTP, drives a
multi-step tool-calling loop, and streams the response back in real time. Supports up to
**four** LLM backends selected at startup.

## Backend selection

Backends are resolved in a fixed priority order at startup. The first one whose
credentials/binary are available wins. The two production backends are **Claude CLI**
(primary, active in Docker) and **Gemini** (fallback); two additional dev-only backends —
**Anthropic API** and **Mock** — are part of the canonical superset so the service can run
with native SDK tool-calling or with no credentials at all.

| Priority | Condition | Backend | Active in Docker? |
|---|---|---|---|
| 1 | `CLAUDE_CLI_PATH` non-empty & binary present | **Claude CLI** | **Yes** — docker-compose sets `/usr/bin/claude` |
| 2 | `ANTHROPIC_API_KEY` set (and Claude CLI absent) | **Anthropic API** (direct SDK, native tool-calling) | No (opt-in) |
| 3 | `GOOGLE_API_KEY` set (and both above absent) | **Gemini** | Only if `CLAUDE_CLI_PATH` unset |
| 4 | none of the above | **Mock** intent router (deterministic, no LLM) | No — dev/test only |

**Claude CLI backend** (`CLAUDE_CLI_PATH` non-empty): spawns the `claude -p` process via
`CustomAnthropicClient`. `TOOL_SCHEMAS` are passed as-is (already in Anthropic native format
— no translation needed). Model selected via `ANTHROPIC_MODEL_NAME` (**default: `sonnet`**).
The model the client actually spawns and the model reported by `GET /health` MUST be the same
value — `CustomAnthropicClient` is constructed with the resolved `ANTHROPIC_MODEL_NAME`, never
a separate hard-coded default. Session history stored as
`_claude_sessions: dict[str, list[{"role", "content"}]]`.

**Anthropic API backend** (dev opt-in): uses the Anthropic Python SDK directly with the
native Messages tool-calling loop. `TOOL_SCHEMAS` used as-is, no translation. Same
`ANTHROPIC_MODEL_NAME` default (`sonnet`). The Claude CLI accepts short aliases natively, but
the direct Messages API requires concrete model ids, so the alias is resolved for this
backend (`sonnet` → `claude-sonnet-4-6`, `haiku` → `claude-haiku-4-5-20251001`,
`opus` → `claude-opus-4-8`); `GET /health` reports the resolved id actually in use.

**Mock backend** (no credentials): deterministic keyword→tool intent router used for CI and
offline demos. Emits a one-line notice that real reasoning requires `GOOGLE_API_KEY` or
`CLAUDE_CLI_PATH`.

**Gemini backend** (`CLAUDE_CLI_PATH` empty): uses `google-genai` SDK, requires
`GOOGLE_API_KEY`. Tool schemas translated from Anthropic-style JSON to Gemini
`function_declarations` at startup via `_clean_params()`. Model selected via `GEMINI_MODEL`
(code default: `gemini-2.0-flash`; docker-compose overrides to `gemini-2.5-flash`). Session
history stored as `_gemini_sessions: dict[str, list[types.Content]]`.

`GET /health` returns `{"status": "ok", "model": "<name>",
"backend": "claude-cli"|"anthropic-api"|"gemini"|"mock"}`. `model` MUST be the model actually
in use.

## Request / Response flow

```
User message  (POST /chat)
      │
      ├─► build_network_context()  ──GET /network──► Controller
      │         (live cell snapshot appended to system prompt)
      │
      ▼
SYSTEM_PROMPT + live snapshot + session history
      │
      ▼
  ┌──────────────────────────────────────────────┐
  │  Gemini 2.5 Flash  (non-streaming API call)  │
  └──────────────────────────────────────────────┘
      │
      ├── text parts → yield to caller (streaming)
      │
      └── function_call parts → tool-calling loop:
              ├─ yield "*[calling tool: name...]*"
              ├─ execute_tool(name, args)  (Python call)
              ├─ append FunctionResponse to history
              └─ call Gemini again  →  repeat until no tool calls
```

## System prompt

Two-part prompt injected on every request:

- **Static** (`SYSTEM_PROMPT`): 30-cell network overview — site naming convention
  (`MLS_<SITE>_<SECTOR>`), DU/CU hierarchy, per-band UE limits and power specs, operator
  guidelines (confirm before destructive actions, flag overloads, bullet summaries)
- **Dynamic** (`build_network_context()`): calls `GET /network` on the Controller and formats
  every cell as one line — `cell_id (area) → DU=... | UEs=... | PRB=...% | SINR=...dB |
  Power=...W`. Appended to the static prompt on every request so the LLM always sees current
  live state. Returns a warning message if the Controller is unreachable.

## Tool-calling loop

Each `/chat` request runs a `while True` loop until Gemini returns no function calls:

1. `gemini.models.generate_content(model, contents=history, config)` — synchronous,
   non-streaming
2. `model_content` (the full assistant turn) is appended to session history
3. Any text parts are yielded immediately to the streaming caller
4. For each `function_call` in the response:
   - Yield `\n\n*[calling tool: name...]*\n` (visible in the chat UI)
   - Call `T.TOOL_MAP[name](args)` — synchronous Python, hits Controller / Planning API /
     InfluxDB over HTTP
   - JSON-sanitise the result (`json.dumps(result, default=str)`) so proto Struct accepts it
   - Append a `FunctionResponse` part to a new `user` turn in history
5. Go to step 1 with the updated history. Break when the response contains no function calls.

Multiple tools can be called per response (Gemini may batch them); all are executed and their
results fed back in a single user turn before the next model call.

## Tool schema translation

`tools.py` stores all **14** tool schemas in **Anthropic-style JSON** (`name`,
`description`, `input_schema` with JSON Schema `properties`).

- **Claude CLI backend**: schemas used as-is — no translation needed.
- **Gemini backend**: `_clean_params()` strips `default` fields (Gemini rejects them), removes
  empty `enum` arrays (arises from the `""` sentinel in `severity` enum), and deep-copies to
  avoid mutating `TOOL_SCHEMAS`. Produces `GEMINI_TOOLS = [{"function_declarations": [...]}]`.

## Tool inventory

| Tool | HTTP call | Purpose |
|---|---|---|
| `query_network` | `GET /network` on Controller | Full topology + live KPIs for all 30 cells |
| `list_cells` | `GET /cells?area=&du_id=&cu_id=` | Filtered cell list with KPIs |
| `query_cell` | `GET /cells/{id}` | Single cell config + 30-min KPI time series |
| `move_cell` | `POST /move/cell` | Reassign a cell to a different DU |
| `move_du` | `POST /move/du` | Reassign a DU to a different CU |
| `plan_network` | `POST /plan` | Heuristic or MIP-optimal placement + PCI + slice planning |
| `plan_network_multi_period` | `POST /plan/multi-period` | Multi-period MIP (Case A phased rollout / Case B diurnal shift) |
| `apply_plan` | `POST /plan/apply` | Push accepted plan to Controller as live topology |
| `get_alerts` | InfluxDB Flux query (direct) | Recent KPI anomaly alerts tagged by severity and type |
| `query_ue` | InfluxDB Flux query (direct) | UE-level usage and mobility data (filter by ue_id or cell_id) |
| `get_son_status` | InfluxDB Flux query (direct) | SON action summary + counts by type, last 10 actions, active alert severity |
| `add_cell` | `POST /cells/add` on Controller | Deploy a new cell via chat; auto-assigns PCI if not provided |
| `remove_cell` | `DELETE /cells/{id}` on Controller | Decommission a cell and remove from DU assignment |
| `optimize_congestion` | `GET /congestion` on Controller | Ranked per-cell congestion scores (top-N); surfaces the worst cells for the LLM to act on |

Tool count is **14**. `optimize_congestion` materialises the SON congestion view as a
first-class operator tool. Every tool-count reference (system prompt, `GET /tools`, API
quick-ref) is consistent at **14**.

## Session management

- Two in-memory session stores: `_gemini_sessions` (list of `types.Content`) and
  `_claude_sessions` (list of `{"role", "content"}` dicts) — one is active depending on the
  backend
- Multiple sessions coexist independently per `session_id` (e.g. `default`, `ops-team`,
  `map-abc1234`)
- `DELETE /history` clears a session; sessions are lost on container restart (no persistence)
- `GET /history` normalises either session format into flat `{"role", "content"}` dicts; tool
  calls shown as `[Calling name]`, results as `[Tool result: name]`

## Streaming

`POST /chat` returns a FastAPI `StreamingResponse` wrapping a **synchronous generator**
(`chat_turn`). Starlette runs sync generators in a thread pool, so the blocking Gemini API
call and tool HTTP calls do not stall the asyncio event loop. The caller receives plain
`text/plain` chunks:

- LLM text — one chunk per Gemini response turn (not token-by-token; Gemini's non-streaming
  API returns the full turn at once)
- `\n\n*[calling tool: name...]*\n` — emitted before each tool execution
- `\n\n[Error] ...` — on quota exhaustion (`429`), rate limit, or API failure
- Quota/rate-limit errors are detected by checking for `"429"`, `"quota"`, or
  `"ResourceExhausted"` in the exception message

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `CLAUDE_CLI_PATH` | `""` (Gemini) / `/usr/bin/claude` (Docker) | Path to `claude` binary; non-empty activates Claude CLI backend (priority 1) |
| `ANTHROPIC_MODEL_NAME` | `sonnet` | Claude model alias (Claude CLI + Anthropic API backends). Single source of truth; `/health` reports the model actually used — for the direct Anthropic API the alias is resolved to a concrete id (e.g. `sonnet` → `claude-sonnet-4-6`) |
| `ANTHROPIC_API_KEY` | — (optional) | Activates the direct Anthropic SDK backend (priority 2) when set and Claude CLI is absent |
| `GOOGLE_API_KEY` | required for Gemini | Gemini API authentication (priority 3) |
| `GEMINI_MODEL` | `gemini-2.0-flash` (code) / `gemini-2.5-flash` (Docker) | Gemini model name (Gemini backend only) |
| `CONTROLLER_URL` | `http://controller:8080` | Context injection + move_cell / move_du tools |
| `PLANNING_URL` | `http://planning-api:8081` | plan_network / apply_plan tools |
| `INFLUX_URL` | `http://influxdb:8086` | get_alerts / query_ue / get_son_status (direct Flux queries) |
| `INFLUX_TOKEN` / `INFLUX_ORG` / `INFLUX_BUCKET` | — | InfluxDB authentication for direct queries |

**Credentials via `.env`.** In Docker, the orchestrator service loads an `env_file: .env` at
the repo root (template: `.env.example`). Set one backend's key there (`GOOGLE_API_KEY` or
`ANTHROPIC_API_KEY`, or `CLAUDE_CLI_PATH`) and run `docker compose up -d orchestrator`; with
none set, the **Mock** backend is used. `.env` is git-ignored.
