"""
Shared test scaffolding for code/client/backend's optimization_cpsat.py
tests: builds the same fixtures code/server/tests/conftest.py does, kept
as an independent copy rather than imported from there -- code/client and
code/server are two separately deployed projects that never import each
other's code, only ever communicating by submitting a job to the cluster
over SSH (see model_common.py's module docstring). code/client/backend
(where optimization_cpsat.py and its bare `from model_common import ...`
live) and code/client (where this app's own copy of model_common.py
lives, right next to manage.py) go on sys.path so tests can `import
optimization_cpsat` / trigger its `from model_common import ...` the same
bare-name way the real Django app does at runtime, without any Django
settings/app registry needing to be spun up.
"""
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_TESTS_DIR)
_CLIENT_DIR = os.path.dirname(_BACKEND_DIR)
for _dir in (_CLIENT_DIR, _BACKEND_DIR):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)

import pytest


def make_student_type(tid, students=1, flexibility=1, answered=True, preferences=None, a=None,
                       students_list=None):
    """
    Build one "student type" dict -- students_types[tid] everywhere in the
    solver -- with sane defaults for fields a test doesn't care about.
    `a` maps module name -> "0"/"1"/0/1 (section availability), matching
    the real shape produced by this app's own create_students_types()
    (backend/utils.py).
    """
    preferences = preferences or {}
    a = a or {}
    if students_list is None:
        students_list = [f"{tid}_s{i}" for i in range(students)]
    return {
        "id": tid,
        "students": students,
        "flexibility": flexibility,
        "answered": answered,
        "preferences": dict(preferences),
        "a": dict(a),
        "students_list": list(students_list),
    }


def make_params(students_types, attributes=None, preferences=None, groups_number=2,
                 lower_number=1, upper_number=10, capacity=None, modules=None,
                 same_day=False, fixed_day=None, used_preferences=None,
                 students_types_attr=None, students=None):
    """
    Build a full `params` dict -- the shape create_parms() (this
    directory's own backend/utils.py) produces from an uploaded roster --
    directly from a {type_id: student_type_dict} mapping, so tests can
    construct exactly the roster shape they need without going through a
    spreadsheet upload.

    Fills in `students` (the per-student roster _build_model()'s
    preprocessing/postprocessing actually reads, e.g. for
    get_min_capacity()'s section-availability counts and
    assign_students()'s dict lookups) by expanding each type's
    `students_list` -- unless the caller passes a custom `students` dict,
    for tests that need per-student data types don't carry (e.g. distinct
    `attributes`).
    """
    modules = modules or []
    preferences = preferences or {}
    attributes = attributes or {}
    if capacity is None:
        capacity = {m: 999 for m in modules}
    if students_types_attr is None:
        students_types_attr = {tid: {} for tid in students_types}
    if used_preferences is None:
        used_preferences = len(preferences)
    if students is None:
        students = {}
        for tid, st in students_types.items():
            for sid in st["students_list"]:
                students[sid] = {
                    "id": sid,
                    "attributes": {},
                    "preferences": st["preferences"],
                    "disponibilities": [st["a"].get(m, 0) for m in modules],
                    "a": dict(st["a"]),
                }
    return {
        "attributes": attributes,
        "preferences": preferences,
        "groups_number": groups_number,
        "lower_number": lower_number,
        "upper_number": upper_number,
        "students": students,
        "capacity": capacity,
        "modules": modules,
        "A": [f"{attr}:{val}" for attr in attributes for val in attributes[attr]],
        "tmax": 2,
        "sameDay": same_day,
        "fixedDay": fixed_day or {},
        "students_types": students_types,
        "students_types_attr": students_types_attr,
        "usedPreferences": used_preferences,
    }


@pytest.fixture
def student_type_factory():
    return make_student_type


@pytest.fixture
def params_factory():
    return make_params
