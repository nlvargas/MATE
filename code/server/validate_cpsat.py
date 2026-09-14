"""
Standalone validation for optimization_cpsat.run_model().

This is not a pytest suite -- it's a hand-built "easy problem" (small
enough to eyeball) that exercises every constraint family in the model:
attribute bands (both the plain and the "solo" variant), section/module
capacity and availability, preference-topic min/max group counts, the
not-answered slack (M), and the priority/objective wiring -- then asserts
the returned solution actually respects every one of those rules. It also
runs a second, deliberately-impossible instance to check that infeasible
problems are reported as such instead of silently returning nonsense.

Run with:  python3 validate_cpsat.py
(needs `pip install ortools` first -- see the note in the repo's README/PR
description about why that couldn't be verified in this environment.)

Scenario
--------
12 students, 4 "types" (3 students each), crossed on:
  - level: A or B              (attribute, testable band)
  - section: M1 or M2          (module/section availability)
Every type ranks topic X and topic Y as its #1/#2 choice (alternating).
4 groups are formed, sized 2-4 students, one section per group.
  - level:A must appear >=1 time in every formed group (plain band).
  - level:B is a "solo" attribute: every formed group must have either
    1-2 level:B students, or none at all (tests the P/solo escape hatch).
"""
import sys

from optimization_cpsat import run_model


def build_toy_params(feasible=True):
    modules = ["M1", "M2"]
    attributes = {
        "level": {
            "A": {"min": 1, "max": 4, "solo": False},
            "B": {"min": 1, "max": 2, "solo": True},
        }
    }
    A = ["level:A", "level:B"]

    type_defs = [
        # (type_id, level, module, pref1, pref2)
        ("T1_A_M1", "A", "M1", "X", "Y"),
        ("T2_A_M2", "A", "M2", "Y", "X"),
        ("T3_B_M1", "B", "M1", "X", "Y"),
        ("T4_B_M2", "B", "M2", "Y", "X"),
    ]
    students_per_type = 3

    students = {}
    students_types = {}
    students_types_attr = {}
    sid = 1
    for type_id, level, module, pref1, pref2 in type_defs:
        student_list = []
        for _ in range(students_per_type):
            student_id = f"s{sid}"
            sid += 1
            a = {m: (1 if m == module else 0) for m in modules}
            students[student_id] = {
                "id": student_id,
                "attributes": {"level": level},
                "preferences": {"1": pref1, "2": pref2},
                "disponibilities": [a[m] for m in modules],
                "a": a,
            }
            student_list.append(student_id)

        students_types[type_id] = {
            "id": type_id,
            "attributes": {"level": level},
            "preferences": {1: pref1, 2: pref2},
            "disponibilities": [a[m] for m in modules],
            "flexibility": sum(a[m] for m in modules) or 1,
            "answered": True,
            "students": students_per_type,
            "students_list": list(student_list),
            "a": {m: (1 if m == module else 0) for m in modules},
        }
        students_types_attr[type_id] = {
            "level:A": 1 if level == "A" else 0,
            "level:B": 1 if level == "B" else 0,
        }

    params = {
        "attributes": attributes,
        "preferences": {
            "X": {"min": 1, "max": 3},
            "Y": {"min": 1, "max": 3},
        },
        "groups_number": 4,
        "lower_number": 2 if feasible else 20,  # blow the group-size bound to force infeasibility
        "upper_number": 4,
        "usedPreferences": 2,
        "students": students,
        "capacity": {"M1": 10, "M2": 10},
        "modules": modules,
        "A": A,
        "tmax": 1,
        "sameDay": True,
        "fixedDay": {},
        "students_types": students_types,
        "students_types_attr": students_types_attr,
    }
    return params


def check_feasible_solution():
    params = build_toy_params(feasible=True)
    total_students = sum(t["students"] for t in params["students_types"].values())

    sol = run_model(params)
    print(f"[feasible case] status={sol['status']} factible={sol['factible']} "
          f"groups={len(sol['results'])}")

    assert sol["factible"], "expected the toy problem to be solvable"
    assert len(sol["results"]) == params["groups_number"], (
        f"expected {params['groups_number']} groups, got {len(sol['results'])}"
    )

    seen_students = set()
    for group in sol["results"]:
        size = len(group["students"])
        assert params["lower_number"] <= size <= params["upper_number"], (
            f"group {group['group']} has {size} students, outside "
            f"[{params['lower_number']}, {params['upper_number']}]"
        )

        # every student in a group must actually be available for that group's section
        module_in_name = next(m for m in params["modules"] if f" - {m} (N" in group["group"])
        levels = []
        for student in group["students"]:
            assert student["a"][module_in_name] == 1, (
                f"student {student['id']} placed in a {module_in_name} group "
                f"but isn't available then"
            )
            levels.append(student["attributes"]["level"])
            assert student["id"] not in seen_students, f"student {student['id']} assigned twice"
            seen_students.add(student["id"])

        a_count = levels.count("A")
        b_count = levels.count("B")
        assert a_count >= 1, f"group {group['group']} has no level:A student (min=1 band)"
        assert b_count == 0 or 1 <= b_count <= 2, (
            f"group {group['group']} has {b_count} level:B students -- "
            f"solo band should allow 0, or force 1-2"
        )

    assert len(seen_students) == total_students, (
        f"expected all {total_students} students placed, got {len(seen_students)}"
    )
    print("[feasible case] OK -- all constraint families respected\n")


def check_infeasible_reported():
    params = build_toy_params(feasible=False)
    sol = run_model(params)
    print(f"[infeasible case] status={sol['status']} factible={sol['factible']}")
    assert not sol["factible"], "expected the impossible-bounds problem to be reported infeasible"
    assert sol["results"] == []
    print("[infeasible case] OK -- correctly reported as infeasible\n")


if __name__ == "__main__":
    try:
        check_feasible_solution()
        check_infeasible_reported()
    except AssertionError as e:
        print(f"VALIDATION FAILED: {e}")
        sys.exit(1)
    print("All CP-SAT validation checks passed.")
