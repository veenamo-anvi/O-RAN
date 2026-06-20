"""PCI planning via graph colouring — collision-free AND confusion-free.

collision-free : no two adjacent cells share a PCI.
confusion-free : no cell has two neighbours with the same PCI (i.e. colour the square graph
                 G^2 — forbid colours of neighbours and neighbours-of-neighbours).
"""
from __future__ import annotations

from typing import Any

from geo import haversine_m

NEIGHBOR_RADIUS_M = 800.0
MAX_PCI = 503


def _neighbors(cells: dict[str, Any]) -> dict[str, set[str]]:
    ids = list(cells)
    adj: dict[str, set[str]] = {cid: set() for cid in ids}
    for i, a in enumerate(ids):
        ca = cells[a]
        for b in ids[i + 1:]:
            cb = cells[b]
            if haversine_m(ca["lat"], ca["lon"], cb["lat"], cb["lon"]) <= NEIGHBOR_RADIUS_M:
                adj[a].add(b)
                adj[b].add(a)
    return adj


def assign_pcis(cells: dict[str, Any]) -> dict[str, int]:
    """Assign a PCI to every cell. Mutates cells['pci'] and returns {cell_id: pci}."""
    adj = _neighbors(cells)
    # colour higher-degree cells first (better packing)
    order = sorted(cells, key=lambda c: len(adj[c]), reverse=True)
    pci_of: dict[str, int] = {}
    for cid in order:
        forbidden: set[int] = set()
        for n in adj[cid]:
            if n in pci_of:
                forbidden.add(pci_of[n])
            for nn in adj[n]:           # neighbours-of-neighbours -> confusion-free
                if nn in pci_of:
                    forbidden.add(pci_of[nn])
        pci = 0
        while pci in forbidden and pci < MAX_PCI:
            pci += 1
        pci_of[cid] = pci
        cells[cid]["pci"] = pci
    return pci_of


def verify(cells: dict[str, Any]) -> dict[str, Any]:
    """Return collision/confusion conflict counts (0/0 == valid plan)."""
    adj = _neighbors(cells)
    collisions = 0
    confusions = 0
    for cid, neigh in adj.items():
        pci = cells[cid]["pci"]
        npcis = [cells[n]["pci"] for n in neigh]
        collisions += sum(1 for p in npcis if p == pci)
        confusions += len(npcis) - len(set(npcis))
    return {"collisions": collisions // 2, "confusions": confusions // 2,
            "valid": collisions == 0 and confusions == 0}
