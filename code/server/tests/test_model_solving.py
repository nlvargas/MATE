"""
Tests for optimization_cpsat.py: building and solving the CP-SAT model --
feasible solves, infeasibility diagnosis, the sparse y[i, g] optimization,
the precomputed_sets fast path, and the warm-start hint.
"""
from ortools.sat.python import cp_model

import model_common as mc
import optimization_cpsat as cpsat


# -------------------- feasible solves --------------------

def test_run_model_places_every_student_when_feasible(params_factory, student_type_factory):
    types = {
        "T0": student_type_factory("T0", students=4, preferences={"1": "Math"}),
        "T1": student_type_factory("T1", students=4, preferences={"1": "Physics"}),
    }
    params = params_factory(
        students_types=types,
        preferences={"Math": {"min": 0, "max": 2}, "Physics": {"min": 0, "max": 2}},
        groups_number=2, lower_number=1, upper_number=10,
    )
    sol = cpsat.run_model(params)

    assert sol["factible"] is True
    assert sol["status"] in ("OPTIMAL", "FEASIBLE")
    assert sol["causes"] == []
    total_placed = sum(len(g["students"]) for g in sol["results"])
    assert total_placed == 8


def test_run_model_respects_group_size_band(params_factory, student_type_factory):
    types = {"T0": student_type_factory("T0", students=9, preferences={"1": "Math"})}
    params = params_factory(
        students_types=types,
        preferences={"Math": {"min": 0, "max": 5}},
        groups_number=3, lower_number=2, upper_number=4,
    )
    sol = cpsat.run_model(params)

    assert sol["factible"] is True
    for group in sol["results"]:
        assert 2 <= len(group["students"]) <= 4


def test_run_model_group_names_are_display_names_not_internal_keys(params_factory, student_type_factory):
    types = {"T0": student_type_factory("T0", students=2, preferences={"1": "Data Structures"})}
    params = params_factory(
        students_types=types,
        preferences={"Data Structures": {"min": 0, "max": 1}},
        groups_number=1, lower_number=1, upper_number=5,
    )
    sol = cpsat.run_model(params)

    assert sol["factible"] is True
    assert len(sol["results"]) == 1
    assert sol["results"][0]["group_name"] == "Data Structures"
    assert "Tema" not in sol["results"][0]["group_name"]


# -------------------- infeasibility diagnosis --------------------

def test_run_model_infeasible_reports_empty_results_and_causes(params_factory, student_type_factory):
    # 10 students, but only 1 group allowed of size at most 2 -- can never fit.
    types = {"T0": student_type_factory("T0", students=10, preferences={"1": "Math"})}
    params = params_factory(
        students_types=types,
        preferences={"Math": {"min": 0, "max": 5}},
        groups_number=1, lower_number=1, upper_number=2,
    )
    sol = cpsat.run_model(params)

    assert sol["factible"] is False
    assert sol["results"] == []
    assert sol["causes"], "expected at least one diagnosed cause"
    assert all(isinstance(c, str) for c in sol["causes"])
    # priority is still computed/returned even on the infeasible path.
    assert "T0" in sol["priority"]


def test_find_infeasibility_causes_identifies_the_specific_offending_bound(params_factory, student_type_factory):
    # A "solo"-style attribute bound that can't be met is the injected
    # infeasibility; group size/count/section are all otherwise generous,
    # so the diagnosis should point specifically at the attribute bound.
    types = {
        "T0": student_type_factory("T0", students=17, preferences={"1": "Math"}),
    }
    students_types_attr = {"T0": {"gender:M": 1}}
    params = params_factory(
        students_types=types,
        attributes={"gender": {"M": {"min": 5, "max": 999, "solo": False}}},
        preferences={"Math": {"min": 0, "max": 8}},
        groups_number=8, lower_number=1, upper_number=10,
        students_types_attr=students_types_attr,
    )
    causes = cpsat.find_infeasibility_causes(params)

    assert causes
    assert any("gender" in c and "M" in c for c in causes)


def test_disabling_a_family_can_turn_an_infeasible_model_feasible(params_factory, student_type_factory):
    # groups_number=5 is impossible to hit exactly (only 1 group's worth of
    # students exist and upper_number cap prevents spreading thin), so the
    # full model is infeasible -- but with that family disabled it must
    # become solvable, since it's the only bound in the way.
    types = {"T0": student_type_factory("T0", students=4, preferences={"1": "Math"})}
    params = params_factory(
        students_types=types,
        preferences={"Math": {"min": 0, "max": 10}},
        groups_number=5, lower_number=1, upper_number=10,
    )
    status_with = cpsat._solve_status(params, frozenset(), 5.0)
    status_without = cpsat._solve_status(params, frozenset({"groups_number"}), 5.0)

    assert status_with == cp_model.INFEASIBLE
    assert status_without in (cp_model.OPTIMAL, cp_model.FEASIBLE)


# -------------------- sparse y[i, g] --------------------

def test_sparse_y_only_creates_eligible_type_section_pairs(params_factory, student_type_factory):
    t0 = student_type_factory("T0", students=1, preferences={"1": "Math"}, a={"mod1": 1, "mod2": 0})
    params = params_factory(
        students_types={"T0": t0},
        preferences={"Math": {"min": 0, "max": 2}},
        modules=["mod1", "mod2"],
        groups_number=1, upper_number=5,
    )
    _model, ctx = cpsat._build_model(params)
    y = ctx["y"]

    mod1_groups = ctx["G_d"]["mod1"]
    mod2_groups = ctx["G_d"]["mod2"]
    assert all(("T0", g) in y for g in mod1_groups)
    # T0 is NOT available for mod2 -- no variable should exist for those pairs.
    assert all(("T0", g) not in y for g in mod2_groups)


def test_precomputed_sets_matches_recomputed_sets(params_factory, student_type_factory):
    types = {
        "T0": student_type_factory("T0", students=3, preferences={"1": "Math"}, a={"mod1": 1}),
        "T1": student_type_factory("T1", students=2, preferences={"1": "Physics"}, a={"mod1": 1}),
    }
    params = params_factory(
        students_types=types,
        preferences={"Math": {"min": 0, "max": 2}, "Physics": {"min": 0, "max": 2}},
        modules=["mod1"], groups_number=2, upper_number=10,
    )
    G, G_t, G_d, G_td = mc.preprocessing(params)
    priority = mc.compute_priority(params["students_types"], G_t)
    precomputed = (G, G_t, G_d, G_td, priority)

    model_a, ctx_a = cpsat._build_model(params)
    model_b, ctx_b = cpsat._build_model(params, precomputed_sets=precomputed)

    assert set(ctx_a["y"].keys()) == set(ctx_b["y"].keys())
    assert ctx_a["G"] == ctx_b["G"]
    proto_a, proto_b = model_a.Proto(), model_b.Proto()
    assert len(proto_a.variables) == len(proto_b.variables)
    assert len(proto_a.constraints) == len(proto_b.constraints)


# -------------------- warm-start hint --------------------

def test_greedy_hint_never_exceeds_group_capacity(params_factory, student_type_factory):
    types = {
        "T0": student_type_factory("T0", students=6, preferences={"1": "Math"}, a={"mod1": 1}),
        "T1": student_type_factory("T1", students=6, preferences={"1": "Math"}, a={"mod1": 1}),
    }
    params = params_factory(
        students_types=types,
        preferences={"Math": {"min": 0, "max": 2}},
        modules=["mod1"], groups_number=2, upper_number=5,
    )
    _model, ctx = cpsat._build_model(params)
    y_hint, w_hint = cpsat._greedy_hint(params, ctx["G"], ctx["T"], ctx["G_t"], ctx["G_d"], ctx["G_td"])

    fill_per_group = {}
    for (i, g), count in y_hint.items():
        fill_per_group[g] = fill_per_group.get(g, 0) + count
    for g, total in fill_per_group.items():
        assert total <= params["upper_number"]


def test_greedy_hint_only_places_students_in_available_sections(params_factory, student_type_factory):
    t0 = student_type_factory("T0", students=3, preferences={"1": "Math"}, a={"mod1": 1, "mod2": 0})
    params = params_factory(
        students_types={"T0": t0},
        preferences={"Math": {"min": 0, "max": 2}},
        modules=["mod1", "mod2"], groups_number=2, upper_number=10,
    )
    _model, ctx = cpsat._build_model(params)
    y_hint, _w_hint = cpsat._greedy_hint(params, ctx["G"], ctx["T"], ctx["G_t"], ctx["G_d"], ctx["G_td"])

    mod2_groups = set(ctx["G_d"]["mod2"])
    assert not any(g in mod2_groups for (_i, g) in y_hint)
