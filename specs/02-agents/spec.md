# 02 — Agent Architecture

> **Parent:** [Root Spec](../spec.md)
> **Children:** [Orchestrator](./orchestrator.md) · [chat.py CLI](./chat-cli.md) ·
> [Controller](./controller.md) · [Planning Engine](./planning-engine.md) ·
> [KPI Agent](./kpi-agent.md) · [Map Server](./map-server.md)

The system is composed of five agents plus a thin operator CLI client. Each has its own
child spec:

| Agent | Port | Child spec | Role |
|---|---|---|---|
| Agent 1 — LLM Orchestrator | 8082 | [orchestrator.md](./orchestrator.md) | NL command understanding, tool-calling, streaming |
| — chat.py CLI client | — | [chat-cli.md](./chat-cli.md) | Standalone terminal REPL over the orchestrator REST API |
| Agent 2 — Controller | 8080 | [controller.md](./controller.md) | Single source of truth for topology; live moves + CRUD |
| Agent 3 — Planning Engine | 8081 | [planning-engine.md](./planning-engine.md) | Placement, PCI, slicing, MIP, multi-period |
| Agent 4 — KPI Monitoring | — | [kpi-agent.md](./kpi-agent.md) | BiLSTM anomaly detection + autonomous SON actions |
| Agent 5 — Map Server | 8083 | [map-server.md](./map-server.md) | Leaflet.js live map + orchestrator proxy |
