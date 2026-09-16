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


def validate_feasibility(params):
    """
    Sound, cheap-to-check necessary conditions for `params` to be
    feasible at all, computed directly from the request -- without
    building or solving a model. Every check here is a *sufficient*
    condition for guaranteed infeasibility, traced directly from
    _add_constraints() (code/client/backend/optimization_cpsat.py): if a
    check fires, no assignment of students to groups can possibly satisfy
    every constraint, regardless of solver, time budget, or hardware --
    so backend/views.py's run_model() returns these immediately, before
    attempting a solve (or queuing a cluster job) that's mathematically
    guaranteed to fail.

    This deliberately does NOT try to catch every possible infeasibility --
    only the ones a closed-form check can prove soundly and cheaply. Two
    known infeasibility mechanisms are left out on purpose:
      - "Solo" attribute bounds (params["attributes"][a][v]["solo"]): the
        model gives each group a free P[g, attr] opt-out variable, so a
        group can duck a solo bound entirely -- there's no total-headcount
        inequality that has to hold the way there is for a non-solo bound.
      - The `used_preferences` cap coupled with `sameDay`: `u[p, d] <= o[p]`
        only binds when sameDay is on and sections are configured, and
        working out exactly when that combination forces infeasibility
        needs more care than a quick closed-form check can give
        confidently.
    Both are documented here (and in docs/ARCHITECTURE.md's Restrictions
    subsection) so a future pass can revisit them deliberately, instead of
    a silent gap nobody wrote down.

    Returns a list of human-readable messages, empty if nothing obviously
    infeasible was found. An empty list is not a feasibility guarantee --
    the solve itself is still the only way to know for sure.
    """
    issues = []
    students_types = params["students_types"]
    students_types_attr = params.get("students_types_attr", {})
    modules = params["modules"]
    groups_number = params["groups_number"]
    lower_number = params["lower_number"]
    upper_number = params["upper_number"]
    attr_bounds = params["attributes"]
    preferences_bounds = params["preferences"]
    used_preferences = params.get("usedPreferences", len(preferences_bounds))
    total_students = sum(st["students"] for st in students_types.values())

    # 1. Section availability. y[i, g] is only created for a (type, group)
    # pair when that type marked itself available for the group's section
    # (see _build_vars()'s sparse construction) -- a type unavailable for
    # EVERY configured section gets no y[i, g] variables at all, so its
    # headcount-conservation constraint (sum(y[i, g] for g) == headcount)
    # sums an empty set against a positive headcount: an unsatisfiable
    # 0 == headcount.
    if modules:
        for st in students_types.values():
            if st["students"] <= 0:
                continue
            if not any(int(st["a"].get(d, 0)) == 1 for d in modules):
                issues.append(
                    f"{st['students']} student(s) aren't available for any "
                    "configured section, so they can't be placed in any "
                    "group at all."
                )

    # 2. Target group count vs. candidate groups. "Target group count"
    # requires sum(w[g] for g in G) == groups_number, and w[g] is one
    # boolean per candidate group preprocessing() builds -- asking for more
    # groups than candidate slots exist makes that sum unreachable.
    G, G_t, G_d, G_td = preprocessing(params)
    if groups_number > len(G):
        issues.append(
            f"Requested {groups_number} groups, but only {len(G)} candidate "
            "group slot(s) can be built from the configured topics"
            + (" and sections" if modules else "")
            + " -- raise the topics'/sections' group-count bounds, or "
            "lower the requested group count."
        )

    # 3. Group-size band vs. total roster. Every active group's headcount
    # must sit in [lower_number, upper_number], and exactly groups_number
    # groups are active -- so the whole roster has to fit inside
    # [groups_number * lower_number, groups_number * upper_number].
    band_lo = groups_number * lower_number
    band_hi = groups_number * upper_number
    if total_students < band_lo or total_students > band_hi:
        issues.append(
            f"{total_students} student(s) can't be split into "
            f"{groups_number} group(s) of between {lower_number} and "
            f"{upper_number} students each (that band covers {band_lo}-"
            f"{band_hi} students total)."
        )

    # 4. Attribute balance (non-solo bounds only -- see docstring above for
    # why "solo" bounds are skipped). A configured min/max on how many
    # students with a given attribute value land in an active group, added
    # for every one of the groups_number active groups, forces the roster's
    # *total* headcount with that value into
    # [groups_number * min_bound, groups_number * max_bound] too.
    for attr, values in (attr_bounds or {}).items():
        for value, bound in values.items():
            if bound.get("solo"):
                continue
            attr_key = f"{attr}:{value}"
            min_bound = int(bound["min"])
            max_bound = int(bound["max"])
            total_with_value = sum(
                st["students"] for tid, st in students_types.items()
                if students_types_attr.get(tid, {}).get(attr_key)
            )
            lo = groups_number * min_bound
            hi = groups_number * max_bound
            if total_with_value < lo or total_with_value > hi:
                issues.append(
                    f'{total_with_value} student(s) have "{attr}: {value}", '
                    f"but {groups_number} group(s) each requiring between "
                    f"{min_bound} and {max_bound} of them need a total "
                    f"between {lo} and {hi}."
                )

    # 5. Total section capacity vs. roster size. Every student ends up in
    # exactly one group, in exactly one section; section capacity is
    # enforced per section, so the sum of every section's effective
    # capacity (get_min_capacity(), already clamped to who's actually
    # available for it) has to be able to seat the whole roster.
    if modules:
        cap = get_min_capacity(params)
        total_capacity = sum(cap.values())
        if total_capacity < total_students:
            issues.append(
                f"Configured section capacity totals {total_capacity} "
                f"seat(s) across every section, short of the "
                f"{total_students} student(s) to place."
            )

    # 6. Topic coverage vs. target group count. G_t partitions the
    # candidate groups by topic, and "target group count" pins
    # sum(w[g] for g in G) == groups_number exactly -- so summing each
    # topic's own min/max bound over every topic has to bracket
    # groups_number too. The minimum only applies when every configured
    # topic is required to be used (used_preferences == every topic) --
    # matching the same condition _add_constraints() checks.
    if preferences_bounds:
        max_sum = sum(int(b["max"]) for b in preferences_bounds.values())
        if max_sum < groups_number:
            issues.append(
                f"Configured topics can host at most {max_sum} group(s) "
                f"combined, short of the {groups_number} requested."
            )
        if used_preferences == len(preferences_bounds):
            min_sum = sum(int(b["min"]) for b in preferences_bounds.values())
            if min_sum > groups_number:
                issues.append(
                    f"Configured topics require at least {min_sum} group(s) "
                    f"combined, more than the {groups_number} requested."
                )

    return issues
