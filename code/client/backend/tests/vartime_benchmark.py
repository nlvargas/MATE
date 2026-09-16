"""
Ad-hoc benchmark (not part of the test suite): for a given roster size N
and target group count, builds the real CP-SAT model (production shape --
greedy hint applied, same solver settings run_model() uses) and times how
long it takes to solve, alongside the model's actual variable count.

Appends one CSV row per invocation to backend/tests/vartime_results2.csv so
a sweep can be run as several separate calls (each solve can take up to
the cap below) without losing earlier points.

Run from code/client:
    DJANGO_SETTINGS_MODULE=project.settings python3 backend/tests/vartime_benchmark.py N GROUPS [CAP_SECONDS]
"""
import csv
import io
import os
import random
import sys
import time

sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")

import django
django.setup()

from django.test import RequestFactory
from openpyxl import Workbook
from ortools.sat.python import cp_model

from backend import views
from backend.utils import create_parms
from backend.optimization_cpsat import _build_model, _greedy_hint

ATTRS = {"A1": ["a", "b", "c"], "A2": ["x", "y", "z"], "A3": ["p", "q", "r"]}
MODULES = ["Mon 10:00", "Wed 15:00", "Fri 09:00"]
TOPICS = [f"Topic{i}" for i in range(8)]
RANK_COUNT = 3
RESULTS_CSV = os.path.join(os.path.dirname(__file__), "vartime_results2.csv")


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
        avail = [1 if random.random() < 0.8 else 0 for _ in MODULES]
        if not any(avail):
            # Guarantee every student is available for at least one
            # configured section -- an all-zero row makes that student's
            # type structurally unplaceable (y[i, g] never gets created
            # for any g), which makes the *whole* model infeasible
            # regardless of problem size. Real deployments would reject
            # or flag such a row; this benchmark is about solve-time
            # scaling, not that separate edge case.
            avail[random.randrange(len(MODULES))] = 1
        row += avail
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


def estimate_variables(params, G, T, G_t, G_d, G_td):
    """Python port of frontend/src/estimateModelSize.js's formula, for an
    apples-to-apples check of the pre-solve estimate against reality."""
    students_types = params["students_types"]
    modules = params["modules"]
    types_count = len(T)
    groups_count = len(G)
    attr_values_count = len(params["A"])
    solo_count = 0  # benchmark roster never marks a bound "solo"
    if modules:
        total_frac = 0.0
        for i in T:
            avail = sum(int(students_types[i]["a"].get(d, 0)) for d in modules)
            total_frac += avail / len(modules)
        avg_frac = total_frac / max(1, types_count)
        y_est = round(types_count * groups_count * avg_frac)
        topic_section = len(params["preferences"]) * len(modules) + len(params["preferences"])
    else:
        y_est = types_count * groups_count
        topic_section = 0
    w = groups_count
    z = types_count + 1
    q = groups_count * attr_values_count
    p = groups_count * solo_count
    m = groups_count + 1
    return y_est + w + z + q + p + m + topic_section


def main():
    n_students = int(sys.argv[1])
    groups_number = int(sys.argv[2])
    cap_seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 100.0

    rf = RequestFactory()
    roster = build_roster_xlsx(n_students, seed=1000 + n_students)
    upload_req = rf.post("/dev/upload/", data={
        "attributes": ",".join(ATTRS.keys()),
        "modules": ",".join(MODULES),
        "preferencesNumber": str(RANK_COUNT),
        "file": roster,
    })
    upload_resp = views.upload(upload_req)
    assert upload_resp.status_code == 200, upload_resp.data
    import json
    students = json.loads(upload_resp.data["students"])
    options = json.loads(upload_resp.data["a"])

    min_students = max(1, n_students // groups_number - 1)
    max_students = max(1, -(-n_students // groups_number) + 1)

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
        "tmax": 60,
        "sameDay": False,
        "fixedDay": fixed_day,
    }
    params = create_parms(body)

    model, ctx = _build_model(params, symmetry_break=False)
    y, w, G, T = ctx["y"], ctx["w"], ctx["G"], ctx["T"]
    G_t, G_d, G_td = ctx["G_t"], ctx["G_d"], ctx["G_td"]

    real_var_count = len(model.Proto().variables)
    est_var_count = estimate_variables(params, G, T, G_t, G_d, G_td)

    y_hint, w_hint = _greedy_hint(params, G, T, G_t, G_d, G_td)
    for (i, g) in y:
        model.AddHint(y[i, g], y_hint.get((i, g), 0))
    for g in G:
        model.AddHint(w[g], w_hint.get(g, 0))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = cap_seconds
    solver.parameters.relative_gap_limit = 0.01
    solver.parameters.num_search_workers = 8
    started = time.monotonic()
    status = solver.Solve(model)
    wall = time.monotonic() - started
    status_name = solver.StatusName(status)

    row = {
        "n_students": n_students, "groups_number": groups_number,
        "types_count": len(T), "groups_count": len(G),
        "real_var_count": real_var_count, "est_var_count": est_var_count,
        "wall_seconds": round(wall, 2), "status": status_name,
        "cap_seconds": cap_seconds,
    }
    print(row)

    file_exists = os.path.exists(RESULTS_CSV)
    with open(RESULTS_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


if __name__ == "__main__":
    main()
