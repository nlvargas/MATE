import itertools
import os
import gurobipy as gp

from model_common import (
    preprocessing, get_min_capacity, group_display_name, compute_priority, UNRANKED_PRIORITY,
)


def assign_students(students_dict, students_types, student_type_name, y, T):
    """
    Pop this group's assigned students off each contributing type's
    students_list and return them as a flat list.

    MUTATES students_types: student_type["students_list"].pop() below
    consumes a type's remaining student pool as it's assigned. Across one
    run_model() call's group-by-group results loop, that's exactly right
    -- the model's own "sum(y[i,g] for g in G) == students_types[i]['students']"
    constraint guarantees every one of a type's students gets popped
    exactly once, total, over all groups. It's only right ONCE, though:
    students_types (and the students_list lists inside it) must be freshly
    built for every independent run_model() call. Reusing the same
    students_types object across two calls -- comparing solver backends on
    the same roster, a retry, anything that doesn't rebuild it -- would
    find some or all students_list already drained by the first call. The
    guard below turns that into a clear error instead of silently
    returning too few students (if any are left) or a bare
    "IndexError: pop from empty list" (once none are).
    """
    students = []
    for i in T:
        sol = int(y[i, student_type_name].X)
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


def run_model(params):
    # -------------------- Params --------------------
    attr_bounds = params["attributes"]
    preferences = list(params["preferences"].keys())
    groups_number = params["groups_number"]
    lower_number = params["lower_number"]
    upper_number = params["upper_number"]
    preferences_bounds = params["preferences"]
    used_preferences = params["usedPreferences"]
    students = params["students"]
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
    G, G_t, G_d, G_td = preprocessing(params)
    priority = compute_priority(students_types, G_t)

    # A type's headcount is the tightest valid upper bound for any variable
    # that counts (or is derived from) that type's own students -- mirrors
    # optimization_cpsat.py's identically-named total_by_type/total_students,
    # kept here in lockstep so both backends reason over the same root-node
    # relaxation instead of Gurobi inferring these bounds late, from the
    # constraints alone.
    total_by_type = {i: max(1, students_types[i]["students"]) for i in T}
    max_type_size = max(total_by_type.values())

    # -------------------- Model --------------------
    m = gp.Model()

    # -------------------- Vars --------------------
    # Every var below is also declared with an explicit ub= -- without one,
    # Gurobi defaults an integer var's upper bound to +infinity and leaves
    # the LP relaxation to discover the real bound from the constraints
    # further down. Declaring the true bound up front gives Gurobi a
    # tighter relaxation at the root node, before it's done any of that
    # work. Every bound here is a structural fact (a group can never hold
    # more than upper_number students, a type can never rack up more
    # priority cost than its own headcount allows), not a guess -- so none
    # of them can cut off a feasible solution.
    y = m.addVars(itertools.product(T, G), vtype=gp.GRB.INTEGER, lb=0, ub=upper_number, name="y")
    w = m.addVars(G, vtype=gp.GRB.BINARY, name="w")
    z = m.addVars(T, vtype=gp.GRB.INTEGER, lb=0,
                  ub={i: UNRANKED_PRIORITY * total_by_type[i] for i in T}, name="z")
    z_max = m.addVar(vtype=gp.GRB.INTEGER, lb=0, ub=UNRANKED_PRIORITY * max_type_size, name="z_max")
    Q = m.addVars(itertools.product(G, A), vtype=gp.GRB.INTEGER, lb=0, ub=upper_number, name="Q")
    P = m.addVars(itertools.product(G, A), vtype=gp.GRB.BINARY, name="P")
    M = m.addVars(G, vtype=gp.GRB.INTEGER, lb=0, ub=upper_number, name="M")
    M_max = m.addVar(vtype=gp.GRB.INTEGER, lb=0, ub=upper_number, name="M_max")
    u = m.addVars(itertools.product(preferences, D), vtype=gp.GRB.BINARY, name="u")
    o = m.addVars(preferences, vtype=gp.GRB.BINARY, name="o")

    # -------------------- Constraints --------------------
    m.addConstrs(
        (sum(y[i, g] for g in G) == students_types[i]["students"] for i in T),
        name="Todos los alumnos deben ser asignados a algun grupo -"
    )

    m.addConstrs(
        (y[i, g] <= upper_number * w[g] for i in T for g in G),
        name="Activacion de w"
    )

    m.addConstr(
        sum(w[g] for g in G) == groups_number,
        name="Cantidad de grupos"
    )

    m.addConstrs(
        (sum(y[i, g] for i in T) >= lower_number * w[g] for g in G),
        name="Cantidad minima de alumnos por grupo"
    )
    m.addConstrs(
        (sum(y[i, g] for i in T) <= upper_number * w[g] for g in G),
        name="Cantidad maxima de alumnos por grupo"
    )

    m.addConstr(
        sum(o[p] for p in preferences) <= used_preferences,
        name="Cantidad maxima de preferencias a utilizar"
    )

    m.addConstrs(sum(y[i, g] for i in not_answered) <= 1 + M[g] for g in G)

    m.addConstrs(M_max >= M[g] for g in G)

    for preference in preferences_bounds:
        if used_preferences == len(preferences):
            min_bound = int(preferences_bounds[preference]["min"])
            m.addConstr(sum(w[g] for g in G_t[str(preference)]) >= min_bound)

        max_bound = int(preferences_bounds[preference]["max"])
        m.addConstr(sum(w[g] for g in G_t[str(preference)]) <= max_bound)

    m.addConstrs(z[i] == sum(y[i, g] * int(priority[i][g]) for g in G) for i in T)

    m.addConstrs(z_max >= z[i] for i in T)

    for a in attr_bounds:
        for r in attr_bounds[a]:
            attr_key = f"{a}:{r}"
            min_bound = int(attr_bounds[a][r]["min"])
            max_bound = int(attr_bounds[a][r]["max"])

            m.addConstrs(Q[g, attr_key] == sum(y[i, g] * students_types_attr[i][attr_key] for i in T) for g in G)
            if not attr_bounds[a][r]["solo"]:
                m.addConstrs(min_bound * w[g] <= Q[g, attr_key] for g in G)
                m.addConstrs(max_bound * w[g] >= Q[g, attr_key] for g in G)
            else:
                m.addConstrs(min_bound * (w[g] - P[g, attr_key]) <= Q[g, attr_key] for g in G)
                m.addConstrs(Q[g, attr_key] <= max_bound * (1 - P[g, attr_key]) for g in G)

    if modules:
        m.addConstrs(sum(y[i, g] for i in T for g in G_d[d]) <= cap[d] for d in D)

        m.addConstrs(sum(y[i, g] for g in G_d[d]) <= upper_number * int(students_types[i]["a"][d]) for d in D for i in T)

        m.addConstrs(sum(w[g] for g in G_td[p, d]) <= groups_number * u[p, d] for p in preferences for d in D if params['sameDay'])

        m.addConstrs(sum(u[p, d] for d in D) <= 1 for p in preferences if params['sameDay'])

        m.addConstrs(u[pref, mod] == 0 for mod in params['fixedDay'] for pref in params['fixedDay'][mod] if params['fixedDay'][mod][pref])

        m.addConstrs(u[p, d] <= o[p] for p in preferences for d in D)

    # -------------------- Objective --------------------
    m.setObjective(
        sum(students_types[i]["flexibility"] * z[i] for i in T) + 1000 * (z_max + M_max),
        gp.GRB.MINIMIZE
    )

    # -------------------- Solver --------------------
    m.Params.MIPGap = 0.01
    m.Params.TimeLimit = 0.90*60*params["tmax"]
    m.optimize()

    # -------------------- Results --------------------
    results = []
    # SolCount (Gurobi's own count of feasible incumbents found), not the
    # status code, is the correct "do we have something usable" test: a MIP
    # that hits m.Params.TimeLimit while still holding a feasible incumbent
    # reports status TIME_LIMIT (9), not OPTIMAL (2) or SUBOPTIMAL (13), even
    # though its solution is perfectly usable -- and TIME_LIMIT is exactly
    # what's expected on the cluster path for large/hard rosters that need
    # the full time budget. Mirrors optimization_cpsat.py's
    # FACTIBLE_STATUSES = (cp_model.OPTIMAL, cp_model.FEASIBLE) handling of
    # the analogous "solver hit a limit but still has an incumbent" case.
    factible = m.SolCount > 0
    if factible:
        for g in G:
            students = [i for i in T if y[i, g].X != 0]
            if students:
                group_name = group_display_name(g)
                students = assign_students(params["students"], students_types, g, y, T)
                results.append({"group": g, "students": students, "group_name": group_name})
    elif m.status == gp.GRB.INFEASIBLE:
        # Only call computeIIS() when the model was actually proven
        # infeasible -- calling it on e.g. a TIME_LIMIT-with-no-incumbent or
        # INF_OR_UNBD outcome raises a GurobiError instead of a usable
        # diagnosis.
        m.computeIIS()
        iis_path = "groups/outputs/IIS.ilp"
        os.makedirs(os.path.dirname(iis_path), exist_ok=True)
        m.write(iis_path)

    return {"results": results, "factible": factible, "priority": priority}
