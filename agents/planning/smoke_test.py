"""Phase-C smoke test for the Planning Engine (no Controller required)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import pci_planner  # noqa: E402

c = TestClient(main.app)
fails = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


print("health / candidates / demand-clusters")
check("health ok", c.get("/health").json()["status"] == "ok")
cand = c.get("/candidates").json()
check("candidates >= 10 sites", cand["total"] >= 10)
dc = c.get("/demand-clusters").json()
check("10 demand clusters", dc["total"] == 10)

print("POST /plan (heuristic)")
p = c.post("/plan", json={"deployment_budget": 3_000_000}).json()
check("plan_id returned", "plan_id" in p)
check("cells selected", p["selected_cell_count"] > 0 and len(p["cells"]) == p["selected_cell_count"])
check("mip_used False", p["mip_used"] is False)
check("slice allocations present", "slice_allocations" in p and "totals" in p["slice_allocations"])
check("cost estimate present", p["cost_estimate"]["total"] > 0)
check("pci collision/confusion-free", p["pci_check"]["valid"] is True)
bands_in_plan = {cell["band"] for cell in p["cells"]}
check("no n28 by default", "n28" not in bands_in_plan)
check("default bands subset", bands_in_plan <= {"n78", "n41", "B3", "B40"})

print("GET /plan/{id}")
got = c.get(f"/plan/{p['plan_id']}").json()
check("retrieve stored plan", got["plan_id"] == p["plan_id"])
check("404 on unknown plan", c.get("/plan/does-not-exist").status_code == 404)

print("n28 explicit-only")
p28 = c.post("/plan", json={"spectrum_bands": ["n78", "n41", "B3", "B40", "n28"]}).json()
check("n28 appears when explicit", "n28" in {cell["band"] for cell in p28["cells"]})

print("POST /plan use_mip=true (MIP or graceful fallback)")
pm = c.post("/plan", json={"use_mip": True, "mip_time_limit_sec": 30, "sinr_min_db": 6}).json()
check("mip plan has cells", pm["selected_cell_count"] > 0)
check("mip pci valid", pm["pci_check"]["valid"] is True)
print(f"    (mip_used={pm['mip_used']})")

print("POST /plan/multi-period")
mp = c.post("/plan/multi-period", json={"demand_mode": "permanent", "mip_time_limit_sec": 30}).json()
check("build_schedule present", "build_schedule" in mp and len(mp["build_schedule"]) > 0)
check("mp pci valid", mp["pci_check"]["valid"] is True)
mp2 = c.post("/plan/multi-period", json={"demand_mode": "temporary", "mip_time_limit_sec": 30}).json()
check("temporary mode ok", mp2["demand_mode"] == "temporary" and mp2["selected_cell_count"] > 0)

print("POST /plan/apply (controller unreachable -> 503, no crash)")
ap = c.post("/plan/apply", json={"plan_id": p["plan_id"]})
check("apply 503 when controller down", ap.status_code == 503)

print("plan topology is controller-compatible (DU/CU refs resolve)")
topo = main.pipeline.get_plan(p["plan_id"])["_topology"]
ok_refs = all(cell["du_id"] in topo["dus"] for cell in topo["cells"].values()) and \
    all(du["cu_id"] in topo["cus"] for du in topo["dus"].values())
check("topology references valid", ok_refs)

print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
