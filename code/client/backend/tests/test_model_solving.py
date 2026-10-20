"""
Tests for optimization_cpsat.py: building and solving the CP-SAT model --
feasible solves, infeasibility diagnosis, the sparse y[i, g] optimization,
and the precomputed_sets fast path.
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


def test_run_model_places_a_type_larger_than_one_group_within_a_single_section(params_factory, student_type_factory):
    # One section, one topic, one type of 10 students, upper_number=4 --
    # three groups of size <=4 comfortably fit all 10 (e.g. 4+3+3), and
    # since there's only one configured section every one of that type's
    # groups lands in it anyway, so this has to be feasible regardless of
    # how many sections exist. It's a minimal reproduction of a bug where
    # _add_constraints()'s per-type-per-section bound capped a type's
    # *total* headcount within a section to upper_number (one group's
    # worth) instead of the type's own headcount -- so any type larger
    # than a single group, placed into a section at all, made the whole
    # model spuriously infeasible the moment sections were configured.
    types = {"T0": student_type_factory("T0", students=10, preferences={"1": "Math"}, a={"Mon": 1})}
    params = params_factory(
        students_types=types,
        preferences={"Math": {"min": 0, "max": 5}},
        modules=["Mon"],
        groups_number=3, lower_number=1, upper_number=4,
    )
    sol = cpsat.run_model(params)

    assert sol["factible"] is True, sol["causes"]
    total_placed = sum(len(g["students"]) for g in sol["results"])
    assert total_placed == 10


def test_solve_full_uses_a_tight_relative_gap_not_a_loosened_one(params_factory, student_type_factory):
    # Regression test for the bug behind a Results-vs-Sensitivity-panel
    # discrepancy found while validating the demo screenshots: a 48-student
    # roster's Results panel showed 69% of students on their #1 choice,
    # while the Sensitivity panel's baseline (a separate, tight-gap solve
    # of the exact same request -- see sensitivity_report()'s docstring)
    # showed 93.8%. The cause was _solve_full() loosening CP-SAT's
    # relative_gap_limit to 0.01, even though the search_budget time limit
    # already bounds wall-clock with or without a loosened gap -- so the
    # 1% of objective slack it bought was pure downside, and was enough on
    # a realistic roster to let a solution with several students off their
    # #1 choice come back labeled OPTIMAL. Guard against it creeping back.
    types = {
        "T0": student_type_factory("T0", students=4, preferences={"1": "Math"}),
        "T1": student_type_factory("T1", students=4, preferences={"1": "Physics"}),
    }
    params = params_factory(
        students_types=types,
        preferences={"Math": {"min": 0, "max": 2}, "Physics": {"min": 0, "max": 2}},
        groups_number=2, lower_number=1, upper_number=10,
    )
    solver, ctx, status = cpsat._solve_full(params)

    assert solver.parameters.relative_gap_limit == 0.0


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


# -------------------- sensitivity analysis --------------------

def test_sensitivity_lists_nothing_when_no_family_changes_the_objective(params_factory, student_type_factory):
    types = {
        "T0": student_type_factory("T0", students=6, preferences={"1": "Math"}),
        "T1": student_type_factory("T1", students=6, preferences={"1": "Physics"}),
    }
    params = params_factory(
        students_types=types,
        preferences={"Math": {"min": 0, "max": 2}, "Physics": {"min": 0, "max": 2}},
        groups_number=2, lower_number=3, upper_number=9,
    )
    report = cpsat.sensitivity_report(params)

    assert report["available"] is True
    assert report["families"] == []
    assert report["unchecked"] == 0
    assert report["tested"] == report["total_families"]


def test_sensitivity_does_not_credit_a_family_for_a_baseline_that_was_not_optimal(params_factory, student_type_factory):
    def params():
        types = {
            "T0": student_type_factory("T0", students=6, preferences={"1": "Math"}),
            "T1": student_type_factory("T1", students=6, preferences={"1": "Physics"}),
        }
        return params_factory(
            students_types=types,
            preferences={"Math": {"min": 0, "max": 2}, "Physics": {"min": 0, "max": 2}},
            groups_number=2, lower_number=3, upper_number=9,
        )

    solution = _solution_of(params())
    first, second = list(solution)
    solution[first][:3], solution[second][:3] = solution[second][:3], solution[first][:3]
    assert cpsat._baseline_from_solution(params(), solution) is not None
    assert cpsat._baseline_from_solution(params(), solution)[2] > cpsat._baseline_from_solution(params(), _solution_of(params()))[2]
    report = cpsat.sensitivity_report(params(), solution)

    assert report["available"] is True
    assert report["families"] == []


def _binding_group_size_params(params_factory, student_type_factory):
    types = {
        "T0": student_type_factory("T0", students=4, preferences={"1": "Math"}),
        "T1": student_type_factory("T1", students=4, preferences={"1": "Math"}),
        "T2": student_type_factory("T2", students=4, preferences={"1": "Physics"}),
    }
    return params_factory(
        students_types=types,
        preferences={"Math": {"min": 1, "max": 1}, "Physics": {"min": 1, "max": 1}},
        groups_number=2, lower_number=1, upper_number=6,
    )


def test_sensitivity_reports_only_the_family_that_improves_the_objective(params_factory, student_type_factory):
    params = _binding_group_size_params(params_factory, student_type_factory)
    report = cpsat.sensitivity_report(params)

    assert [f["label"] for f in report["families"]] == ["Group size band (1-6 students per group)"]
    assert report["families"][0]["gain_points"] >= cpsat._SENSITIVITY_MIN_GAIN_POINTS
    assert report["families"][0]["family"] == {"kind": "group_size", "lo": params["lower_number"], "hi": params["upper_number"]}
    assert report["total_families"] == 5
    assert report["unchecked"] == 0


def test_sensitivity_gain_is_measured_in_objective_points(params_factory, student_type_factory):
    params = _binding_group_size_params(params_factory, student_type_factory)
    solution = _solution_of(_binding_group_size_params(params_factory, student_type_factory))
    model, ctx = cpsat._build_model(params)
    baseline = cpsat.objective_value(model, cpsat.solution_values(model, ctx, params, solution))

    relaxed, relaxed_ctx = cpsat._build_model(params, disabled={"group_size"})
    solver = cp_model.CpSolver()
    assert solver.Solve(relaxed) == cp_model.OPTIMAL
    expected = round((baseline - solver.ObjectiveValue()) / cpsat.BALANCE_CONSTANT, 2)

    report = cpsat.sensitivity_report(_binding_group_size_params(params_factory, student_type_factory), solution)
    group_size = next(f for f in report["families"] if f["label"].startswith("Group size band"))
    assert group_size["gain_points"] == expected


def test_relaxing_a_family_in_place_matches_building_without_it(params_factory, student_type_factory):
    params = _binding_group_size_params(params_factory, student_type_factory)
    model, ctx = cpsat._build_model(params)

    def optimum(m):
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        assert solver.Solve(m) == cp_model.OPTIMAL
        return solver.ObjectiveValue()

    for key, _label in cpsat._candidate_families(params):
        relaxed = model.clone()
        cpsat._relax_constraints(relaxed, ctx["family_constraints"].get(key, []))
        rebuilt, _ = cpsat._build_model(params, disabled={key})
        assert optimum(relaxed) == optimum(rebuilt), key


def _solution_of(params_for_solve):
    sol = cpsat.run_model(params_for_solve)
    return {g["group"]: [st["id"] for st in g["students"]] for g in sol["results"]}


def test_sensitivity_with_the_runs_own_solution_matches_solving_the_baseline(params_factory, student_type_factory):
    solution = _solution_of(_binding_group_size_params(params_factory, student_type_factory))
    fresh = _binding_group_size_params(params_factory, student_type_factory)
    with_solution = cpsat.sensitivity_report(fresh, solution)
    without = cpsat.sensitivity_report(_binding_group_size_params(params_factory, student_type_factory))

    assert with_solution["families"] == without["families"]


def test_sensitivity_ignores_a_solution_that_does_not_fit_the_model(params_factory, student_type_factory):
    solution = _solution_of(_binding_group_size_params(params_factory, student_type_factory))
    first_group = next(iter(solution))
    solution[first_group] = solution[first_group][:-1]
    report = cpsat.sensitivity_report(_binding_group_size_params(params_factory, student_type_factory), solution)

    assert report["available"] is True
    assert [f["label"] for f in report["families"]] == ["Group size band (1-6 students per group)"]


def test_family_constraint_tags_match_what_disabling_a_family_removes(params_factory, student_type_factory):
    types = {
        "T0": student_type_factory("T0", students=4, preferences={"1": "Math"}, a={"m1": 1, "m2": 1}),
        "T1": student_type_factory("T1", students=4, preferences={"1": "Physics"}, a={"m1": 1, "m2": 1}),
    }
    params = params_factory(
        students_types=types,
        preferences={"Math": {"min": 0, "max": 2}, "Physics": {"min": 0, "max": 2}},
        attributes={
            "gender": {
                "M": {"min": 0, "max": 5, "solo": False},
                "F": {"min": 2, "max": 5, "solo": True},
            }
        },
        students_types_attr={"T0": {"gender:M": 1, "gender:F": 0}, "T1": {"gender:M": 0, "gender:F": 1}},
        modules=["m1", "m2"], capacity={"m1": 6, "m2": 6},
        groups_number=2, lower_number=1, upper_number=6,
    )
    base_model, base_ctx = cpsat._build_model(params)
    base_count = len(base_model.Proto().constraints)

    families = cpsat._candidate_families(params)
    assert families
    for key, _label in families:
        dropped_model, _ = cpsat._build_model(params, disabled={key})
        removed = base_count - len(dropped_model.Proto().constraints)
        assert len(base_ctx["family_constraints"].get(key, [])) == removed, key


def test_dual_screen_flags_the_binding_family_and_falls_back_on_bad_input(params_factory, student_type_factory):
    from backend.sensitivity_lp import dual_screen

    params = _binding_group_size_params(params_factory, student_type_factory)
    model, ctx = cpsat._build_model(params)
    scores = dual_screen(model, ctx["family_constraints"])

    assert scores is not None
    assert scores["group_size"] > 0
    assert dual_screen(None, {}) is None


def test_dual_screen_works_on_a_roster_with_sections(params_factory, student_type_factory):
    from backend.sensitivity_lp import dual_screen

    types = {
        "T0": student_type_factory("T0", students=4, preferences={"1": "Math"}, a={"Mon": 1}),
        "T1": student_type_factory("T1", students=4, preferences={"1": "Math"}, a={"Mon": 1}),
        "T2": student_type_factory("T2", students=4, preferences={"1": "Physics"}, a={"Mon": 1}),
    }
    params = params_factory(
        students_types=types,
        preferences={"Math": {"min": 1, "max": 1}, "Physics": {"min": 1, "max": 1}},
        modules=["Mon"], groups_number=2, lower_number=1, upper_number=6,
    )
    model, ctx = cpsat._build_model(params)
    scores = dual_screen(model, ctx["family_constraints"])

    assert scores is not None
    assert scores["group_size"] > 0


# -------------------- optimality gap --------------------

class _FakeSolver:
    def __init__(self, objective, bound):
        self._objective, self._bound = objective, bound

    def ObjectiveValue(self):
        return self._objective

    def BestObjectiveBound(self):
        return self._bound


def test_optimality_gap_is_zero_for_a_proven_optimal_solve():
    assert cpsat._optimality_gap_pct(_FakeSolver(100.0, 40.0), cpsat.cp_model.OPTIMAL) == 0.0


def test_optimality_gap_for_a_time_limited_solve_is_relative_to_the_objective():
    # Best solution costs 1000, proven lower bound is 900 -> within 10%.
    assert cpsat._optimality_gap_pct(_FakeSolver(1000.0, 900.0), cpsat.cp_model.FEASIBLE) == 10.0


def test_run_model_reports_a_gap(params_factory, student_type_factory):
    types = {"T0": student_type_factory("T0", students=4, preferences={"1": "Math"})}
    params = params_factory(
        students_types=types, preferences={"Math": {"min": 0, "max": 1}},
        groups_number=1, lower_number=1, upper_number=10,
    )
    sol = cpsat.run_model(params)

    assert sol["factible"] is True
    assert sol["gap"] == 0.0
