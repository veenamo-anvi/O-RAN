"""Phase-F smoke test: coverage model, map routes, proxy graceful-degradation, dashboards."""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
from coverage import compute_coverage_radius_m  # noqa: E402

c = TestClient(main.app)
fails = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


print("coverage model (COST-231-Hata)")
r_n78 = compute_coverage_radius_m("n78", 1000, "5G", "64T64R")
r_b3 = compute_coverage_radius_m("B3", 320, "4G", "4T4R")
r_n28 = compute_coverage_radius_m("n28", 1000, "5G", "8T8R")
check("n78 radius positive", r_n78 > 0)
check("b3 radius positive", r_b3 > 0)
check("lower band reaches further (n28 > n78)", r_n28 > r_n78)
print(f"    n78={r_n78}m b3={r_b3}m n28={r_n28}m")

print("map routes")
check("health ok", c.get("/health").json()["status"] == "ok")
idx = c.get("/")
check("index serves Leaflet HTML", idx.status_code == 200 and "leaflet" in idx.text.lower() and "/api/chat" in idx.text)

print("graceful degradation (controller + orchestrator down)")
check("/api/cells 503 when controller down", c.get("/api/cells").status_code == 503)
check("/api/orch-health 503 when orch down", c.get("/api/orch-health").status_code == 503)
check("/api/tools 503 when orch down", c.get("/api/tools").status_code == 503)
check("/api/history 503 when orch down", c.get("/api/history").status_code == 503)

print("grafana provisioning")
dash_dir = os.path.join(ROOT, "grafana", "provisioning", "dashboards")
files = sorted(glob.glob(os.path.join(dash_dir, "*.json")))
check("5 dashboard JSONs", len(files) == 5)
valid = True
titles = []
for fp in files:
    try:
        d = json.load(open(fp, encoding="utf-8"))
        titles.append(d.get("title"))
        if "panels" not in d or not d["panels"]:
            valid = False
    except Exception:
        valid = False
check("all dashboards valid JSON with panels", valid)
expected = {"Network Overview", "Cell KPI", "UE Analytics", "SON Alerts", "DU/CU Performance"}
check("expected dashboard titles", set(titles) == expected)
check("datasource yaml present", os.path.exists(os.path.join(ROOT, "grafana", "provisioning", "datasources", "influxdb.yaml")))

print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
