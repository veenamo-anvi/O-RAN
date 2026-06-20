# 01.1 — Network Topology (Malleswaram, North Bangalore)

> **Parent:** [System Architecture](./spec.md) › [Root Spec](../spec.md)
> **Sibling:** [Vendor Distribution](./vendor-distribution.md)

**Population model:** 40,000 residents + 15% commuter overhead (railway station transit hub)
= 46,000 effective. Tier-1 operator 40% market share → **18,400 peak active UEs**. Busy-hour
traffic = 18,400 × 0.025 Erlangs/user = **460 Erlangs**. At 16 Erlangs per sector (Erlang-C,
2% blocking) → **29–30 sectors required**.

| CU | DU | Sites served | Cells |
|---|---|---|---|
| CU-MLS | DU-MLS-1 | RWS, 18C, BEL, SNK (north) | 12 |
| CU-MLS | DU-MLS-2 | SPG, 3MN, 10C (central) | 9 |
| CU-MLS | DU-MLS-3 | MGR, CHD, 6CR (south-west) | 9 |

**30 cells (10 macro sites × 3 sectors). 700 MHz (n28) is _supported but not deployed_** —
its ~8.4 km coverage radius extends beyond Malleswaram to Peenya. The planner accepts `n28`
only when an operator passes it explicitly in `spectrum_bands`; it MUST NOT appear in any
default band list, candidate-site table, or deployed topology.

### Sector mix per site

| Sites | Sector 1 | Sector 2 | Sector 3 |
|---|---|---|---|
| RWS, 18C, SNK, SPG, 10C (high traffic) | 5G n78 3500 MHz | 5G n41 2500 MHz | 4G B3 1800 MHz |
| BEL, 3MN, MGR, CHD, 6CR (residential) | 5G n78 3500 MHz | 4G B40 2300 MHz | 4G B3 1800 MHz |

**Two distinct figures — do not conflate:**

- **Concurrent capacity = 16,500 UEs** (`max_ues` summed across cells: 900×10 n78 + 700×5 n41
  + 300×5 B40 + 250×10 B3) — the most UEs *connectable at one instant*. This is the per-cell
  `max_ues` value present in `topology.json`, so any live "sum of max UEs" query returns 16,500.
- **Design busy-hour peak (`active_ues_peak`) = 18,400 UEs** — the *active-user population in the
  busiest hour* (46,000 effective × 40% share). A planning figure, not a per-cell field.

Peak demand (18,400) intentionally **exceeds** concurrent capacity (16,500); the ~1,900 gap is
absorbed by Erlang-C blocking (~2%) because not all busy-hour users are connected at the same
instant. So "max UEs" (16,500, capacity) and "peak UEs" (18,400, demand) are different by design.

**Cell naming convention:** `MLS_<SITE>_<SECTOR>`.

> Related: deployed band defaults in [Planning Engine](../02-agents/planning-engine.md).
