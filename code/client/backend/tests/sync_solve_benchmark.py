"""
Benchmarks the *actual* synchronous solve path (Django's real upload() and
run_model() views, called in-process via RequestFactory -- same code
production runs, no HTTP server needed) across a sweep of roster sizes,
using the frontend's own default group-count formula
(CreateGroups.js: groupsNumber = min(4, totalStudents)) rather than an
arbitrary shape.

Why this matters: the original SYNC_SOLVE_MAX_STUDENTS=100 benchmark used a
fixed 8-group shape (mate-demo-script.md's validated config). But
CreateGroups.js's own default caps groupsNumber at 4 regardless of roster
size -- so a real user who doesn't touch that field gets *fewer, larger*
groups as N grows, which turned out to be a meaningfully harder shape for
CP-SAT (a 50-student/4-group run took ~29s total wall time in a live UI
test, vs ~2s for the original 50-student/8-group benchmark point). This
script sweeps N using that actual default shape, post the run_model()
wall-clock-budget fix (optimization_cpsat.py's run_model() now bounds
model-build + hint + search together, not just the search), and reports
whether each point reaches OPTIMAL/FEASIBLE inside the real production
budget (SYNC_SOLVE_TMAX_SECONDS) or not.

Run from code/client:
    DJANGO_SETTINGS_MODULE=project.settings python3 backend/tests/sync_solve_benchmark.py
"""
import io
import os
import random
import sys
import time

sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")

import django
django.setup()

from django.conf import settings
from django.test import RequestFactory
from openpyxl import Workbook

from backend import views

# Diversity chosen to avoid model_common.get_min_capacity() collapsing a
# large roster into fewer distinct student "types" than students -- see
# this session's ARCHITECTURE.md note. 3 attributes x 3 values, 8 topics
# ranked 3 deep, 3 sections with independent 80% availability.
ATTRS = {"A1": ["a", "b", "c"], "A2": ["x", "y", "z"], "A3": ["p", "q", "r"]}
MODULES = ["Mon 10:00", "Wed 15:00", "Fri 09:00"]
TOPICS = [f"Topic{i}" for i in range(8)]
RANK_COUNT = 3

SYNC_TMAX_SECONDS = settings.SYNC_SOLVE_TMAX_SECONDS  # real production value


def build_roster_xlsx(n_students, seed):
    random.seed(seed)
    wb = Workbook()
    ws = wb.active
    header = ["student_fk"] + list(ATTRS.keys()) + MODULES + list(range(1, RANK_COUNT + 1))
    ws.append(header)
    weights = [8, 7, 6, 5, 4, 3, 2, 1]
    for i in range(n_students):
        row = [f"s{i}"]
        for values in ATTRS.values():
            row.append(random.choice(values))
        for _ in MODULES:
            row.append(1 if random.random() < 0.8 else 0)
        pool, w = list(TOPICS), list(weights)
        for _ in range(RANK_COUNT):
            idx = random.choices(range(len(pool)), weights=w, k=1)[0]
            row.append(pool[idx])
            pool.pop(idx)
            w.pop(idx)
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def run_point(rf, n_students, seed):
    roster = build_roster_xlsx(n_students, seed)
    upload_req = rf.post("/dev/upload/", data={
        "attributes": ",".join(ATTRS.keys()),
        "modules": ",".join(MODULES),
        "preferencesNumber": str(RANK_COUNT),
        "file": roster,
    })
    upload_resp = views.upload(upload_req)
    if upload_resp.status_code != 200:
        return {"n": n_students, "error": f"upload {upload_resp.status_code}"}
    import json
    students = json.loads(upload_resp.data["students"])
    options = json.loads(upload_resp.data["a"])

    # Mirror CreateGroups.js's own default formula exactly.
    groups_number = max(1, min(4, n_students))
    min_students = max(1, n_students // groups_number - 1)
    max_students = max(1, -(-n_students // groups_number) + 1)  # ceil + 1

    bounds = {}
    for attr, values in ATTRS.items():
        for v in values:
            bounds[v] = {"min": 0, "max": n_students, "solo": False}
    capacity = {m: n_students for m in MODULES}
    fixed_day = {m: {p: False for p in TOPICS} for m in MODULES}
    prefs_bounds = {p: {"min": 0, "max": groups_number} for p in TOPICS}

    body = {
        "attributes": list(ATTRS.keys()),
        "preferences": TOPICS,
        "groupsNumber": groups_number,
        "minStudents": min_students,
        "maxStudents": max_students,
        "bounds": bounds,
        "students": students,
        "capacity": capacity,
        "preferencesNumber": RANK_COUNT,
        "options": options,
        "prefsBounds": prefs_bounds,
        "usedPreferences": RANK_COUNT,
        "modules": MODULES,
        "email": "bench@example.com",
        "tmax": 60,  # overwritten server-side for the sync path, same as prod
        "sameDay": False,
        "fixedDay": fixed_day,
    }
    run_req = rf.post("/dev/run_model/", data=body, content_type="application/json")
    started = time.monotonic()
    run_resp = views.run_model(run_req)
    wall = time.monotonic() - started

    if run_resp.status_code != 200:
        return {"n": n_students, "groups": groups_number, "error": f"run_model {run_resp.status_code}: {run_resp.data}"}
    d = run_resp.data
    placed = sum(g["size"] for g in d.get("groups", [])) if d.get("factible") else 0
    return {
        "n": n_students, "groups": groups_number, "band": f"{min_students}-{max_students}",
        "factible": d.get("factible"), "status": d.get("status"),
        "server_solve_time": d.get("solve_time"), "wall": wall, "placed": placed,
    }


def main():
    rf = RequestFactory()
    print(f"Production SYNC_SOLVE_TMAX_SECONDS = {SYNC_TMAX_SECONDS}s (total wall budget, post-fix)\n")
    sweep = [20, 30, 40, 50, 60, 75, 90, 100]
    for n in sweep:
        r = run_point(rf, n, seed=100 + n)
        if "error" in r:
            print(f"N={n:4d}  ERROR: {r['error']}")
            continue
        flag = "OK" if r["status"] == "OPTIMAL" else ("SLOW/CAPPED" if r["wall"] > SYNC_TMAX_SECONDS * 0.8 else "?")
        print(f"N={n:4d}  groups={r['groups']}  band={r['band']:>7s}  "
              f"status={r['status']:<10s}  factible={r['factible']}  "
              f"placed={r['placed']}/{n}  server_solve_time={r['server_solve_time']:.2f}s  "
              f"wall={r['wall']:.2f}s  [{flag}]")


if __name__ == "__main__":
    main()
