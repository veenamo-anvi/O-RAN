"""Phase-G unit tests: PCI planning, slice allocation, placement, congestion scoring."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "agents", "planning"))
sys.path.insert(0, os.path.join(ROOT, "agents", "controller"))

fails = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


# ---------------------------------------------------------------- PCI planner
print("PCI planner (graph colouring)")
import candidates as C  # noqa: E402
import pci_planner  # noqa: E402

cells = C.build_candidate_cells(["n78", "n41", "B3", "B40"])
pci_planner.assign_pcis(cells)
v = pci_planner.verify(cells)
check("collision-free", v["collisions"] == 0)
check("confusion-free", v["confusions"] == 0)
check("verify reports valid", v["valid"] is True)
check("all cells have pci", all(c["pci"] >= 0 for c in cells.values()))

# ---------------------------------------------------------------- slice allocator
print("slice allocator")
import slice_allocator as SA  # noqa: E402

alloc = SA.allocate(cells, {"eMBB": 0.5, "URLLC": 0.3, "mMTC": 0.2})
check("fractions normalised ~1", abs(sum(alloc["profile_fractions"].values()) - 1.0) < 1e-6)
check("eMBB largest share", alloc["profile_fractions"]["eMBB"] > alloc["profile_fractions"]["mMTC"])
one = next(iter(alloc["per_cell"].values()))
check("per-cell slices sum <= total_prb", one["eMBB"] + one["URLLC"] + one["mMTC"] <= one["total_prb"] + 1)
check("totals accumulated", alloc["totals"]["eMBB"] > 0)

# ---------------------------------------------------------------- placement
print("placement heuristic")
import placement  # noqa: E402

sel, sites = placement.select_cells(["n78", "n41", "B3", "B40"], deployment_budget=3_000_000)
check("selected non-empty", len(sel) > 0 and len(sites) > 0)
check("selected cells belong to selected sites", all(C.site_of(cid) in sites for cid in sel))
tiny_sel, tiny_sites = placement.select_cells(["n78", "n41", "B3", "B40"], deployment_budget=150_000)
check("budget limits site count", len(tiny_sites) <= len(sites))

# ---------------------------------------------------------------- congestion
print("congestion scorer")
import congestion  # noqa: E402

low = congestion.score_cell({"prb_dl_pct": 10, "sinr_db": 22, "bler_pct": 1, "latency_ms": 10})
high = congestion.score_cell({"prb_dl_pct": 98, "sinr_db": 3, "bler_pct": 18, "latency_ms": 120})
check("higher load -> higher score", high > low)
check("critical score > 0.75", high > 0.75)
ranked = congestion.rank(
    {"c1": {"area": "a", "du_id": "DU-MLS-1", "band": "n78"},
     "c2": {"area": "b", "du_id": "DU-MLS-2", "band": "B3"}},
    {"c1": {"prb_dl_pct": 95, "sinr_db": 4, "bler_pct": 15, "latency_ms": 100},
     "c2": {"prb_dl_pct": 12, "sinr_db": 20, "bler_pct": 1, "latency_ms": 8}},
)
check("rank sorted desc", ranked["cells"][0]["cell_id"] == "c1")
check("summary counts total", sum(ranked["summary"].values()) == ranked["total_cells"] == 2)

print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
