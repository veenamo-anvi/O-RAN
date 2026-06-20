"""Phase-G integration test: orchestrator -> planning -> controller -> topology change.

Launches the Controller (8090), Planning (8091), and Orchestrator (8092, Mock backend) as
real uvicorn subprocesses and drives the end-to-end flow over HTTP, then tears them down.
No InfluxDB / Grafana / sims required.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fails = []
procs = []
logs = {}


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


def get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        import json
        return json.loads(r.read().decode())


def post(url, body):
    import json
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode()


def start(name, cwd, port, env_extra):
    env = dict(os.environ)
    for k in ("GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_CLI_PATH"):
        env.pop(k, None)
    env.update(env_extra)
    log = open(os.path.join(tempfile.gettempdir(), f"oran_{name}.log"), "w")
    logs[name] = log.name
    p = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    procs.append(p)
    return p


def wait_health(port, path="/health", timeout=40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            get(f"http://127.0.0.1:{port}{path}")
            return True
        except Exception:
            time.sleep(0.5)
    return False


tmpdir = tempfile.mkdtemp()
topo_path = os.path.join(tmpdir, "topology.json")
shutil.copyfile(os.path.join(ROOT, "dev-env", "config", "topology.json"), topo_path)

try:
    start("controller", os.path.join(ROOT, "agents", "controller"), 8090,
          {"TOPOLOGY_FILE": topo_path, "INFLUX_URL": "http://127.0.0.1:1"})
    start("planning", os.path.join(ROOT, "agents", "planning"), 8091,
          {"CONTROLLER_URL": "http://127.0.0.1:8090"})
    start("orchestrator", os.path.join(ROOT, "agents", "orchestrator"), 8092,
          {"CONTROLLER_URL": "http://127.0.0.1:8090", "PLANNING_URL": "http://127.0.0.1:8091",
           "INFLUX_URL": "http://127.0.0.1:1"})

    print("startup")
    check("controller up", wait_health(8090))
    check("planning up", wait_health(8091))
    check("orchestrator up", wait_health(8092))

    print("orchestrator backend = mock, model reported")
    oh = get("http://127.0.0.1:8092/health")
    check("backend mock", oh["backend"] == "mock" and oh["model"] == "mock-intent-router")

    print("planning -> controller (apply replaces live topology)")
    import json
    plan = json.loads(post("http://127.0.0.1:8091/plan", {"deployment_budget": 3_000_000, "use_mip": False}))
    pid, ncells = plan["plan_id"], plan["selected_cell_count"]
    applied = json.loads(post("http://127.0.0.1:8091/plan/apply", {"plan_id": pid}))
    check("apply ok", applied.get("status") == "applied")
    ctrl_cells = get("http://127.0.0.1:8090/health")["cells"]
    check(f"controller topology replaced ({ctrl_cells}=={ncells})", ctrl_cells == ncells)

    print("orchestrator -> controller (move cell via chat)")
    topo = get("http://127.0.0.1:8090/topology")
    cid = next(iter(topo["cells"]))
    cur_du = topo["cells"][cid]["du_id"]
    other_du = next((d for d in topo["dus"] if d != cur_du), None)
    if other_du:
        body = post("http://127.0.0.1:8092/chat", {"message": f"move cell {cid} to {other_du}", "session_id": "it"})
        moved = get(f"http://127.0.0.1:8090/cells/{cid}")["cell"]["du_id"]
        check("move marker streamed", "move_cell" in body)
        check(f"cell reassigned ({cur_du}->{other_du})", moved == other_du)
    else:
        check("multiple DUs to move between", False)

    print("orchestrator -> planning (plan via chat)")
    body = post("http://127.0.0.1:8092/chat", {"message": "generate a network plan", "session_id": "it"})
    check("plan summary streamed", "Plan" in body and "calling tool: plan_network" in body)

    print("orchestrator -> controller (live network context injected)")
    body = post("http://127.0.0.1:8092/chat", {"message": "what is the network status?", "session_id": "it"})
    check("network query streamed", "query_network" in body and "Network:" in body)

finally:
    for p in procs:
        p.terminate()
    for p in procs:
        try:
            p.wait(timeout=10)
        except Exception:
            p.kill()
    if fails:
        print("\n--- server logs (tail) ---")
        for name, path in logs.items():
            try:
                tail = open(path, encoding="utf-8", errors="replace").read()[-800:]
                print(f"[{name}]\n{tail}")
            except Exception:
                pass
    shutil.rmtree(tmpdir, ignore_errors=True)

print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
