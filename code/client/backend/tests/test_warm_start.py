"""Tests for warm_start.py."""
from ortools.sat.python import cp_model

import optimization_cpsat as cpsat
import warm_start


def _types(student_type_factory, n_types, per_type, topics, modules=None, avail=None):
    types = {}
    for t in range(n_types):
        tid = f"T{t}"
        a = {}
        if modules:
            a = {m: (1 if (avail is None or (t + k) % avail != 0) else 0) for k, m in enumerate(modules)}
            if not any(a.values()):
                a[modules[0]] = 1
        types[tid] = student_type_factory(
            tid, students=per_type, a=a,
            preferences={"1": topics[t % len(topics)], "2": topics[(t + 1) % len(topics)]},
        )
    return types


def _attrs():
    return {"level": {"A": {"min": 1, "max": 6, "solo": False}, "B": {"min": 1, "max": 6, "solo": False}}}


def _attr_matrix(types):
    return {tid: {"level:A": 1 if n % 2 == 0 else 0, "level:B": 1 if n % 2 else 0}
            for n, tid in enumerate(sorted(types))}


def _check_hint(params):
    model, ctx = cpsat._build_model(params)
    hint = warm_start.feasible_hint(model, ctx, params)
    assert hint is not None
    assert len(hint) == len(model.Proto().variables)
    for idx, val in hint.items():
        model.AddHint(model.GetIntVarFromProtoIndex(idx), val)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 20
    solver.parameters.num_search_workers = 1
    solver.parameters.fix_variables_to_their_hinted_value = True
    status = solver.Solve(model)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    return model, hint, solver


def test_hint_is_a_feasible_complete_solution_without_sections(params_factory, student_type_factory):
    topics = ["Math", "Physics", "Art"]
    types = _types(student_type_factory, 6, 4, topics)
    params = params_factory(
        students_types=types, attributes=_attrs(), students_types_attr=_attr_matrix(types),
        preferences={t: {"min": 1, "max": 3} for t in topics},
        groups_number=4, lower_number=5, upper_number=7,
    )
    _check_hint(params)


def test_hint_respects_section_availability_and_capacity(params_factory, student_type_factory):
    topics = ["Math", "Physics"]
    modules = ["Mon", "Tue", "Wed"]
    types = _types(student_type_factory, 9, 4, topics, modules=modules, avail=3)
    params = params_factory(
        students_types=types, attributes=_attrs(), students_types_attr=_attr_matrix(types),
        preferences={t: {"min": 0, "max": 6} for t in topics},
        modules=modules, capacity={"Mon": 14, "Tue": 14, "Wed": 14},
        groups_number=6, lower_number=5, upper_number=7,
    )
    model, ctx = cpsat._build_model(params)
    hint = warm_start.feasible_hint(model, ctx, params)
    assert hint is not None
    placed = {d: 0 for d in modules}
    for (i, g), var in ctx["y"].items():
        n = hint[var.Index()]
        for d in modules:
            if g in ctx["G_d"][d]:
                assert n == 0 or int(types[i]["a"][d]) == 1, "student placed in a section they cannot attend"
                placed[d] += n
    cap = warm_start.get_min_capacity(params)
    for d in modules:
        assert placed[d] <= cap[d]
    assert sum(placed.values()) == sum(t["students"] for t in types.values())


def test_hint_objective_is_the_models_objective(params_factory, student_type_factory):
    topics = ["Math", "Physics"]
    types = _types(student_type_factory, 4, 4, topics)
    params = params_factory(
        students_types=types, preferences={t: {"min": 1, "max": 2} for t in topics},
        groups_number=2, lower_number=7, upper_number=9,
    )
    model, hint, _solver = _check_hint(params)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    assert solver.Solve(model) == cp_model.OPTIMAL
    assert warm_start.objective_value(model, hint) >= solver.ObjectiveValue()


def _same_day_params(params_factory, student_type_factory, **extra):
    topics = ["Math", "Physics", "Art", "Music"]
    modules = ["Mon", "Tue"]
    types = _types(student_type_factory, 8, 3, topics, modules=modules)
    kwargs = dict(
        students_types=types, preferences={t: {"min": 1, "max": 2} for t in topics},
        modules=modules, groups_number=4, lower_number=5, upper_number=7, same_day=True,
        capacity={"Mon": 20, "Tue": 20},
    )
    kwargs.update(extra)
    return params_factory(**kwargs), topics, modules


def _topic_sections(ctx, hint, topics, modules):
    found = {p: set() for p in topics}
    for d in modules:
        for p in topics:
            if any(hint[ctx["w"][g].Index()] for g in ctx["G_td"][p, d]):
                found[p].add(d)
    return found


def test_same_day_hint_runs_each_topic_in_a_single_section(params_factory, student_type_factory):
    params, topics, modules = _same_day_params(params_factory, student_type_factory)
    model, ctx = cpsat._build_model(params)
    hint = warm_start.feasible_hint(model, ctx, params)
    assert hint is not None
    for p, ds in _topic_sections(ctx, hint, topics, modules).items():
        assert len(ds) <= 1, f"{p} runs in {ds}"


def test_same_day_hint_respects_fixed_day(params_factory, student_type_factory):
    params, topics, modules = _same_day_params(
        params_factory, student_type_factory, fixed_day={"Mon": {"Math": True, "Physics": True}})
    model, ctx = cpsat._build_model(params)
    hint = warm_start.feasible_hint(model, ctx, params)
    assert hint is not None
    found = _topic_sections(ctx, hint, topics, modules)
    assert "Mon" not in found["Math"] and "Mon" not in found["Physics"]


def test_same_day_hint_uses_at_most_used_preferences_topics(params_factory, student_type_factory):
    params, topics, modules = _same_day_params(
        params_factory, student_type_factory, used_preferences=3, groups_number=4)
    model, ctx = cpsat._build_model(params)
    hint = warm_start.feasible_hint(model, ctx, params)
    assert hint is not None
    used = [p for p, ds in _topic_sections(ctx, hint, topics, modules).items() if ds]
    assert len(used) <= 3


def test_hint_declines_when_the_roster_does_not_fit_the_group_band(params_factory, student_type_factory):
    topics = ["Math"]
    types = _types(student_type_factory, 2, 4, topics)
    params = params_factory(
        students_types=types, preferences={"Math": {"min": 0, "max": 5}},
        groups_number=4, lower_number=3, upper_number=5,
    )
    model, ctx = cpsat._build_model(params)
    assert warm_start.feasible_hint(model, ctx, params) is None


def test_solve_full_still_solves_when_the_heuristic_fails(params_factory, student_type_factory, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("heuristic bug")
    monkeypatch.setattr(cpsat, "feasible_hint", boom)
    params, _topics, _modules = _same_day_params(params_factory, student_type_factory)
    sol = cpsat.run_model(params)
    assert sol["factible"] is True


def test_unverified_hint_is_identical_to_the_verified_one(params_factory, student_type_factory):
    topics = ["Math", "Physics", "Art"]
    types = _types(student_type_factory, 6, 4, topics)
    params = params_factory(
        students_types=types, attributes=_attrs(), students_types_attr=_attr_matrix(types),
        preferences={t: {"min": 1, "max": 3} for t in topics},
        groups_number=4, lower_number=5, upper_number=7,
    )
    model, ctx = cpsat._build_model(params)
    assert warm_start.feasible_hint(model, ctx, params, verify=False) == warm_start.feasible_hint(model, ctx, params)


def test_solution_values_accepts_a_feasible_assignment_and_rejects_a_broken_one(params_factory, student_type_factory):
    topics = ["Math", "Physics", "Art"]
    types = _types(student_type_factory, 6, 4, topics)
    params = params_factory(
        students_types=types, attributes=_attrs(), students_types_attr=_attr_matrix(types),
        preferences={t: {"min": 1, "max": 3} for t in topics},
        groups_number=4, lower_number=5, upper_number=7,
    )
    model, ctx = cpsat._build_model(params)
    hint = warm_start.feasible_hint(model, ctx, params)
    pools = {i: list(types[i]["students_list"]) for i in types}
    groups = {}
    for (i, g), var in ctx["y"].items():
        for _ in range(hint[var.Index()]):
            groups.setdefault(g, []).append(pools[i].pop())

    assert warm_start.solution_values(model, ctx, params, groups) == hint

    missing = {g: list(ids) for g, ids in groups.items()}
    missing[next(iter(missing))].pop()
    assert warm_start.solution_values(model, ctx, params, missing) is None

    duplicated = {g: list(ids) for g, ids in groups.items()}
    first, second = list(duplicated)[:2]
    duplicated[second][0] = duplicated[first][0]
    assert warm_start.solution_values(model, ctx, params, duplicated) is None

    assert warm_start.solution_values(model, ctx, params, {"no such group": ["T0_s0"]}) is None
