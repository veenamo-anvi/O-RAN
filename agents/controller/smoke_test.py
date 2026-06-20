"""Phase-A smoke test for the Controller (no InfluxDB required).

Runs the FastAPI app in-process via TestClient against the generated topology.json.
InfluxDB is unreachable here, so `kpi` dicts come back empty — that is the expected
graceful-degradation behaviour. Exercises read routes + every mutation.
"""
import os
import sys

# point the store at the generated dev topology before importing the app
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
os.environ["TOPOLOGY_FILE"] = os.path.join(ROOT, "dev-env", "config", "topology.json.test")

# work on a throwaway copy so the test never mutates the real source of truth
import shutil
src = os.path.join(ROOT, "dev-env", "config", "topology.json")
shutil.copyfile(src, os.environ["TOPOLOGY_FILE"])

sys.path.insert(0, HERE)
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

c = TestClient(main.app)
fails = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


print("health / topology")
h = c.get("/health").json()
check("health 30 cells", h["cells"] == 30 and h["dus"] == 3 and h["cus"] == 1)

print("network / cells / congestion")
net = c.get("/network").json()
check("network 30 cells", net["total_cells"] == 30)
check("cells have kpi dict", all("kpi" in cc for cc in net["cells"]))
flt = c.get("/cells", params={"du_id": "DU-MLS-2"}).json()
check("filter DU-MLS-2 -> 9", flt["total"] == 9)
one = c.get("/cells/MLS_RWS_01").json()
check("cell detail config+series", one["cell"]["cell_id"] == "MLS_RWS_01" and "series" in one)
cong = c.get("/congestion").json()
check("congestion 30 ranked", cong["total_cells"] == 30 and len(cong["cells"]) == 30)

print("neighbors")
nb = c.get("/neighbors/MLS_RWS_01", params={"max_neighbors": 6}).json()
check("neighbors=6 sorted", len(nb["neighbors"]) == 6 and
      nb["neighbors"] == sorted(nb["neighbors"], key=lambda r: r["distance_m"]))

print("move/cell")
mv = c.post("/move/cell", json={"cell_id": "MLS_RWS_01", "to_du_id": "DU-MLS-2"}).json()
check("move ok", mv["status"] == "ok" and mv["to_du"] == "DU-MLS-2")
check("move persisted", c.get("/cells/MLS_RWS_01").json()["cell"]["du_id"] == "DU-MLS-2")
check("move bad du -> 404", c.post("/move/cell", json={"cell_id": "MLS_RWS_01", "to_du_id": "NOPE"}).status_code == 404)

print("cells/add (PCI auto-assign) + delete")
add = c.post("/cells/add", json={"cell_id": "MLS_NEW_01", "du_id": "DU-MLS-1", "pci": 0,
                                 "band": "n78", "generation": "5G"}).json()
check("add auto-pci 31", add["status"] == "ok" and add["pci"] == 31)
check("add dup -> 409", c.post("/cells/add", json={"cell_id": "MLS_NEW_01", "du_id": "DU-MLS-1"}).status_code == 409)
check("count now 31", c.get("/health").json()["cells"] == 31)
dl = c.delete("/cells/MLS_NEW_01").json()
check("delete ok", dl["status"] == "ok")
check("count back to 30", c.get("/health").json()["cells"] == 30)

print("son/pci-reopt")
before = c.get("/cells/MLS_18C_01").json()["cell"]["pci"]
re = c.post("/son/pci-reopt", json={"cell_id": "MLS_18C_01"}).json()
check("pci-reopt ok + changed", re["status"] == "ok" and re["to_pci"] != before)

print("move/du + topology/replace")
mdu = c.post("/move/du", json={"du_id": "DU-MLS-3", "to_cu_id": "CU-MLS"}).json()
check("move/du same cu noop-ish ok", mdu["status"] == "ok")
topo = c.get("/topology").json()
rep = c.post("/topology/replace", json={"cus": topo["cus"], "dus": topo["dus"], "cells": topo["cells"]}).json()
check("topology/replace ok", rep["status"] == "ok" and rep["cells"] == 30)
check("replace empty -> 400", c.post("/topology/replace", json={"cus": {}, "dus": {}, "cells": {}}).status_code == 400)

os.remove(os.environ["TOPOLOGY_FILE"])
print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
