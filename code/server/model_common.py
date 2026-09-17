"""
Solver-agnostic pieces of the MATE group-assignment model: building the
candidate groups (and the topic/section indexes over them), computing each
student type's per-group preference priority, and computing effective
section capacity. No gurobipy or ortools import here on purpose -- both
optimization.py (Gurobi) and optimization_cpsat.py (OR-Tools CP-SAT) import
from this module, so the open-source default path never has to pull in
gurobipy, and both solver backends stay guaranteed to agree on what a
"group" is, how it's indexed, and how a student's stated preferences map
onto it.
"""
import math
from collections import defaultdict


# Priority a group gets in a student type's z[i] objective term when that
# group's topic isn't among the type's ranked preferences at all. Shared here
# so both solver backends agree on it without hardcoding the same number
# twice (optimization.py used to have its own inline "# HARDCODED" 1000).
UNRANKED_PRIORITY = 1000


def preprocessing(params):
    """
    Build the candidate group list G, plus the indexes over it everything
    else in the model needs: G_t[topic] (that topic's groups), G_d[section]
    (that section's groups), and G_td[topic, section] (both).

    These used to be computed in two passes: this function built G as
    formatted display strings ("Tema {topic} - {section} (N{n})"), and a
    separate create_subsets() re-derived topic/section membership afterwards
    by pattern-matching substrings of that same string (e.g.
    `"Tema {} - ".format(topic) in g`). That's fragile -- it silently only
    matches the *first word* of a topic or section name, so a group whose
    topic contains a space (e.g. "Data Structures") never matched anything,
    which is exactly the bug compute_priority()'s docstring below describes
    -- and wasteful (O(|G| * |topics| * |sections|) substring scans for
    information this function already has while building G). Building the
    indexes in the same loop that builds G is both correct regardless of
    what topic/section names contain, and O(|G|).
    """
    preferences_bounds = params["preferences"]
    preferences = list(params["preferences"].keys())
    upper_number = params["upper_number"]
    modules = params["modules"]
    students = params["students"]

    G = []
    G_t = defaultdict(list)
    G_d = defaultdict(list)
    G_td = defaultdict(list)

    if modules:
        disp = {
            mod: len([s for s in students if int(students[s]["a"][mod]) == 1])
            for mod in modules
        }
        modules_number = {mod: {} for mod in modules}
        for m in modules:
            for p in preferences:
                modules_number[m][p] = math.floor(disp[m] / upper_number) + 1
                if modules_number[m][p] < preferences_bounds[p]["min"]:
                    modules_number[m][p] = preferences_bounds[p]["min"]
                elif modules_number[m][p] > preferences_bounds[p]["max"]:
                    modules_number[m][p] = preferences_bounds[p]["max"]

        for p in preferences:
            for d in modules:
                for n in range(1, modules_number[d][p] + 1):
                    g = f"Tema {p} - {d} (N{n})"
                    G.append(g)
                    G_t[p].append(g)
                    G_d[d].append(g)
                    G_td[p, d].append(g)
    else:
        for p in preferences:
            for n in range(1, preferences_bounds[p]["max"] + 1):
                g = f"Tema {p} (N{n})"
                G.append(g)
                G_t[p].append(g)

    return G, G_t, G_d, G_td


def group_display_name(g):
    """
    Human-facing group name -- e.g. for the Results screen and the emailed
    Excel export. Same string produced by preprocessing() to key and match
    groups, minus the "Tema " ("topic" in Spanish) prefix and the trailing
    "(Nn)" disambiguator suffix, which are implementation detail and
    shouldn't leak into an English-language UI.
    """
    name = g.split(" (N")[0]
    prefix = "Tema "
    if name.startswith(prefix):
        name = name[len(prefix):]
    return name


def student_type_key(attributes, preferences, disponibilities):
    """
    Canonical, order-independent identity for a group of students who share
    the same attributes/preferences/availability -- i.e. a "student type".
    Building this key used to be duplicated, independently, in three
    places that all have to agree byte-for-byte for a lookup to succeed:
    code/client/backend/utils.py's create_students_types() (which collapses
    individual students into types in the first place), backend/views.py's
    _preference_outcome() (which looks a type back up from one of its own
    students' records for the Results screen's preference tally, sync
    path), and code/server/utils.py's get_report() (same lookup, for the
    emailed/offline path). Each was its own f"{attributes} - {preferences}
    - {disponibilities}" (or without disponibilities, when there are no
    modules) -- fragile because Python's dict repr follows insertion order,
    so the exact same key/value pairs inserted in a different order (e.g.
    a different JSON key order from a different code path building the
    same logical record) stringify differently, silently creating two
    "different" types that are actually the same one: extra spurious types
    in the solve, or a failed lookup ("type not found") in the tally.

    Sorting each dict's items() makes the key depend only on its actual
    content, not insertion order. `disponibilities` is a plain list, not a
    dict -- its *position* is meaningful (index N means "available for
    module N"), so it's left in order, just tupled to be hashable. A type
    with no modules configured (an empty/falsy disponibilities) gets a
    2-tuple instead of a 3-tuple, matching the original code's own
    with-vs-without-disponibilities branch.
    """
    attr_key = tuple(sorted(attributes.items()))
    pref_key = tuple(sorted(preferences.items()))
    if disponibilities:
        return (attr_key, pref_key, tuple(disponibilities))
    return (attr_key, pref_key)


def get_min_capacity(params):
    """
    Effective per-section capacity: the smaller of the configured "seats"
    bound (params["capacity"][mod]) and how many students are actually
    available for that section, so the solver never gets asked to seat
    more students in a section than marked themselves available for it.

    disponibilities[mod] sums students_types[s]["students"] (each type's
    real headcount) over types available for mod -- the same headcount
    preprocessing()'s own `disp` computes, just grouped by type instead of
    iterated per student. This used to count len(types available) instead
    -- the number of distinct student *types*, not the number of actual
    students each one represents. That was a bug, not a deliberate
    conservative bound: downstream, _add_constraints() in both
    optimization.py and optimization_cpsat.py uses cap[d] to bound
    `sum(y[i, g] for i in T for g in G_d[d])`, and y[i, g] is a headcount
    (each type i's y-values across all groups sum to
    students_types[i]["students"], enforced by its own constraint) -- so
    comparing that headcount sum against a *type count* silently
    undercounted true capacity whenever several students shared a type
    (the normal case, since types are exactly students who share
    attributes/preferences/availability), making an otherwise entirely
    feasible roster spuriously infeasible. E.g. one type of 50 identical
    students available for a section used to compute capacity 1 for it.
    """
    modules = params["modules"]
    students_types = params["students_types"]
    disponibilities = {
        mod: sum(
            students_types[s]["students"]
            for s in students_types if int(students_types[s]["a"][mod]) == 1
        ) for mod in modules
    }
    capacity = {
        mod: min(disponibilities[mod], params["capacity"][mod])
        for mod in modules
    }
    return capacity


def compute_priority(students_types, G_t, unranked_priority=UNRANKED_PRIORITY):
    """
    For each student type, rank the groups belonging to its stated
    preferences: priority[type_id][g] = 1 for its 1st-choice topic's groups,
    2 for its 2nd choice, and so on -- following t["preferences"]'s own
    iteration order (a dict of rank -> topic name). A group whose topic the
    type didn't rank at all falls back to `unranked_priority`.

    Looks up each choice's groups directly via G_t (from preprocessing())
    instead of pattern-matching against group *display* strings. The
    previous version compared a topic name to `g.split(" ")[1]`, which only
    ever checks the first whitespace-separated word of the group's name --
    so a topic with a space in it (e.g. "Data Structures", entirely plausible
    for a real, user-uploaded topic name) never matched at all, leaving every
    group tied to that topic permanently "unranked" for every student type
    that chose it, silently corrupting both the objective and the
    preference-outcome stats shown on Results. G_t is keyed by the actual
    topic value (not a substring of a formatted display string), so this is
    correct no matter what a topic or section name contains, and it's an
    O(1) dict lookup per ranked choice instead of an O(|G|) scan of every
    group for every (type, choice) pair.
    """
    priority = {}
    for t in students_types.values():
        p = defaultdict(lambda: unranked_priority)
        for i, rank_key in enumerate(t["preferences"]):
            topic = t["preferences"][rank_key]
            for g in G_t.get(topic, ()):
                p[g] = i + 1
        priority[t["id"]] = p
    return priority

def estimate_variable_count(params):
    """
    Exact count of the CP-SAT decision variables _build_model()
    (code/client/backend/optimization_cpsat.py) would create for `params`,
    computed directly from `params` and preprocessing() -- without ever
    building the model itself, so it's cheap enough to run on every
    /run_model/ request ahead of any solve.

    This is what decides whether a request solves inline or gets handed
    off to the cluster (see backend/views.py's run_model() and
    project/settings.py's SYNC_SOLVE_MAX_VARIABLES) -- replacing the old
    raw-student-count threshold. Student count alone was a poor proxy for
    how hard a roster actually is to solve: the same headcount can produce
    wildly different variable counts (and solve times) depending on how
    many distinct student types it collapses into and how many
    topics/sections are configured. See docs/ARCHITECTURE.md's note on
    this threshold for the benchmark this number is based on.

    Mirrors _build_vars() family by family: y is sparse the same way it is
    there (a (type, group) pair only exists when that type marked itself
    available for the group's section), Q/P/M/M_max/u/o are dense over
    their full index sets, exactly as _build_vars() declares them. Both
    this function and frontend/src/estimateModelSize.js (a client-side
    approximation used for the live "~N variables" display on the
    Configure & run screen, before a request is ever sent) implement the
    same formula -- this one is the exact, authoritative version the
    backend actually acts on.
    """
    G, G_t, G_d, G_td = preprocessing(params)
    students_types = params["students_types"]
    T = list(students_types.keys())
    modules = params["modules"]
    A = params["A"]
    preferences = list(params["preferences"].keys())
    D = list(modules)

    if modules:
        group_section = {g: d for d, gs in G_d.items() for g in gs}
        y_count = sum(
            1 for i in T for g in G
            if int(students_types[i]["a"][group_section[g]]) == 1
        )
    else:
        y_count = len(T) * len(G)

    w_count = len(G)
    z_count = len(T) + 1  # z[i] per type, plus z_max
    q_count = len(G) * len(A)  # Q[g, attr] -- dense, definitional
    p_count = len(G) * len(A)  # P[g, attr] -- dense, same index set as Q
    m_count = len(G) + 1  # M[g] per group, plus M_max
    u_count = len(preferences) * len(D)  # only ever used when modules is set
    o_count = len(preferences)

    return y_count + w_count + z_count + q_count + p_count + m_count + u_count + o_count

