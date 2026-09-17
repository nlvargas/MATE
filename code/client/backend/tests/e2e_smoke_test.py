"""
End-to-end smoke test: drives the real HTTP API (/upload/, /run_model/)
exactly the way the React frontend does -- same request shapes as
UploadTemplate.js/CreateGroups.js -- for a synthetic 50-student roster, and
checks the sync (in-request) CP-SAT path actually places every student.

Not a pytest test and not wired into CI on purpose: it needs a live server
to point at (local `manage.py runserver`, or a real deployed URL after a
`zappa update dev`), which CI can't provide -- CI's own coverage is this
directory's own test_model_solving.py/test_postprocessing.py (calls
optimization_cpsat.run_model() directly, no Django/HTTP in the loop) plus
code/server/tests/ for model_common.py. This is the complementary check:
is the actual API, as deployed, still wired together correctly end to
end. Run it yourself after any deploy:

    python3 backend/tests/e2e_smoke_test.py --base-url http://127.0.0.1:8000/dev
    python3 backend/tests/e2e_smoke_test.py --base-url https://<your-deployed-host>/dev

Needs `requests` (pip install -r backend/tests/requirements-e2e.txt) and openpyxl (already in requirements.txt).
"""
import argparse
import io
import json
import sys
import time

import requests
from openpyxl import Workbook

ATTRS = {"Gender": ["M", "F"], "Home university": ["A", "B"]}
MODULES = ["Mon 10:00", "Wed 15:00"]
TOPICS = ["Scheduling", "Vehicle routing", "Supply chain", "Data pipelines"]
RANK_COUNT = 2
N_STUDENTS = 50
GROUPS_NUMBER = 8   # same ratio as mate-demo-script.md's validated 48-student/8-group config
MIN_STUDENTS = 5
MAX_STUDENTS = 8    # widened by 1 over the demo's 5-7 band -- 50 doesn't divide as cleanly as 48


def build_roster_xlsx():
    """
    Column order must match backend/utils.py's create_students():
    ["student_fk"] + attributes + modules + [1..preferences_number].
    Shape (attribute/topic choices, skew) mirrors mate-demo-script.md so
    this exercises a realistic, already-validated configuration rather
    than an arbitrary one.
    """
    import random
    random.seed(7)

    wb = Workbook()
    ws = wb.active
    header = ["student_fk"] + list(ATTRS.keys()) + MODULES + list(range(1, RANK_COUNT + 1))
    ws.append(header)

    topic_weights = [4, 3, 2, 1]
    for i in range(N_STUDENTS):
        row = [f"s{i}"]
        for values in ATTRS.values():
            row.append(random.choice(values))
        row.extend([1, 1])  # available in both sections -- keeps this a clean placement test
        pool, weights = list(TOPICS), list(topic_weights)
        for _ in range(RANK_COUNT):
            pick = random.choices(pool, weights=weights, k=1)[0]
            idx = pool.index(pick)
            pool.pop(idx)
            weights.pop(idx)
            row.append(pick)
        ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def run(base_url):
    def fail(msg):
        print(f"FAIL: {msg}")
        sys.exit(1)

    print(f"Target: {base_url}")

    # -------------------- /upload/ --------------------
    roster = build_roster_xlsx()
    upload_resp = requests.post(
        f"{base_url}/upload/",
        data={
            "attributes": ",".join(ATTRS.keys()),
            "modules": ",".join(MODULES),
            "preferencesNumber": str(RANK_COUNT),
        },
        files={"file": ("e2e_roster.xlsx", roster, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        timeout=30,
    )
    if upload_resp.status_code != 200:
        fail(f"/upload/ returned {upload_resp.status_code}: {upload_resp.text[:500]}")
    upload_data = upload_resp.json()
    students = json.loads(upload_data["students"])
    options = json.loads(upload_data["a"])
    if len(students) != N_STUDENTS:
        fail(f"/upload/ parsed {len(students)} students, expected {N_STUDENTS}")
    print(f"OK  /upload/ parsed {len(students)} students")

    # -------------------- /run_model/ (same body shape as CreateGroups.js) --------------------
    bounds = {}
    for attr, values in ATTRS.items():
        for v in values:
            bounds[v] = {"min": 0, "max": N_STUDENTS, "solo": False}
    capacity = {m: N_STUDENTS for m in MODULES}
    fixed_day = {m: {p: False for p in TOPICS} for m in MODULES}
    prefs_bounds = {p: {"min": 0, "max": GROUPS_NUMBER} for p in TOPICS}

    body = {
        "attributes": list(ATTRS.keys()),
        "preferences": TOPICS,
        "groupsNumber": GROUPS_NUMBER,
        "minStudents": MIN_STUDENTS,
        "maxStudents": MAX_STUDENTS,
        "bounds": bounds,
        "students": students,
        "capacity": capacity,
        "preferencesNumber": RANK_COUNT,
        "options": options,
        "prefsBounds": prefs_bounds,
        "usedPreferences": RANK_COUNT,
        "modules": MODULES,
        "email": "e2e-smoke-test@example.com",
        "tmax": 60,
        "sameDay": False,
        "fixedDay": fixed_day,
    }

    started = time.monotonic()
    run_resp = requests.post(f"{base_url}/run_model/", json=body, timeout=60)
    elapsed = time.monotonic() - started
    if run_resp.status_code != 200:
        fail(f"/run_model/ returned {run_resp.status_code}: {run_resp.text[:500]}")
    result = run_resp.json()

    if result.get("queued"):
        fail(
            f"{N_STUDENTS} students went to the async/cluster path (queued=True) -- "
            "expected the sync path at this roster size. Check SYNC_SOLVE_MAX_STUDENTS."
        )
    if not result.get("factible"):
        fail(f"Solve came back infeasible: status={result.get('status')} causes={result.get('causes')}")

    groups = result.get("groups", [])
    placed = sum(len(g["students"]) for g in groups)
    print(f"OK  /run_model/ solved in {elapsed:.2f}s (server-reported: {result.get('solve_time'):.2f}s), "
          f"status={result.get('status')}, {len(groups)} groups, {placed} students placed")

    if placed != N_STUDENTS:
        fail(f"{placed} students placed, expected {N_STUDENTS}")
    for g in groups:
        size = len(g["students"])
        if not (MIN_STUDENTS <= size <= MAX_STUDENTS):
            fail(f"Group {g['group_name']!r} has {size} students, outside the [{MIN_STUDENTS},{MAX_STUDENTS}] band")

    print(f"PASS: all {N_STUDENTS} students placed across {len(groups)} groups, "
          f"each within [{MIN_STUDENTS},{MAX_STUDENTS}], sync path, {result.get('status')}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True,
                         help="e.g. http://127.0.0.1:8000/dev or https://<host>/dev")
    args = parser.parse_args()
    run(args.base_url.rstrip("/"))
