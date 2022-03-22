import math
import itertools
from collections import defaultdict
import gurobipy as gp


def preprocessing(params):
    preferences_bounds = params["preferences"]
    preferences = list(params["preferences"].keys())
    upper_number = params["upper_number"]
    modules = params["modules"]
    students = params["students"]

    if modules:
        disp = {
            mod: len([s for s in students if int(students[s]["a"][mod]) == 1]) 
            for mod in modules
        }
        modules_number = {mod: {} for mod in modules}
        for m in modules:
            for p in preferences:
                modules_number[m][p] = math.floor(disp[m]/upper_number) + 1 
                if modules_number[m][p] < preferences_bounds[p]["min"]:
                    modules_number[m][p] = preferences_bounds[p]["min"]
                elif modules_number[m][p] > preferences_bounds[p]["max"]:
                    modules_number[m][p] = preferences_bounds[p]["max"]

        G = [
            f"Tema {p} - {d} (N{n})" 
            for p in preferences 
            for d in modules 
            for n in range(1, modules_number[d][p] + 1)
        ]
    else:
        G = [
            f"Tema {p} (N{n})" 
            for p in preferences 
            for n in range(1, preferences_bounds[p]["max"] + 1)
        ]
    return G


def get_min_capacity(params):
    modules = params["modules"]
    students_types = params["students_types"]
    disponibilities = {
        mod: len(
            [s for s in students_types if int(students_types[s]["a"][mod]) == 1]
        ) for mod in modules
    }
    capacity = {
        mod: min(disponibilities[mod], params["capacity"][mod]) 
        for mod in modules
    }
    return capacity
    

def create_subsets(G, preferences, D):
    G_t = defaultdict(list)  # grupos asociados al tema t
    G_d = defaultdict(list)  # grupos asociados al dia/seccion d
    G_td = defaultdict(list) 
    for g in G:
        if D:
            for p in preferences:
                if "Tema {} - ".format(p) in g:
                    G_t[p].append(g)
            for d in D:
                if " - {} (N".format(d) in g:
                    G_d[d].append(g)
            for t in preferences:
                for d in D:
                    if "Tema {} - ".format(t) in g and " - {} (N".format(d) in g:
                        G_td[t, d].append(g)
        else:
            for p in preferences:
                if "Tema {} ".format(p) in g:
                    G_t[p].append(g)
    return G_t, G_d, G_td     


def assign_students(students_dict, students_types, student_type_name, y, T):
    students = []
    for i in T:
        sol = int(y[i, student_type_name].X) 
        if sol > 0:
            student_type = students_types[i]
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
    G = preprocessing(params)
    G_t, G_d, G_td = create_subsets(G, preferences, D)
    priority = {i: defaultdict(lambda: 1000) for i in T}  # HARDCODED
    for t in students_types.values():
        for i, preference in enumerate(t["preferences"]):
            groups_prefered = filter(
                lambda g: t["preferences"][preference] == g.split(" ")[1] in g, G
            )
            for g in groups_prefered:
                priority[t["id"]][g] = i + 1

    # -------------------- Model --------------------
    m = gp.Model()

    # -------------------- Vars --------------------
    y = m.addVars(itertools.product(T, G), vtype=gp.GRB.INTEGER, lb=0, name="y")
    w = m.addVars(G, vtype=gp.GRB.BINARY, name="w")
    z = m.addVars(T, vtype=gp.GRB.INTEGER, lb=0, name="z")
    z_max = m.addVar(vtype=gp.GRB.INTEGER, lb=0, name="z_max")
    Q = m.addVars(itertools.product(G, A), vtype=gp.GRB.INTEGER, lb=0, name="Q")
    P = m.addVars(itertools.product(G, A), vtype=gp.GRB.BINARY, name="P")
    M = m.addVars(G, vtype=gp.GRB.INTEGER, lb=0, name="M")
    M_max = m.addVar(vtype=gp.GRB.INTEGER, name="M_max")
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
    factible = True if m.status in (2, 13) else False
    if factible:
        for g in G:
            students = [i for i in T if y[i, g].X != 0]
            if students:
                group_name = g.split(" (N")[0]
                students = assign_students(params["students"], students_types, g, y, T)
                results.append({"group": g, "students": students, "group_name": group_name})
    else:
        m.computeIIS()
        m.write("groups/outputs/IIS.ilp")

    return {"results": results, "factible": factible, "priority": priority}