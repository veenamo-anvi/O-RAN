# 01.2 — Vendor Distribution

> **Parent:** [System Architecture](./spec.md) › [Root Spec](../spec.md)
> **Sibling:** [Network Topology](./network-topology.md)

Four vendors, **25% each — 10 cells per vendor**.

| Vendor | 5G Hardware | 4G Hardware | 5G Max UEs | 5G Peak DL | System Power |
|---|---|---|---|---|---|
| Nokia | AirScale MAA 64T64R | AWHFA | 800 | 3800 Mbps | 1000 W |
| Ericsson | AIR 6449 / AIR 3221 | RBS 6402 | 750 | 3600 Mbps | 950 W |
| Samsung | TM500 64T64R | RRU | 700 | 3400 Mbps | 900 W |
| ZTE | AAU 5614 | RRU | 680 | 3200 Mbps | 1000 W |

These hardware fields (`vendor`, `hardware_model`, `generation`, `antenna_config`,
`tx_power_w`, `idle_power_w`, `peak_dl_mbps`, `freq_mhz`, `max_ues`) are preserved end-to-end
through `plan_to_topology()` (see [Planning Engine](../02-agents/planning-engine.md)) and used
for coverage radius computation in the [Map Server](../02-agents/map-server.md).

Map colour coding: Nokia=blue, Ericsson=green, Samsung=purple, ZTE=orange.
