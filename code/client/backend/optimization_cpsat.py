"""
CP-SAT (OR-Tools) implementation of the MATE group-assignment model.

This mirrors code/server/optimization.py's Gurobi model exactly: same sets,
variables, constraints and objective, translated 1:1 to Google OR-Tools'
CP-SAT solver. It's a drop-in replacement -- run_model(params) takes the
same params dict optimization.run_model() does and returns the same
{"results", "factible", "priority"} shape (plus "status" and "causes",
which are new and safe to ignore).

Kept as a separate module (instead of branching inside optimization.py) so
Gurobi stays available as a swap-in option later without pulling gurobipy
into the default open-source path. preprocessing()/get_min_capacity()/
compute_priority() live in model_common.py (no gurobipy dependency) and are
shared with optimization.py's Gurobi model, so the two backends can't drift
apart on how groups are named, how section capacity is computed, or how a
student type's preference ranking maps onto groups.

-------------------- Infeasibility diagnosis --------------------
When the full model is infeasible, find_infeasibility_causes() below runs a
classic "deletion filter" to find an irreducible infeasible subset (IIS)
over the model's *user-configurable* constraint families (group-size band,
attribute balance bounds, topic coverage bounds, section capacity, the
used-topics cap -- see _candidate_families()). It repeatedly re-solves the
model with one more family knocked out at a time, on a short time budget:
if the model is still infeasible without a family, that family wasn't
needed to explain the infeasibility and is dropped for good; if removing it
makes the model feasible, that family was essential and is kept. What's
left when every family has been tried once is a minimal set of bounds that,
together, can't be satisfied -- which is exactly what an interviewer means
by "why is this infeasible", translated into the same language the
Configure & run screen uses.

This intentionally does NOT use CP-SAT's model.AddAssumptions()/
solver.SufficientAssumptionsForInfeasibility() (mentioned as the "natural
next step" in an earlier version of this docstring): that path ties the
diagnosis to CP-SAT-specific literal-index bookkeeping, whereas the
deletion filter only needs "build this model variant and check its
status", so it works identically for the Gurobi backend too (see
optimization.py) with no solver-specific code at all -- consistent with
model_common.py's whole point of keeping the two backends from drifting
apart on how a "group" (and now a "cause") is defined. The cost is one
resolve per family instead of one; each resolve is capped at a few seconds
(_IIS_TRIAL_TIME_LIMIT_SECONDS) and only ever runs on the already-infeasible
path, never on a normal successful solve.

Structural constraints -- ones that define an auxiliary quantity (e.g.
Q[g, attr_key]) or that encode a fact about the data rather than a policy
choice (e.g. a student can only be placed in a section they marked
available) -- are never disabled; only bounds the Configure & run screen
actually lets the user set are candidates. fixedDay/sameDay restrictions
aren't covered by a family yet (out of scope for this pass) -- they show up
folded into whichever other family's resolve happens to also fail.
"""
import itertools
import time
from collections import defaultdict

from ortools.sat.python import cp_model

from model_common import (
    preprocessing, get_min_capacity, group_display_name, compute_priority, UNRANKED_PRIORITY,
)


BALANCE_CONSTANT = 1000  # K in K * (z_max + M_max) -- matches the Gurobi model's objective weight.
# UNRANKED_PRIORITY (priority assigned to a group that isn't among a student
# type's ranked preferences) now lives in model_common.py, shared with
# optimization.py, so the two backends can't quietly drift onto different
# values -- see compute_priority().

# Statuses that mean "there is a usable solution below", mirroring the Gurobi
# code's `factible = True if m.status in (2, 13) else False` (OPTIMAL, SUBOPTIMAL):
# OPTIMAL = proven optimal, FEASIBLE = solver hit a limit (time/gap) but still
# found and is returning a usable incumbent.
FACTIBLE_STATUSES = (cp_model.OPTIMAL, cp_model.FEASIBLE)

# Per-resolve time budget while hunting for infeasibility causes. Small on
# purpose: an UNSAT proof for a problem this size (<= SYNC_SOLVE_MAX_STUDENTS)
# is usually fast, and we may need one resolve per candidate family.
_IIS_TRIAL_TIME_LIMIT_SECONDS = 3.0
# One longer look, only for a trial whose first solve came back UNKNOWN
# (rare -- observed on models that are structurally similar to an already-
# confirmed-INFEASIBLE trial but happen to be harder to prove either way).
_IIS_TRIAL_RETRY_TIME_LIMIT_SECONDS = 10.0

# Hard ceiling on the whole deletion-filter search, wall-clock. Per-trial
# budgets above bound a single resolve, but UNKNOWN+retry on several
# families back-to-back can still add up; this stops the search partway
# through rather than letting a synchronous request hang. Any family not
# yet tested when the budget runs out is conservatively left un-reported
# (never confirmed necessary, so never claimed as a cause) -- see the
# early-exit check in find_infeasibility_causes().
_IIS_TOTAL_TIME_BUDGET_SECONDS = 15.0

# Whether _build_model() adds the lexicographic symmetry-breaking constraints
# (see the "Symmetry breaking" block inside _build_model()). Benchmarked
# against synthetic rosters of 150 and 400 students (25 and 60 groups) on
# 2026-09-09: it made every solve slower, not faster -- +45% at 150 students
# (3.2s -> 5.5s, still OPTIMAL) and +300%+ at 400 (29s OPTIMAL -> 124s, and
# it didn't even finish proving optimality, landing on FEASIBLE against the
# solve-time cap instead). CP-SAT already does its own symmetry detection
# internally, and the extra inequality chains apparently interfere with its
# search/LP relaxation more than they prune it. Left here (default off,
# never on any real request) as a documented dead end rather than deleted,
# in case a future, differently-shaped model benefits from it -- flip this
# to True locally to re-test, don't wire it back up to a request param.
_ENABLE_SYMMETRY_BREAKING = False


def assign_students(students_dict, students_types, student_type_name, solver, y, T):
    """Same as optimization.assign_students, reading CP-SAT values instead of Gurobi's .X.

    `y` is sparse now (see _build_model()'s Vars section) -- a type with no
    y[i, student_type_name] entry was never eligible for this group at all,
    which is exactly "0 students of this type ended up here", so it's
    treated the same as solver.Value(...) == 0 below.

    MUTATES students_types: student_type["students_list"].pop() below
    consumes a type's remaining student pool as it's assigned. Across one
    run_model() call's group-by-group results loop, that's exactly right
    -- the model's own "sum(y[i,g] for g in G) == students_types[i]['students']"
    constraint guarantees every one of a type's students gets popped
    exactly once, total, over all groups. It's only right ONCE, though:
    students_types (and the students_list lists inside it) must be freshly
    built for every independent run_model() call -- see optimization.py's
    assign_students() docstring for the failure mode this guards against.
    """
    students = []
    for i in T:
        sol = solver.Value(y[i, student_type_name]) if (i, student_type_name) in y else 0
        if sol > 0:
            student_type = students_types[i]
            if len(student_type["students_list"]) < sol:
                raise RuntimeError(
                    f"assign_students(): type {i!r} has only "
                    f"{len(student_type['students_list'])} student(s) left to assign, but "
                    f"the solution calls for {sol} in group {student_type_name!r}. This "
                    "usually means students_types was already consumed by an earlier "
                    "run_model() call -- build a fresh students_types for every "
                    "independent run_model() call."
                )
            for _ in range(sol):
                student = student_type["students_list"].pop()
                students.append(students_dict[student])
    return students


def _candidate_families(params):
    """
    The user-configurable constraint families find_infeasibility_causes()
    is allowed to test dropping, as (key, human-readable label) pairs. Keys
    are matched against the `disabled` set _build_model() takes; labels are
    what a person sees in the "why is this infeasible" list, so they're
    phrased to match the Configure & run screen's own wording rather than
    the model's internal variable names.
    """
    attr_bounds = params["attributes"]
    preferences_bounds = params["preferences"]
    modules = params["modules"]
    cap = get_min_capacity(params)
    lower_number = params["lower_number"]
    upper_number = params["upper_number"]
    groups_number = params["groups_number"]
    used_preferences = params["usedPreferences"]

    families = [
        ("group_size", f"Group size band ({lower_number}-{upper_number} students per group)"),
        ("groups_number", f"Target number of groups ({groups_number})"),
    ]
    for a in attr_bounds:
        for r in attr_bounds[a]:
            b = attr_bounds[a][r]
            if b.get("solo"):
                note = "no group may have none of this trait"
            else:
                note = f"{b['min']}-{b['max']} per group"
            families.append((f"attr:{a}:{r}", f"Balance bound for {a} = {r} ({note})"))
    for p in preferences_bounds:
        b = preferences_bounds[p]
        families.append((f"topic:{p}", f"Topic coverage bound for '{p}' ({b['min']}-{b['max']} groups)"))
    for d in modules:
        families.append((f"section:{d}", f"Section capacity for '{d}' ({cap[d]} seats)"))
    families.append(("used_preferences", f"Cap on topics MATE may use at once ({used_preferences})"))
    return families


def _build_model(params, disabled=frozenset(), symmetry_break=False, precomputed_sets=None):
    """
    Build the CP-SAT model for `params`. Identical to what run_model() has
    always solved when `disabled` is empty. `disabled` is a set of family
    keys (see _candidate_families()) whose constraints are left out --
    used only by find_infeasibility_causes() to test which user-configured
    bound(s) are responsible when the full model is infeasible.

    `symmetry_break` adds lexicographic ordering constraints over each
    family of interchangeable group slots (see _add_symmetry_breaking()
    below) -- an experimental, benchmark-only knob (see run_model()'s
    "_symmetry_break" param), off by default so normal requests are
    unaffected.

    `precomputed_sets`, if given, is a (G, G_t, G_d, G_td, priority) tuple
    to reuse instead of recomputing it via preprocessing()/compute_priority().
    Both depend only on `params`, never on `disabled` -- find_infeasibility_causes()
    computes them once and passes the same tuple into every deletion-filter
    trial's _build_model() call instead of silently rebuilding identical sets
    from scratch on each of the (up to len(_candidate_families(params)))
    resolves a single diagnosis run can do. run_model()'s normal (single
    solve) path omits this and lets _build_model() compute them itself, as
    before.

    The y[i, g] variable dict this builds is sparse when `modules` is set:
    a (type, group) pair is only created when the type marked itself
    available for that group's section, since it's otherwise structurally
    guaranteed to be 0 -- see the comment inside _build_vars() below for why
    and ctx["y"]'s callers (assign_students(), run_model()) for how a
    missing entry is handled the same as a variable pinned to 0.

    This function itself is just the old Params/Sets/Model/Vars/Constraints/
    Symmetry-breaking/Objective sections wired together -- each section
    below was moved, as-is with no logic changes, into its own
    _model_params()/_build_vars()/_add_constraints()/_add_symmetry_breaking()/
    _set_objective() helper. State flows between them via two plain dicts
    instead of the fully-inlined locals this function used to build
    directly: `mp` ("model params") from _model_params() carries the
    Params+Sets section's values, and `v` from _build_vars() carries the
    CP-SAT variable dicts (y, w, z, Q, P, ...).

    Returns (model, ctx) where ctx carries every piece run_model() and
    find_infeasibility_causes() need afterwards (variables, sets, priority).
    """
    mp = _model_params(params, precomputed_sets)

    # -------------------- Model --------------------
    model = cp_model.CpModel()

    v = _build_vars(model, mp)
    _add_constraints(model, mp, v, disabled)
    if symmetry_break:
        _add_symmetry_breaking(model, mp, v)
    _set_objective(model, mp, v)

    ctx = {
        "y": v["y"], "w": v["w"], "G": mp["G"], "T": mp["T"], "priority": mp["priority"],
        "students_types": mp["students_types"],
        "G_t": mp["G_t"], "G_d": mp["G_d"], "G_td": mp["G_td"],
    }
    return model, ctx


def _model_params(params, precomputed_sets):
    """
    _build_model()'s old Params + Sets sections, moved here unchanged: pull
    the plain scalars/dicts the model needs out of `params` (identical to
    optimization.run_model()'s own copy of this) and compute -- or, if
    `precomputed_sets` is given, reuse -- the sets preprocessing()/
    compute_priority() produce. Returned as one dict (`mp`) rather than a
    dataclass so _build_vars()/_add_constraints()/_add_symmetry_breaking()/
    _set_objective() below can each just pull out the few mp["..."] entries
    they need.
    """
    # -------------------- Params -------------------- (identical to optimization.run_model)
    attr_bounds = params["attributes"]
    preferences = list(params["preferences"].keys())
    groups_number = params["groups_number"]
    lower_number = params["lower_number"]
    upper_number = params["upper_number"]
    preferences_bounds = params["preferences"]
    used_preferences = params["usedPreferences"]
    cap = get_min_capacity(params)
    modules = params["modules"]
    students_types = params["students_types"]
    students_types_attr = params["students_types_attr"]
    not_answered_students_types = filter(
        lambda i: not students_types[i]["answered"], students_types
    )
    not_answered = [
        students_types[student_type]["id"] for student_type in not_answered_students_types
    ]

    # -------------------- Sets --------------------
    A = params["A"]
    D = [d for d in modules]
    T = list(students_types.keys())
    if precomputed_sets is not None:
        G, G_t, G_d, G_td, priority = precomputed_sets
    else:
        G, G_t, G_d, G_td = preprocessing(params)
        priority = compute_priority(students_types, G_t)

    total_by_type = {i: max(1, students_types[i]["students"]) for i in T}
    total_students = max(1, sum(students_types[i]["students"] for i in T))

    return {
        "attr_bounds": attr_bounds,
        "preferences": preferences,
        "groups_number": groups_number,
        "lower_number": lower_number,
        "upper_number": upper_number,
        "preferences_bounds": preferences_bounds,
        "used_preferences": used_preferences,
        "cap": cap,
        "modules": modules,
        "students_types": students_types,
        "students_types_attr": students_types_attr,
        "not_answered": not_answered,
        "A": A,
        "D": D,
        "T": T,
        "G": G,
        "G_t": G_t,
        "G_d": G_d,
        "G_td": G_td,
        "priority": priority,
        "total_by_type": total_by_type,
        "total_students": total_students,
        # A few constraints (sameDay/fixedDay, below) read params directly
        # rather than through a named mp[...] entry -- kept around for them.
        "params": params,
    }


def _build_vars(model, mp):
    """
    _build_model()'s old Vars section, moved here unchanged. Returned as
    one dict (`v`) for the same reason _model_params() returns `mp` as a
    dict -- _add_constraints()/_add_symmetry_breaking()/_set_objective()
    below each only need a few of these.
    """
    modules = mp["modules"]
    T, G, D, A = mp["T"], mp["G"], mp["D"], mp["A"]
    students_types = mp["students_types"]
    upper_number = mp["upper_number"]
    total_by_type = mp["total_by_type"]
    total_students = mp["total_students"]
    preferences = mp["preferences"]

    # y[i, g] is sparse: a (type, group) pair is only structurally possible
    # if the type marked itself available for the section group g belongs
    # to (see the "sum(y[i, g] for g in G_d[d]) <= upper_number * a[i][d]"
    # constraint in _add_constraints() below -- before this change that was
    # the ONLY thing that forced an ineligible y[i, g] to 0, but CP-SAT
    # still had to create the variable, add it to every sum() it appears in
    # below, and propagate it down to 0 during presolve/search, for every
    # (type, group) combination -- most of them structurally dead on
    # arrival whenever there's more than one section. Skipping variable
    # creation for those pairs entirely is exactly as correct (the
    # constraint used to force sum(y[i,g])==0 for these g's; now there's
    # simply no y[i, g] term to sum) and yields a strictly smaller model.
    # Every place below that indexes y[i, g] for a (type, group) pair that
    # might not exist uses y.get((i, g), 0) instead of y[i, g] to account
    # for this -- a missing entry behaves exactly like a variable pinned to
    # 0, which is what it always was.
    # Q/P (right below) are NOT pruned the same way: they're indexed by
    # (group, attribute-value), and there's no structural reason a group
    # can't contain a student with any given attribute value -- only
    # section availability constrains who ends up where, so there's no
    # analogous "impossible" (group, attribute) pair to skip.
    if modules:
        G_d = mp["G_d"]
        group_section = {g: d for d, gs in G_d.items() for g in gs}
        y = {
            (i, g): model.NewIntVar(0, upper_number, f"y_{i}_{g}")
            for i in T for g in G
            if int(students_types[i]["a"][group_section[g]]) == 1
        }
    else:
        y = {(i, g): model.NewIntVar(0, upper_number, f"y_{i}_{g}") for i in T for g in G}
    w = {g: model.NewBoolVar(f"w_{g}") for g in G}
    z = {i: model.NewIntVar(0, UNRANKED_PRIORITY * total_by_type[i], f"z_{i}") for i in T}
    z_max = model.NewIntVar(0, UNRANKED_PRIORITY * total_students, "z_max")
    Q = {(g, a): model.NewIntVar(0, upper_number, f"Q_{g}_{a}") for g in G for a in A}
    P = {(g, a): model.NewBoolVar(f"P_{g}_{a}") for g in G for a in A}
    M = {g: model.NewIntVar(0, upper_number, f"M_{g}") for g in G}
    M_max = model.NewIntVar(0, upper_number, "M_max")
    u = {(p, d): model.NewBoolVar(f"u_{p}_{d}") for p in preferences for d in D}
    o = {p: model.NewBoolVar(f"o_{p}") for p in preferences}

    return {
        "y": y, "w": w, "z": z, "z_max": z_max,
        "Q": Q, "P": P, "M": M, "M_max": M_max, "u": u, "o": o,
    }


def _add_constraints(model, mp, v, disabled):
    """_build_model()'s old Constraints section, moved here unchanged."""
    T = mp["T"]
    G = mp["G"]
    D = mp["D"]
    modules = mp["modules"]
    students_types = mp["students_types"]
    students_types_attr = mp["students_types_attr"]
    not_answered = mp["not_answered"]
    preferences = mp["preferences"]
    preferences_bounds = mp["preferences_bounds"]
    used_preferences = mp["used_preferences"]
    attr_bounds = mp["attr_bounds"]
    cap = mp["cap"]
    G_t = mp["G_t"]
    G_d = mp["G_d"]
    G_td = mp["G_td"]
    priority = mp["priority"]
    groups_number = mp["groups_number"]
    lower_number = mp["lower_number"]
    upper_number = mp["upper_number"]
    params = mp["params"]

    y = v["y"]
    w = v["w"]
    z = v["z"]
    z_max = v["z_max"]
    Q = v["Q"]
    P = v["P"]
    M = v["M"]
    M_max = v["M_max"]
    u = v["u"]
    o = v["o"]

    for i in T:
        model.Add(sum(y.get((i, g), 0) for g in G) == students_types[i]["students"])

    # y is sparse (see _build_vars() above): only iterate pairs that
    # actually exist as variables instead of the full T x G product.
    for (i, g) in y:
        model.Add(y[i, g] <= upper_number * w[g])

    if "groups_number" not in disabled:
        model.Add(sum(w[g] for g in G) == groups_number)

    if "group_size" not in disabled:
        for g in G:
            model.Add(sum(y.get((i, g), 0) for i in T) >= lower_number * w[g])
            model.Add(sum(y.get((i, g), 0) for i in T) <= upper_number * w[g])

    if "used_preferences" not in disabled:
        model.Add(sum(o[p] for p in preferences) <= used_preferences)

    for g in G:
        model.Add(sum(y.get((i, g), 0) for i in not_answered) <= 1 + M[g])

    for g in G:
        model.Add(M_max >= M[g])

    for preference in preferences_bounds:
        if f"topic:{preference}" in disabled:
            continue
        if used_preferences == len(preferences):
            min_bound = int(preferences_bounds[preference]["min"])
            model.Add(sum(w[g] for g in G_t[str(preference)]) >= min_bound)
        max_bound = int(preferences_bounds[preference]["max"])
        model.Add(sum(w[g] for g in G_t[str(preference)]) <= max_bound)

    for i in T:
        model.Add(z[i] == sum(y.get((i, g), 0) * int(priority[i][g]) for g in G))

    for i in T:
        model.Add(z_max >= z[i])

    for a in attr_bounds:
        for r in attr_bounds[a]:
            attr_key = f"{a}:{r}"
            min_bound = int(attr_bounds[a][r]["min"])
            max_bound = int(attr_bounds[a][r]["max"])

            # Q[g, attr_key] is a derived quantity (how many students with
            # this trait end up in group g) used below -- definitional,
            # always added regardless of `disabled`.
            for g in G:
                model.Add(
                    Q[g, attr_key] == sum(
                        y.get((i, g), 0) * students_types_attr[i][attr_key] for i in T
                    )
                )
            if f"attr:{a}:{r}" in disabled:
                continue
            if not attr_bounds[a][r]["solo"]:
                for g in G:
                    model.Add(min_bound * w[g] <= Q[g, attr_key])
                    model.Add(max_bound * w[g] >= Q[g, attr_key])
            else:
                for g in G:
                    model.Add(min_bound * (w[g] - P[g, attr_key]) <= Q[g, attr_key])
                    model.Add(Q[g, attr_key] <= max_bound * (1 - P[g, attr_key]))

    if modules:
        for d in D:
            # Section capacity: a configurable bound (the "seats" field) --
            # candidate family. The per-student availability constraint just
            # below is a fact about the data (who marked themselves
            # available for this slot), not a policy choice, so it's always
            # enforced.
            if f"section:{d}" not in disabled:
                model.Add(sum(y.get((i, g), 0) for i in T for g in G_d[d]) <= cap[d])

        for d in D:
            for i in T:
                # Now vacuous (0 <= 0) whenever a[i][d] == 0 -- every y[i, g]
                # for g in G_d[d] is already absent from y in that case (see
                # _build_vars() above) -- but kept as-is (not skipped) for
                # the eligible (a[i][d] == 1) case, where it's a real,
                # pre-existing bound: how many students of type i can sit in
                # section d at all, across every one of that section's
                # groups, not just the per-group upper_number cap.
                model.Add(
                    sum(y.get((i, g), 0) for g in G_d[d])
                    <= upper_number * int(students_types[i]["a"][d])
                )

        if params["sameDay"]:
            for p in preferences:
                for d in D:
                    model.Add(sum(w[g] for g in G_td[p, d]) <= groups_number * u[p, d])
            for p in preferences:
                model.Add(sum(u[p, d] for d in D) <= 1)

        for mod in params["fixedDay"]:
            for pref in params["fixedDay"][mod]:
                if params["fixedDay"][mod][pref]:
                    model.Add(u[pref, mod] == 0)

        for p in preferences:
            for d in D:
                model.Add(u[p, d] <= o[p])


def _add_symmetry_breaking(model, mp, v):
    """
    _build_model()'s old Symmetry breaking (experimental) section, moved
    here unchanged -- only called when `symmetry_break` is set.

    Within a (topic, section) family -- or a (topic) family when there are
    no sections -- every group slot G_td[p, d][0], [1], [2], ... is fully
    interchangeable: same topic, same section, same capacity/balance
    bounds, so any assignment has |family|-many equal-objective relabelings
    (which of the k slots is "slot 3" is arbitrary). CP-SAT's search has to
    rediscover that equivalence on its own unless told; lexicographic
    ordering collapses it to a single canonical labeling per family:
    active slots must be a prefix (w descending) and, among active slots,
    size must also be non-increasing (breaking the remaining symmetry of
    *which* active slot gets *which* students). Both are always sound --
    they don't rule out any solution's objective value, only its
    relabelings -- so this only ever prunes search, never the optimum.
    """
    T = mp["T"]
    modules = mp["modules"]
    G_t = mp["G_t"]
    G_td = mp["G_td"]
    y = v["y"]
    w = v["w"]

    families = list(G_td.values()) if modules else list(G_t.values())
    for family in families:
        for g_a, g_b in zip(family, family[1:]):
            model.Add(w[g_a] >= w[g_b])
            model.Add(
                sum(y.get((i, g_a), 0) for i in T) >= sum(y.get((i, g_b), 0) for i in T)
            )


def _set_objective(model, mp, v):
    """_build_model()'s old Objective section, moved here unchanged."""
    students_types = mp["students_types"]
    T = mp["T"]
    z = v["z"]
    z_max = v["z_max"]
    M_max = v["M_max"]

    model.Minimize(
        sum(students_types[i]["flexibility"] * z[i] for i in T) + BALANCE_CONSTANT * (z_max + M_max)
    )


def _solve_status(params, disabled, time_limit_seconds, precomputed_sets=None):
    """Build the model with `disabled` families left out and return just the
    solve status, on a bounded time budget. Shared by find_infeasibility_causes()
    so a trial and its retry use identical model-building logic.

    `precomputed_sets` is forwarded straight to _build_model() (see its
    docstring) -- find_infeasibility_causes() passes the same
    (G, G_t, G_d, G_td, priority) tuple into every trial and retry, since
    none of them depend on `disabled`."""
    model, _ctx = _build_model(params, disabled=disabled, precomputed_sets=precomputed_sets)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 8
    return solver.Solve(model)


def find_infeasibility_causes(params):
    """
    Deletion-filter search for an irreducible infeasible subset of the
    user-configurable constraint families (see _candidate_families()).
    Returns a list of human-readable strings naming the surviving
    (irreducible) family set -- the bounds that, together, can't all be
    satisfied. Falls back to an empty list if anything about the search
    itself goes wrong, so a bug here can never break the (already
    unhappy-path) infeasible response -- callers should show a generic
    message when this returns [].
    """
    try:
        # G/G_t/G_d/G_td/priority depend only on `params`, which is the same
        # for every trial below -- compute them once here instead of letting
        # each _build_model() call (one per candidate family, sometimes two
        # with the UNKNOWN retry) silently redo identical preprocessing()/
        # compute_priority() work.
        G, G_t, G_d, G_td = preprocessing(params)
        priority = compute_priority(params["students_types"], G_t)
        precomputed_sets = (G, G_t, G_d, G_td, priority)

        families = _candidate_families(params)
        dropped = set()
        untested = set()
        started = time.monotonic()
        for key, _label in families:
            if time.monotonic() - started > _IIS_TOTAL_TIME_BUDGET_SECONDS:
                # Out of time -- stop testing; everything left is simply
                # "not confirmed", not "ruled out", so it's dropped (i.e.
                # not reported) same as an INFEASIBLE/inconclusive trial.
                untested.add(key)
                continue
            trial_dropped = dropped | {key}
            status = _solve_status(params, trial_dropped, _IIS_TRIAL_TIME_LIMIT_SECONDS, precomputed_sets)
            if status == cp_model.UNKNOWN:
                # Inconclusive within the base budget -- give it one longer
                # look before deciding anything, rather than either keeping
                # or dropping `key` on a coin flip.
                status = _solve_status(params, trial_dropped, _IIS_TRIAL_RETRY_TIME_LIMIT_SECONDS, precomputed_sets)
            if status != cp_model.FEASIBLE and status != cp_model.OPTIMAL:
                # INFEASIBLE (confirmed not needed) or still UNKNOWN even
                # after the retry (never confirmed `key` was necessary) --
                # either way, don't report `key` as part of the cause: only
                # a family whose removal is *confirmed* feasible earns a
                # spot in the final list, so a slow/inconclusive resolve
                # can under-report a cause but never fabricate one.
                dropped = trial_dropped

        surviving = [label for key, label in families if key not in dropped and key not in untested]
        if not surviving:
            # Every family was individually droppable, yet the model we
            # started from (with none of them disabled) was infeasible --
            # so something outside these families (roster size vs. group
            # count/size, most likely) is the real issue.
            return [
                "The roster itself doesn't fit any valid grouping under "
                "these settings (independent of the balance/section/topic "
                "bounds above) -- double check the target number of groups "
                "and group-size band against the number of students."
            ]
        return surviving
    except Exception:
        return []


def _greedy_hint(params, G, T, G_t, G_d, G_td):
    """
    Cheap constructive heuristic that seeds CP-SAT's search via
    model.AddHint() in run_model(), unconditionally, on every solve.
    Benchmarked 2026-09-09 against synthetic rosters of 150 and 400
    students: roughly a wash at 150 (3.2s -> 3.0s), but a real and
    consistent win at 400 -- mean solve time dropped from ~29s to ~23s
    across repeated runs (baseline ranged 24.9-34.4s, hinted stayed tight
    at 22.5-22.9s), with both still proving OPTIMAL. Worth keeping on
    unconditionally: building the hint is cheap (pure Python, no solver
    calls) and it never made a solve slower or worse in testing, only
    faster or a no-op -- unlike the symmetry-breaking constraints above
    (_ENABLE_SYMMETRY_BREAKING), which measurably hurt at both sizes.

    Ignores the objective and every soft/balance bound entirely: it only
    respects the two things that make a placement *structurally* sane (a
    student type can only sit in a section it marked available, and a
    group can't exceed upper_number seats), first packing each type into
    a group for its ranked topics (rank order, first-fit within the
    matching family), then dumping anything left over into whatever group
    it can physically sit in. Not required to be feasible or even
    complete -- CP-SAT treats a hint as a suggestion, not a solution -- so
    a rough answer here is fine; the point is only to give the search a
    plausible place to start instead of nothing.

    `G`, `T`, `G_t`, `G_d`, `G_td` are the same structures `_build_model()`
    already computed (its `ctx`) -- passed in rather than rebuilt here, so
    this doesn't run preprocessing() a second time on
    every request.
    """
    modules = params["modules"]
    students_types = params["students_types"]
    upper_number = params["upper_number"]
    D = list(modules)

    remaining = {i: max(0, int(students_types[i]["students"])) for i in T}
    fill = {g: 0 for g in G}
    y_hint = defaultdict(int)

    def available_sections(i):
        if not D:
            return [None]
        return [d for d in D if int(students_types[i]["a"].get(d, 0)) == 1] or list(D)

    def place(i, candidates):
        for g in candidates:
            if remaining[i] <= 0:
                break
            room = upper_number - fill[g]
            if room <= 0:
                continue
            take = min(room, remaining[i])
            fill[g] += take
            y_hint[(i, g)] += take
            remaining[i] -= take

    # Pass 1: rank order, restricted to a section the type is available for.
    max_rank = max((len(students_types[i].get("preferences", {}) or {}) for i in T), default=0)
    for rank in range(1, max_rank + 1):
        for i in T:
            if remaining[i] <= 0:
                continue
            topic = students_types[i].get("preferences", {}).get(str(rank))
            if not topic:
                continue
            for d in available_sections(i):
                family = G_td.get((topic, d), []) if D else G_t.get(topic, [])
                place(i, family)
                if remaining[i] <= 0:
                    break

    # Pass 2: fallback -- anything left goes anywhere the type can physically
    # sit, regardless of preference, so the hint is a complete assignment.
    for i in T:
        if remaining[i] <= 0:
            continue
        for d in available_sections(i):
            candidates = G_d.get(d, []) if D else G
            place(i, candidates)
            if remaining[i] <= 0:
                break

    w_hint = {g: (1 if fill[g] > 0 else 0) for g in G}
    return y_hint, w_hint


# Floor on the CP-SAT search itself, however long model-building/hinting
# already ate into the wall-clock budget below. Without this, a roster
# whose _build_model()/_greedy_hint() alone chew through the whole budget
# would hand the solver zero (or negative) time and get back an
# artificial INFEASIBLE/UNKNOWN rather than an honest attempt.
_MIN_SEARCH_SECONDS = 2.0

# -------------------- Sensitivity: "what's this requirement costing you" --------------------
# Companion to find_infeasibility_causes() above, for the opposite case: the
# solve succeeded, and the question is which of the *satisfied* bounds is
# expensive to keep. See sensitivity_report()'s own docstring below for the
# full picture; these two constants bound it the same way
# _IIS_TRIAL_TIME_LIMIT_SECONDS/_IIS_TOTAL_TIME_BUDGET_SECONDS bound the
# infeasibility search, and are deliberately separate constants (not reused)
# so the two searches' budgets can be tuned independently later.
_SENSITIVITY_TRIAL_TIME_LIMIT_SECONDS = 5.0
_SENSITIVITY_TOTAL_TIME_BUDGET_SECONDS = 20.0


def _solve_full(params):
    """
    The "build, hint, solve" core shared by run_model() (the main sync/
    async solve path) and sensitivity_report() (which needs an identical
    baseline solve to compare its what-if trials against). Pulled out of
    run_model() as a pure extraction -- no logic changed -- specifically so
    sensitivity_report() can't quietly drift onto different hint or
    wall-clock-budget behavior than the main path; see run_model()'s
    docstring (below) for why build+hint time has to come out of the same
    budget as the search itself, not be added on top of it.

    Returns (solver, ctx, status). Does not extract results or handle
    infeasibility -- that's each caller's own job, since run_model() wants
    per-student groups and sensitivity_report() only ever wants aggregate
    y[] values (see _top_choice_share() below).
    """
    started = time.monotonic()
    total_budget = 0.90 * 60 * params["tmax"]

    model, ctx = _build_model(params, symmetry_break=_ENABLE_SYMMETRY_BREAKING)
    y, w, G, T = ctx["y"], ctx["w"], ctx["G"], ctx["T"]
    G_t, G_d, G_td = ctx["G_t"], ctx["G_d"], ctx["G_td"]
    y_hint, w_hint = _greedy_hint(params, G, T, G_t, G_d, G_td)
    # y is sparse (see _build_model()'s Vars section) -- only hint the pairs
    # that actually exist as variables; _greedy_hint() already only places
    # students into sections they're available for, so this never silently
    # drops a hint that mattered.
    for (i, g) in y:
        model.AddHint(y[i, g], y_hint.get((i, g), 0))
    for g in G:
        model.AddHint(w[g], w_hint.get(g, 0))

    elapsed_before_search = time.monotonic() - started
    search_budget = max(_MIN_SEARCH_SECONDS, total_budget - elapsed_before_search)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = search_budget
    solver.parameters.relative_gap_limit = 0.01
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    return solver, ctx, status


def run_model(params):
    # params["tmax"] is the *total* wall-clock budget for this call (see
    # views.py's SYNC_SOLVE_TMAX_SECONDS / _SYNC_TIME_LIMIT_SAFETY_FACTOR),
    # not just the CP-SAT search -- callers on a hard request deadline
    # (Lambda behind API Gateway's 29s cap) need the whole thing bounded,
    # model-building and greedy-hint computation included. Those two steps
    # are deterministic (no internal time limit to set), so the fix is to
    # measure how long they actually took and give the solver whatever's
    # left of the budget, instead of always handing it the full amount on
    # top. A 50-student/4-group roster was observed taking ~29s total on
    # dev hardware with the old fixed-search-budget code, even though the
    # CP-SAT search itself never exceeded its 20s cap -- build+hint alone
    # accounted for the rest. See docs/ARCHITECTURE.md. (Now lives in
    # _solve_full() above, shared with sensitivity_report().)
    solver, ctx, status = _solve_full(params)
    G, T = ctx["G"], ctx["T"]
    students_types, priority = ctx["students_types"], ctx["priority"]
    y = ctx["y"]

    # -------------------- Results --------------------
    results = []
    causes = []
    factible = status in FACTIBLE_STATUSES
    if factible:
        for g in G:
            group_students = [i for i in T if (i, g) in y and solver.Value(y[i, g]) != 0]
            if group_students:
                group_name = group_display_name(g)
                group_students = assign_students(params["students"], students_types, g, solver, y, T)
                results.append({"group": g, "students": group_students, "group_name": group_name})
    else:
        causes = find_infeasibility_causes(params)

    return {
        "results": results,
        "factible": factible,
        "priority": priority,
        "status": solver.StatusName(status),
        "causes": causes,
    }


def _top_choice_share(solver, ctx):
    """
    % of individual students who land in a group matching their #1 ranked
    preference, read directly off the solved y[] values, aggregated by
    student *type* rather than expanded into individual students.

    Deliberately doesn't go through assign_students(): that function pops
    students off students_types[i]["students_list"] as it assigns them
    (see its own docstring), which is only safe to do once per fresh
    students_types -- fine for run_model()'s single solve, but
    sensitivity_report() below solves several independent what-if variants
    of the *same* params in one request, and re-running assign_students()
    on each would either double-count or crash on an already-drained pool.
    None of that bookkeeping is needed here anyway: preference rank only
    depends on (type, group), and each type's population size is already
    known from students_types[i]["students"], so this sums directly over
    types instead of individual students.
    """
    y, T, G = ctx["y"], ctx["T"], ctx["G"]
    priority = ctx["priority"]
    students_types = ctx["students_types"]
    total = 0
    top = 0
    for i in T:
        n = students_types[i]["students"]
        if n <= 0:
            continue
        total += n
        for g in G:
            if (i, g) not in y:
                continue
            placed = solver.Value(y[i, g])
            if placed and priority.get(i, {}).get(g) == 1:
                top += placed
    return (top / total * 100.0) if total else 0.0


def sensitivity_report(params):
    """
    "What is each configurable requirement costing you?" -- the
    feasible-solve counterpart to find_infeasibility_causes() above. That
    one answers "which bounds together make this impossible"; this one
    answers "of the bounds you *did* satisfy, which one is the most
    expensive to keep."

    For an already-solvable roster, re-solves once per user-configurable
    constraint family (the same family list find_infeasibility_causes()
    tests -- see _candidate_families()) with that one family dropped, and
    reports how many more students would land their #1 ranked topic if it
    were relaxed, everything else held fixed. Framed in #1-choice
    percentage rather than raw objective value on purpose: it's the same
    unit the Results screen's "Preference outcomes" panel already shows
    the person, and it's meaningful across every family type (a group-size
    change and an attribute-balance change aren't otherwise comparable),
    unlike an internal objective score.

    IMPORTANT: the baseline solve here is deliberately its OWN solve, on
    the exact same solver settings (time limit, default relative_gap_limit
    of 0) as every family trial below -- NOT a call to run_model()/
    _solve_full(), even though that would also produce a "baseline"
    result. run_model()'s production tuning (a ~20s budget and a 0.01
    relative gap, chosen so the sync path stays under API Gateway's 29s
    cap -- see its docstring) means it can return a solution that's within
    1% of optimal on the *overall* objective while still being
    meaningfully worse on #1-choice placement specifically: preference
    priority and the balance penalty share one objective
    (BALANCE_CONSTANT * (z_max + M_max) + sum(flexibility * z[i])), and
    since UNRANKED_PRIORITY (1000) is the same order of magnitude as
    BALANCE_CONSTANT (1000), a 1% gap on a multi-thousand-point objective
    is easily enough slack to flip several students between rank 1 and
    rank 2 without CP-SAT ever "seeing" a reason to prefer one over the
    other. Comparing that kind of near-optimal-but-untied baseline against
    trials solved to a tighter/different tolerance produced a real bug
    during development here: every family, including ones that plainly
    shouldn't matter, showed the exact same suspiciously-round gain --
    an artifact of the tolerance mismatch, not a genuine finding. Solving
    baseline and every trial the same way (see solve_variant() below)
    closes that gap: any difference reported now reflects the family
    that was dropped, not which solve happened to land on a better tied
    solution.

    Unlike the infeasibility deletion filter, dropping one family from an
    already-feasible model can only relax its feasible region -- it can
    never turn feasible into infeasible -- so every trial here is expected
    to land on FEASIBLE/OPTIMAL; a trial that times out inconclusive
    (UNKNOWN within _SENSITIVITY_TRIAL_TIME_LIMIT_SECONDS) is skipped
    rather than guessed at, same caution as find_infeasibility_causes().

    Meant to run as a separate, on-demand call *after* the main solve (see
    views.sensitivity()) -- never inline with run_model() itself. It's
    O(number of families) resolves on top of the main solve, which would
    reopen the exact wall-clock-budget problem run_model() was fixed for
    (see its docstring) if it ran on every request instead of only when
    the person asks for it from the Results screen.

    Returns {"baseline_pct": float, "families": [{"label", "gain_points"}, ...]},
    families sorted most-expensive-first and limited to gain_points > 0.5
    (keeps solver noise off a UI list) -- or {"baseline_pct": None,
    "families": []} if the baseline itself doesn't solve, or the overall
    time budget runs out before it does, or anything else goes wrong.
    Callers should show "not available" rather than an error in that
    case, same contract as find_infeasibility_causes() returning [].
    """
    try:
        # Same "compute the shared sets once" approach as
        # find_infeasibility_causes() -- see that function's comment.
        G, G_t, G_d, G_td = preprocessing(params)
        priority = compute_priority(params["students_types"], G_t)
        precomputed_sets = (G, G_t, G_d, G_td, priority)

        def solve_variant(disabled):
            """
            Build and solve one variant (baseline when `disabled` is empty,
            a what-if trial otherwise) on identical solver settings -- see
            this function's docstring for why that identical-footing
            comparison matters. Deliberately doesn't use _greedy_hint()
            either: a hint computed for the *full* model could bias a
            disabled-family trial toward the baseline's own solution
            shape, working against the point of asking "what changes if
            this family is gone".
            """
            model, ctx = _build_model(params, disabled=disabled, precomputed_sets=precomputed_sets)
            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds = _SENSITIVITY_TRIAL_TIME_LIMIT_SECONDS
            solver.parameters.num_search_workers = 8
            status = solver.Solve(model)
            return solver, ctx, status

        started = time.monotonic()
        baseline_solver, baseline_ctx, baseline_status = solve_variant(frozenset())
        if baseline_status not in FACTIBLE_STATUSES:
            return {"baseline_pct": None, "families": []}
        baseline_share = _top_choice_share(baseline_solver, baseline_ctx)

        families = _candidate_families(params)
        out = []
        for key, label in families:
            if time.monotonic() - started > _SENSITIVITY_TOTAL_TIME_BUDGET_SECONDS:
                # Out of time -- stop testing; an untested family is simply
                # not reported, same "under-report, never fabricate" rule
                # find_infeasibility_causes() follows.
                break
            solver, ctx, status = solve_variant({key})
            if status not in FACTIBLE_STATUSES:
                continue
            share = _top_choice_share(solver, ctx)
            gain = share - baseline_share
            if gain > 0.5:
                out.append({"label": label, "gain_points": round(gain, 1)})
        out.sort(key=lambda r: -r["gain_points"])
        return {"baseline_pct": round(baseline_share, 1), "families": out}
    except Exception:
        return {"baseline_pct": None, "families": []}
