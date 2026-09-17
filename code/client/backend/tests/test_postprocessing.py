"""
Tests for the postprocessing step: optimization_cpsat.assign_students()
(expanding a solved type-count back into real student records, and its
students_list-mutation guard) and run_model()'s results shaping.
"""
import pytest

import optimization_cpsat as cpsat


class _FakeSolver:
    """
    Stand-in for a real CpSolver for assign_students() unit tests. Real
    usage is `solver.Value(y[i, student_type_name])` where y[...] is a
    CP-SAT IntVar; here y maps each (type, group) pair to itself, so this
    fake just looks the pair straight up in a plain dict of solved values.
    """
    def __init__(self, values_by_pair):
        self._values = values_by_pair

    def Value(self, pair_key):
        return self._values[pair_key]


# -------------------- assign_students() --------------------

def test_assign_students_expands_type_count_into_real_student_records():
    students_dict = {f"T0_s{i}": {"id": f"T0_s{i}"} for i in range(5)}
    students_types = {
        "T0": {"id": "T0", "students_list": [f"T0_s{i}" for i in range(5)]},
    }
    y = {("T0", "GroupA"): ("T0", "GroupA")}
    solver = _FakeSolver({("T0", "GroupA"): 3})

    result = cpsat.assign_students(students_dict, students_types, "GroupA", solver, y, T=["T0"])

    assert len(result) == 3
    assert all(r["id"].startswith("T0_s") for r in result)
    # The 3 assigned students were popped off the type's remaining pool.
    assert len(students_types["T0"]["students_list"]) == 2


def test_assign_students_consumes_pool_across_successive_groups():
    # Mirrors how run_model() actually calls this: once per group, in
    # sequence, against the same students_types/students_list.
    students_dict = {f"T0_s{i}": {"id": f"T0_s{i}"} for i in range(5)}
    students_types = {"T0": {"id": "T0", "students_list": [f"T0_s{i}" for i in range(5)]}}
    y = {("T0", "GroupA"): "a", ("T0", "GroupB"): "b"}
    solver = _FakeSolver({"a": 3, "b": 2})

    group_a = cpsat.assign_students(students_dict, students_types, "GroupA", solver, y, T=["T0"])
    group_b = cpsat.assign_students(students_dict, students_types, "GroupB", solver, y, T=["T0"])

    assert len(group_a) == 3
    assert len(group_b) == 2
    # Every student was placed exactly once, none left over, none duplicated.
    assigned_ids = {s["id"] for s in group_a} | {s["id"] for s in group_b}
    assert assigned_ids == set(students_dict.keys())
    assert students_types["T0"]["students_list"] == []


def test_assign_students_raises_when_pool_is_exhausted():
    # Direct test of the mutation guard added this session: calling
    # assign_students() again against an already-consumed students_types
    # (e.g. reusing one across two independent run_model() calls) must
    # raise loudly instead of silently returning too few/wrong students.
    students_dict = {"T0_s0": {"id": "T0_s0"}}
    students_types = {"T0": {"id": "T0", "students_list": ["T0_s0"]}}
    y = {("T0", "GroupA"): "a"}
    solver = _FakeSolver({"a": 2})  # solution wants 2, only 1 left

    with pytest.raises(RuntimeError, match="only 1 student"):
        cpsat.assign_students(students_dict, students_types, "GroupA", solver, y, T=["T0"])


def test_assign_students_treats_missing_sparse_pair_as_zero():
    # y is sparse (see _build_model()'s Vars section) -- a (type, group)
    # pair that was never structurally eligible simply isn't a key in y at
    # all, and assign_students() must treat that exactly like "0 students",
    # not raise a KeyError.
    students_dict = {"T0_s0": {"id": "T0_s0"}}
    students_types = {"T0": {"id": "T0", "students_list": ["T0_s0"]}}
    y = {}  # T0 was never eligible for GroupA
    solver = _FakeSolver({})

    result = cpsat.assign_students(students_dict, students_types, "GroupA", solver, y, T=["T0"])

    assert result == []
    assert students_types["T0"]["students_list"] == ["T0_s0"]


# -------------------- run_model()'s results shaping --------------------

def test_run_model_assigns_each_student_exactly_once(params_factory, student_type_factory):
    types = {
        "T0": student_type_factory("T0", students=5, preferences={"1": "Math"}),
        "T1": student_type_factory("T1", students=5, preferences={"1": "Physics"}),
    }
    params = params_factory(
        students_types=types,
        preferences={"Math": {"min": 0, "max": 3}, "Physics": {"min": 0, "max": 3}},
        groups_number=4, lower_number=1, upper_number=6,
    )
    expected_ids = set(params["students"].keys())

    sol = cpsat.run_model(params)

    assert sol["factible"] is True
    assigned_ids = [s["id"] for group in sol["results"] for s in group["students"]]
    assert sorted(assigned_ids) == sorted(expected_ids)
    assert len(assigned_ids) == len(set(assigned_ids)), "a student was assigned to more than one group"


def test_run_model_leaves_students_types_pool_fully_consumed(params_factory, student_type_factory):
    types = {"T0": student_type_factory("T0", students=6, preferences={"1": "Math"})}
    params = params_factory(
        students_types=types,
        preferences={"Math": {"min": 0, "max": 3}},
        groups_number=2, lower_number=1, upper_number=6,
    )
    sol = cpsat.run_model(params)

    assert sol["factible"] is True
    assert params["students_types"]["T0"]["students_list"] == []


def test_run_model_infeasible_never_calls_assign_students(params_factory, student_type_factory, monkeypatch):
    calls = []
    monkeypatch.setattr(cpsat, "assign_students", lambda *a, **kw: calls.append(1) or [])

    types = {"T0": student_type_factory("T0", students=10, preferences={"1": "Math"})}
    params = params_factory(
        students_types=types,
        preferences={"Math": {"min": 0, "max": 5}},
        groups_number=1, lower_number=1, upper_number=2,
    )
    sol = cpsat.run_model(params)

    assert sol["factible"] is False
    assert calls == []
