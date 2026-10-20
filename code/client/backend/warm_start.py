"""Constructive warm start for the CP-SAT model: builds a full assignment that satisfies the model, to be used with AddHint."""
import math
import time
from collections import defaultdict, deque

import numpy as np
from ortools.graph.python import min_cost_flow

from model_common import get_min_capacity, UNRANKED_PRIORITY


_SEARCH_SECONDS = 1.0


class _GiveUp(Exception):
    pass


def feasible_hint(model, ctx, params, verify=True):
    """Complete {variable index: value} hint for `model`, or None if none was built. verify=True re-checks every constraint."""
    try:
        y_values, w_values, topic_section = _construct(params, ctx)
        values = _complete(model, ctx, params, y_values, w_values, topic_section)
        if verify and not _satisfies_model(model, values):
            return None
        return values
    except _GiveUp:
        return None


def solution_values(model, ctx, params, groups):
    """Complete variable values for an existing assignment {group: [student ids]}, or None if it does not fit the model."""
    try:
        type_of = {str(sid): i for i in ctx["T"] for sid in ctx["students_types"][i]["students_list"]}
        group_key = {str(g): g for g in ctx["w"]}
        y_values = defaultdict(int)
        w_values = {}
        seen = set()
        for g_raw, ids in groups.items():
            g = group_key.get(str(g_raw))
            if g is None:
                return None
            for sid in ids:
                sid = str(sid)
                if sid in seen or sid not in type_of or (type_of[sid], g) not in ctx["y"]:
                    return None
                seen.add(sid)
                y_values[type_of[sid], g] += 1
                w_values[g] = 1
        if len(seen) != len(type_of):
            return None
        topic_section = {}
        if params["sameDay"] and params["modules"]:
            cell = {g: pd for pd, gs in ctx["G_td"].items() for g in gs}
            for g in w_values:
                p, d = cell[g]
                if topic_section.setdefault(p, d) != d:
                    return None
        values = _complete(model, ctx, params, y_values, w_values, topic_section)
        return values if _satisfies_model(model, values) else None
    except _GiveUp:
        return None


def _construct(params, ctx):
    ST = ctx["students_types"]
    T = ctx["T"]
    G_td, G_t = ctx["G_td"], ctx["G_t"]
    priority = ctx["priority"]
    modules = list(params["modules"])
    sections = modules or [None]
    L, U, K = params["lower_number"], params["upper_number"], params["groups_number"]
    topics = list(params["preferences"].keys())
    topic_bounds = params["preferences"]
    used_all = params["usedPreferences"] == len(topics)

    N = sum(ST[i]["students"] for i in T)
    if N == 0 or not (K * L <= N <= K * U):
        raise _GiveUp("roster does not fit the group count and size band")

    attr_specs = []
    for a, values in params["attributes"].items():
        for r, b in values.items():
            attr_specs.append((f"{a}:{r}", int(b["min"]), int(b["max"]), bool(b["solo"])))
    type_attr = {
        i: tuple(int(ctx_attr) for ctx_attr in (params["students_types_attr"][i][k] for k, *_ in attr_specs))
        for i in T
    }

    def ranked(i):
        return [t for t in ST[i]["preferences"].values() if t in topic_bounds]

    ranked_by_type = {i: ranked(i) for i in T}

    same_day = bool(params["sameDay"] and modules)
    topic_section = {}
    slots = {(p, d): len(G_td[p, d]) if modules else len(G_t[p]) for p in topics for d in sections}
    lo_p = {p: (int(topic_bounds[p]["min"]) if used_all else 0) for p in topics}
    hi_p = {p: int(topic_bounds[p]["max"]) for p in topics}
    if same_day:
        k, seats, x, best, topic_section = _same_day_plan(
            ctx, params, topics, ranked_by_type, lo_p, hi_p, slots)
    else:
        flow, K_d = _students_to_sections(ST, T, sections, params, N)
        section_students = {d: sum(flow.get((i, d), 0) for i in T) for d in sections}

        demand = defaultdict(int)
        for (i, d), n in flow.items():
            if ranked_by_type[i]:
                demand[ranked_by_type[i][0], d] += n

        k = _groups_per_cell(topics, sections, K_d, demand, slots, lo_p, hi_p)

        def place_greedy(k):
            seats = {}
            for d in sections:
                cells = [p for p in topics if k[p, d] > 0]
                if not cells:
                    continue
                lows = {p: k[p, d] * L for p in cells}
                highs = {p: k[p, d] * U for p in cells}
                s = {p: min(max(demand[p, d], lows[p]), highs[p]) for p in cells}
                diff = section_students[d] - sum(s.values())
                while diff != 0:
                    if diff > 0:
                        options = [p for p in cells if s[p] < highs[p]]
                        if not options:
                            raise _GiveUp("not enough seats")
                        p = max(options, key=lambda q: (highs[q] - s[q]))
                        s[p] += 1; diff -= 1
                    else:
                        options = [p for p in cells if s[p] > lows[p]]
                        if not options:
                            raise _GiveUp("too many seats")
                        p = max(options, key=lambda q: (s[q] - demand[q, d]))
                        s[p] -= 1; diff += 1
                for p in cells:
                    seats[p, d] = s[p]

            displaced = defaultdict(int)
            x = defaultdict(int)
            for d in sections:
                cells = [p for p in topics if (p, d) in seats]
                room = {p: seats[p, d] for p in cells}
                left = {i: flow.get((i, d), 0) for i in T if flow.get((i, d), 0) > 0}
                max_rank = max((len(ranked_by_type[i]) for i in left), default=0)
                for level in range(max_rank):
                    for p in cells:
                        claim = {i: left[i] for i in left
                                 if left[i] > 0 and len(ranked_by_type[i]) > level and ranked_by_type[i][level] == p}
                        total = sum(claim.values())
                        excess = total - room[p]
                        for _ in range(max(0, excess)):
                            i = min((i for i in claim if claim[i] > 0),
                                    key=lambda t: (displaced[t] * UNRANKED_PRIORITY + ST[t]["students"], -claim[t]))
                            claim[i] -= 1
                            displaced[i] += 1
                        for i, n in claim.items():
                            if n:
                                x[i, p, d] += n; left[i] -= n; room[p] -= n
                for i in sorted(left, key=lambda t: (displaced[t], -left[t])):
                    for _ in range(left[i]):
                        p = max((c for c in cells if room[c] > 0), key=lambda c: room[c])
                        x[i, p, d] += 1; room[p] -= 1
                    left[i] = 0
            cost = {i: 0 for i in T}
            for (i, p, d), n in x.items():
                ids = G_td[p, d] if modules else G_t[p]
                cost[i] += n * int(priority[i][ids[0]])
            return seats, x, (max(cost.values()), sum(cost.values()))

        def place_flow(k):
            seats = {}
            x = defaultdict(int)
            for d in sections:
                cells = [p for p in topics if k[p, d] > 0]
                if not cells:
                    continue
                types = [i for i in T if flow.get((i, d), 0) > 0]
                mcf = min_cost_flow.SimpleMinCostFlow()
                tnode = {i: n for n, i in enumerate(types)}
                cnode = {p: len(types) + n for n, p in enumerate(cells)}
                sink = len(types) + len(cells)
                arcs = []
                for i in types:
                    n_i = flow[i, d]
                    for p in cells:
                        ids = G_td[p, d] if modules else G_t[p]
                        pr = int(priority[i][ids[0]])
                        if pr < UNRANKED_PRIORITY:
                            arcs.append((mcf.add_arc_with_capacity_and_unit_cost(tnode[i], cnode[p], n_i, pr), i, p))
                        else:
                            for m in range(n_i):
                                c = pr + m * 5 * UNRANKED_PRIORITY + n_i
                                arcs.append((mcf.add_arc_with_capacity_and_unit_cost(tnode[i], cnode[p], 1, c), i, p))
                force = 10 ** 9
                for p in cells:
                    mcf.add_arc_with_capacity_and_unit_cost(cnode[p], sink, k[p, d] * L, -force)
                    if U > L:
                        mcf.add_arc_with_capacity_and_unit_cost(cnode[p], sink, k[p, d] * (U - L), 0)
                total = sum(flow[i, d] for i in types)
                for i in types:
                    mcf.set_node_supply(tnode[i], flow[i, d])
                mcf.set_node_supply(sink, -total)
                if mcf.solve() != mcf.OPTIMAL:
                    raise _GiveUp("placement flow infeasible")
                for arc, i, p in arcs:
                    n = mcf.flow(arc)
                    if n:
                        x[i, p, d] += n
                        seats[p, d] = seats.get((p, d), 0) + n
            return seats, x

        def score(x):
            cost = {i: 0 for i in T}
            for (i, p, d), n in x.items():
                ids = G_td[p, d] if modules else G_t[p]
                cost[i] += n * int(priority[i][ids[0]])
            return (max(cost.values()), sum(cost.values()))

        def place(k):
            candidates = []
            for build in (place_flow, place_greedy_xs):
                try:
                    seats_, x_ = build(k)
                except _GiveUp:
                    continue
                candidates.append((score(x_), len(candidates), seats_, x_))
            if not candidates:
                raise _GiveUp("no placement found")
            sc, _, seats_, x_ = min(candidates, key=lambda c: c[:2])
            return seats_, x_, sc

        def place_greedy_xs(k):
            seats_, x_, _ = place_greedy(k)
            return seats_, x_

        seats, x, best = place(k)
        deadline = time.monotonic() + _SEARCH_SECONDS
        improved = True
        while improved and time.monotonic() < deadline:
            improved = False
            for d in sections:
                for a_ in topics:
                    for b_ in topics:
                        if a_ == b_ or time.monotonic() >= deadline:
                            continue
                        total_a = sum(k[a_, e] for e in sections)
                        total_b = sum(k[b_, e] for e in sections)
                        if k[a_, d] <= 0 or total_a - 1 < lo_p[a_] or total_b + 1 > hi_p[b_] or k[b_, d] + 1 > slots[b_, d]:
                            continue
                        k[a_, d] -= 1; k[b_, d] += 1
                        try:
                            cand = place(k)
                        except _GiveUp:
                            cand = None
                        if cand is not None and cand[2] < best:
                            seats, x, best = cand
                            improved = True
                        else:
                            k[a_, d] += 1; k[b_, d] -= 1

    groups = {}
    group_cell = {}
    for d in sections:
        for p in topics:
            if (p, d) not in seats:
                continue
            ids = (G_td[p, d] if modules else G_t[p])[:k[p, d]]
            base, extra = divmod(seats[p, d], k[p, d])
            size = {g: base + (1 if n < extra else 0) for n, g in enumerate(ids)}
            students = []
            for i in T:
                students += [i] * x.get((i, p, d), 0)
            students.sort(key=lambda i: type_attr[i])
            members = {g: [] for g in ids}
            order = list(ids); pos = 0; step = 1
            for i in students:
                for _ in range(len(order) * 2):
                    g = order[pos]
                    if len(members[g]) < size[g]:
                        break
                    pos += step
                    if pos == len(order) or pos < 0:
                        step = -step; pos += step
                members[g].append(i)
                pos += step
                if pos == len(order) or pos < 0:
                    step = -step; pos += step
            for g in ids:
                groups[g] = members[g]
                group_cell[g] = (p, d)

    for cap in (best[0], best[0] + UNRANKED_PRIORITY, float("inf")):
        trial = {g: list(m) for g, m in groups.items()}
        try:
            _repair_attributes(trial, group_cell, attr_specs, type_attr, priority, sections, cap)
        except _GiveUp:
            if cap == float("inf"):
                raise
            continue
        groups = trial
        break

    y_values = defaultdict(int)
    for g, members in groups.items():
        for i in members:
            y_values[i, g] += 1
    w_values = {g: (1 if g in groups else 0) for g in ctx["G"]}
    return y_values, w_values, topic_section


def _same_day_plan(ctx, params, topics, ranked_by_type, lo_p, hi_p, slots):
    ST, T, G_td, priority = ctx["students_types"], ctx["T"], ctx["G_td"], ctx["priority"]
    modules = list(params["modules"])
    L, U, K = params["lower_number"], params["upper_number"], params["groups_number"]
    cap = get_min_capacity(params)
    forbidden = {(p, d) for d in params["fixedDay"] for p, on in params["fixedDay"][d].items() if on}

    first = defaultdict(int)
    for i in T:
        if ranked_by_type[i]:
            first[ranked_by_type[i][0]] += ST[i]["students"]
    active = sorted(topics, key=lambda p: (-first[p], str(p)))[:max(0, int(params["usedPreferences"]))]
    if not active:
        raise _GiveUp("no topic may be used")

    def room(p, d):
        return min(hi_p[p], slots[p, d])

    load = {d: 0.0 for d in modules}
    sec_of = {}
    for p in active:
        options = [d for d in modules if (p, d) not in forbidden and slots[p, d] > 0]
        if not options:
            raise _GiveUp("a used topic has no allowed section")
        d = min(options, key=lambda d: (load[d] / max(cap[d], 1), str(d)))
        sec_of[p] = d
        load[d] += first[p] + 1
    kp = dict(zip(active, _apportion(
        K, [first[p] + 0.01 for p in active],
        [lo_p[p] for p in active], [room(p, sec_of[p]) for p in active])))

    def evaluate(sec_of, kp):
        x, seats = _same_day_flow(ST, T, G_td, priority, modules, active, sec_of, kp, cap, L, U)
        cost = {i: 0 for i in T}
        for (i, p, d), n in x.items():
            cost[i] += n * int(priority[i][G_td[p, d][0]])
        return x, seats, (max(cost.values()), sum(cost.values()))

    x, seats, best = evaluate(sec_of, kp)
    deadline = time.monotonic() + 1.5 * _SEARCH_SECONDS
    improved = True
    while improved and time.monotonic() < deadline:
        improved = False
        moves = [("k", a, b) for a in active for b in active if a != b]
        moves += [("d", p, d) for p in active for d in modules if d != sec_of[p]]
        for kind, a, b in moves:
            if time.monotonic() >= deadline:
                break
            if kind == "k":
                if kp[a] - 1 < lo_p[a] or kp[b] + 1 > room(b, sec_of[b]):
                    continue
                kp[a] -= 1; kp[b] += 1
            else:
                if (a, b) in forbidden or kp[a] > room(a, b):
                    continue
                old = sec_of[a]; sec_of[a] = b
            try:
                cand = evaluate(sec_of, kp)
            except _GiveUp:
                cand = None
            if cand is not None and cand[2] < best:
                x, seats, best = cand
                improved = True
            elif kind == "k":
                kp[a] += 1; kp[b] -= 1
            else:
                sec_of[a] = old

    k = {(p, d): (kp[p] if sec_of.get(p) == d else 0) for p in topics for d in modules}
    return k, seats, x, best, dict(sec_of)


def _same_day_flow(ST, T, G_td, priority, modules, active, sec_of, kp, cap, L, U):
    mcf = min_cost_flow.SimpleMinCostFlow()
    tnode = {i: n for n, i in enumerate(T)}
    cnode = {p: len(T) + n for n, p in enumerate(active)}
    snode = {d: len(T) + len(active) + n for n, d in enumerate(modules)}
    sink = len(T) + len(active) + len(modules)
    arcs = []
    for i in T:
        n_i = ST[i]["students"]
        for p in active:
            if int(ST[i]["a"][sec_of[p]]) != 1:
                continue
            pr = int(priority[i][G_td[p, sec_of[p]][0]])
            if pr < UNRANKED_PRIORITY:
                arcs.append((mcf.add_arc_with_capacity_and_unit_cost(tnode[i], cnode[p], n_i, pr), i, p))
            else:
                for m in range(n_i):
                    c = pr + m * 5 * UNRANKED_PRIORITY + n_i
                    arcs.append((mcf.add_arc_with_capacity_and_unit_cost(tnode[i], cnode[p], 1, c), i, p))
    force = 10 ** 9
    cell_arcs = []
    for p in active:
        cell_arcs.append((p, mcf.add_arc_with_capacity_and_unit_cost(cnode[p], snode[sec_of[p]], kp[p] * L, -force)))
        if U > L:
            mcf.add_arc_with_capacity_and_unit_cost(cnode[p], snode[sec_of[p]], kp[p] * (U - L), 0)
    for d in modules:
        mcf.add_arc_with_capacity_and_unit_cost(snode[d], sink, cap[d], 0)
    total = sum(ST[i]["students"] for i in T)
    for i in T:
        mcf.set_node_supply(tnode[i], ST[i]["students"])
    mcf.set_node_supply(sink, -total)
    if mcf.solve() != mcf.OPTIMAL:
        raise _GiveUp("sameDay flow infeasible")
    x = defaultdict(int)
    seats = {}
    for arc, i, p in arcs:
        n = mcf.flow(arc)
        if n:
            d = sec_of[p]
            x[i, p, d] += n
            seats[p, d] = seats.get((p, d), 0) + n
    for p in active:
        if seats.get((p, sec_of[p]), 0) < kp[p] * L:
            raise _GiveUp("sameDay plan cannot fill a topic's groups")
    return x, seats


def _students_to_sections(ST, T, sections, params, N):
    K, L, U = params["groups_number"], params["lower_number"], params["upper_number"]
    if not params["modules"]:
        return {(i, None): ST[i]["students"] for i in T}, {None: K}
    cap = get_min_capacity(params)
    if sum(cap.values()) < N:
        raise _GiveUp("section capacity below roster size")
    available = {d: sum(ST[i]["students"] for i in T if int(ST[i]["a"][d]) == 1) for d in sections}
    for weights in (cap, available):
        K_d = dict(zip(sections, _apportion(
            K, [weights[d] for d in sections],
            [0] * len(sections), [cap[d] // L for d in sections])))
        minimum = {d: L * K_d[d] for d in sections}
        flow = _max_flow(ST, T, sections, minimum)
        if sum(flow.values()) < sum(minimum.values()):
            continue
        flow = _max_flow(ST, T, sections, {d: min(cap[d], U * K_d[d]) for d in sections}, start=flow)
        if sum(flow.values()) == N:
            return {key: n for key, n in flow.items() if n > 0}, K_d
    raise _GiveUp("students cannot be seated in sections consistently with the group counts")


def _max_flow(ST, T, sections, section_cap, start=None):
    flow = defaultdict(int, start or {})
    remaining = {i: ST[i]["students"] - sum(flow.get((i, d), 0) for d in sections) for i in T}
    free = {d: section_cap[d] - sum(flow.get((i, d), 0) for i in T) for d in sections}
    avail = {i: [d for d in sections if int(ST[i]["a"][d]) == 1] for i in T}
    while True:
        parent = {}
        queue = deque()
        for i in T:
            if remaining[i] > 0:
                parent[("t", i)] = None
                queue.append(("t", i))
        found = None
        while queue and found is None:
            node = queue.popleft()
            if node[0] == "t":
                for d in avail[node[1]]:
                    nxt = ("d", d)
                    if nxt not in parent:
                        parent[nxt] = node
                        if free[d] > 0:
                            found = nxt
                            break
                        queue.append(nxt)
            else:
                d = node[1]
                for i in T:
                    if flow.get((i, d), 0) > 0 and ("t", i) not in parent:
                        parent[("t", i)] = node
                        queue.append(("t", i))
        if found is None:
            return flow
        node = found
        free[node[1]] -= 1
        while True:
            prev = parent[node]
            if node[0] == "d":
                flow[prev[1], node[1]] += 1
            else:
                flow[node[1], prev[1]] -= 1
            node = prev
            if parent[node] is None:
                remaining[node[1]] -= 1
                break


def _apportion(total, weights, lows, highs):
    n = len(weights)
    if sum(lows) > total or sum(highs) < total:
        raise _GiveUp("cannot apportion")
    x = list(lows)
    scale = total / (sum(weights) or 1)
    target = [w * scale for w in weights]
    for _ in range(total - sum(x)):
        j = max((j for j in range(n) if x[j] < highs[j]), key=lambda j: target[j] - x[j])
        x[j] += 1
    return x


def _groups_per_cell(topics, sections, K_d, demand, slots, lo_p, hi_p):
    k = {}
    for d in sections:
        weights = [demand[p, d] + 0.01 for p in topics]
        values = _apportion(K_d[d], weights, [0] * len(topics), [slots[p, d] for p in topics])
        for p, v in zip(topics, values):
            k[p, d] = v
    col = lambda p: sum(k[p, d] for d in sections)
    for _ in range(2000):
        over = [p for p in topics if col(p) > hi_p[p]]
        under = [p for p in topics if col(p) < lo_p[p]]
        if not over and not under:
            return k
        if over:
            p = over[0]
            moved = False
            for d in sections:
                if k[p, d] == 0:
                    continue
                targets = [q for q in topics if q != p and col(q) < hi_p[q] and k[q, d] < slots[q, d]]
                if targets:
                    q = max(targets, key=lambda q: ((col(q) < lo_p[q]), demand[q, d] - k[q, d] * 7))
                    k[p, d] -= 1; k[q, d] += 1
                    moved = True
                    break
            if not moved:
                raise _GiveUp("cannot meet topic upper bound")
        else:
            p = under[0]
            moved = False
            for d in sections:
                if k[p, d] >= slots[p, d]:
                    continue
                donors = [q for q in topics if q != p and col(q) > lo_p[q] and k[q, d] > 0]
                if donors:
                    q = max(donors, key=lambda q: (col(q) > hi_p[q], col(q) - lo_p[q]))
                    k[q, d] -= 1; k[p, d] += 1
                    moved = True
                    break
            if not moved:
                raise _GiveUp("cannot meet topic lower bound")
    raise _GiveUp("topic bounds did not converge")


def _violation(counts, specs):
    total = 0
    for q, (_key, lo, hi, solo) in zip(counts, specs):
        if q > hi:
            total += q - hi
        elif solo:
            if 0 < q < lo:
                total += min(q, lo - q)
        elif q < lo:
            total += lo - q
    return total


def _repair_attributes(groups, group_cell, specs, type_attr, priority, sections, z_cap):
    n_attr = len(specs)
    counts = {g: [sum(type_attr[i][a] for i in m) for a in range(n_attr)] for g, m in groups.items()}
    viol = {g: _violation(counts[g], specs) for g in groups}
    z = defaultdict(int)
    for g, m in groups.items():
        for i in m:
            z[i] += int(priority[i][g])
    by_section = defaultdict(list)
    for g, (_p, d) in group_cell.items():
        by_section[d].append(g)

    def swap_gain(g, h, i, j):
        cg = [counts[g][a] - type_attr[i][a] + type_attr[j][a] for a in range(n_attr)]
        ch = [counts[h][a] - type_attr[j][a] + type_attr[i][a] for a in range(n_attr)]
        dv = _violation(cg, specs) + _violation(ch, specs) - viol[g] - viol[h]
        dc = (priority[i][h] + priority[j][g]) - (priority[i][g] + priority[j][h])
        return dv, dc, cg, ch

    for _ in range(5000):
        bad = [g for g in groups if viol[g] > 0]
        if not bad:
            return
        improved = False
        for g in bad:
            cell = group_cell[g]
            pools = [
                [h for h in by_section[cell[1]] if h != g and group_cell[h] == cell],
                [h for h in by_section[cell[1]] if h != g and group_cell[h] != cell],
            ]
            for pool in pools:
                best = None
                for i in sorted(set(groups[g]), key=str):
                    for h in pool:
                        for j in sorted(set(groups[h]), key=str):
                            if i == j:
                                continue
                            dv, dc, cg, ch = swap_gain(g, h, i, j)
                            if z[i] + priority[i][h] - priority[i][g] > z_cap or z[j] + priority[j][g] - priority[j][h] > z_cap:
                                continue
                            key = (dv, dc) if pool is pools[0] else (dc, dv)
                            if dv < 0 and (best is None or key < best[0]):
                                best = (key, g, h, i, j, cg, ch)
                if best:
                    _, g_, h, i, j, cg, ch = best
                    z[i] += int(priority[i][h]) - int(priority[i][g_]); z[j] += int(priority[j][g_]) - int(priority[j][h])
                    groups[g_].remove(i); groups[g_].append(j)
                    groups[h].remove(j); groups[h].append(i)
                    counts[g_], counts[h] = cg, ch
                    viol[g_], viol[h] = _violation(cg, specs), _violation(ch, specs)
                    improved = True
                    break
            if improved:
                break
        if not improved:
            raise _GiveUp("attribute bounds could not be met")
    raise _GiveUp("attribute repair did not converge")


def _complete(model, ctx, params, y_values, w_values, topic_section=None):
    proto_vars = model.Proto().variables
    values = {}
    for key, var in ctx["y"].items():
        values[var.Index()] = int(y_values.get(key, 0))
    for g, var in ctx["w"].items():
        values[var.Index()] = int(w_values.get(g, 0))
    names = {v.name: idx for idx, v in enumerate(proto_vars)}

    def put(name, val):
        if name not in names:
            raise _GiveUp(f"unexpected model: no variable {name}")
        values[names[name]] = int(val)

    T, G, G_t = ctx["T"], ctx["G"], ctx["G_t"]
    ST, priority = ctx["students_types"], ctx["priority"]
    attr = params["students_types_attr"]
    solo = {f"{a}:{r}": bool(b["solo"]) for a, vals in params["attributes"].items() for r, b in vals.items()}

    z = {i: 0 for i in T}
    unanswered = {g: 0 for g in G}
    Q = {(g, a): 0 for g in G for a in params["A"]}
    type_attrs = {i: [a for a in params["A"] if attr[i][a]] for i in T}
    for (i, g), n in y_values.items():
        if not n:
            continue
        z[i] += n * int(priority[i][g])
        if not ST[i]["answered"]:
            unanswered[g] += n
        for a in type_attrs[i]:
            Q[g, a] += n * attr[i][a]
    for i in T:
        put(f"z_{i}", z[i])
    put("z_max", max(z.values()))
    M = {g: max(0, unanswered[g] - 1) for g in G}
    for g in G:
        put(f"M_{g}", M[g])
    put("M_max", max(M.values()))
    for g in G:
        for a in params["A"]:
            q = Q[g, a]
            put(f"Q_{g}_{a}", q)
            put(f"P_{g}_{a}", 1 if (solo.get(a) and w_values.get(g, 0) == 1 and q == 0) else 0)
    topic_section = topic_section or {}
    for p in params["preferences"]:
        put(f"o_{p}", 1 if p in topic_section else 0)
    for p in params["preferences"]:
        for d in params["modules"]:
            put(f"u_{p}_{d}", 1 if topic_section.get(p) == d else 0)
    for idx, var in enumerate(proto_vars):
        if idx not in values and len(var.domain) == 2 and var.domain[0] == var.domain[1]:
            values[idx] = int(var.domain[0])
    if len(values) != len(proto_vars):
        missing = [proto_vars[i].name for i in range(len(proto_vars)) if i not in values][:5]
        raise _GiveUp(f"hint does not cover every model variable (e.g. {missing})")
    return values


def _satisfies_model(model, values):
    proto = model.Proto()
    n_vars = len(proto.variables)
    vals = np.fromiter((values[i] for i in range(n_vars)), dtype=np.int64, count=n_vars)

    def in_domain(v, dom):
        return any(dom[n] <= v <= dom[n + 1] for n in range(0, len(dom), 2))

    lo = np.empty(n_vars, dtype=np.int64); hi = np.empty(n_vars, dtype=np.int64)
    for idx, var in enumerate(proto.variables):
        dom = var.domain
        if len(dom) == 2:
            lo[idx], hi[idx] = dom[0], dom[1]
        else:
            lo[idx], hi[idx] = -(1 << 60), 1 << 60
            if not in_domain(vals[idx], list(dom)):
                return False
    if np.any(vals < lo) or np.any(vals > hi):
        return False

    def literal(lit):
        return int(vals[lit]) if lit >= 0 else 1 - int(vals[~lit])

    var_chunks, coeff_chunks, lengths, rlo, rhi = [], [], [], [], []
    for ct in proto.constraints:
        if len(ct.enforcement_literal) and not all(literal(l) for l in ct.enforcement_literal):
            continue
        if ct.has_bool_or():
            if not any(literal(l) for l in ct.bool_or.literals):
                return False
            continue
        if not ct.has_linear():
            return False
        lin = ct.linear
        dom = lin.domain
        if len(dom) != 2:
            total = sum(c * int(vals[vi]) for vi, c in zip(lin.vars, lin.coeffs))
            if not in_domain(total, list(dom)):
                return False
            continue
        var_chunks.append(np.fromiter(lin.vars, dtype=np.int64, count=len(lin.vars)))
        coeff_chunks.append(np.fromiter(lin.coeffs, dtype=np.int64, count=len(lin.coeffs)))
        lengths.append(len(lin.vars))
        rlo.append(dom[0]); rhi.append(dom[1])
    if not lengths:
        return True
    lengths = np.array(lengths, dtype=np.int64)
    terms = np.concatenate(coeff_chunks) * vals[np.concatenate(var_chunks)]
    starts = np.concatenate(([0], np.cumsum(lengths)[:-1]))
    nonempty = lengths > 0
    totals = np.zeros(len(lengths), dtype=np.int64)
    if terms.size:
        totals[nonempty] = np.add.reduceat(terms, starts[nonempty])
    return bool(np.all(totals >= np.array(rlo, dtype=np.int64)) and np.all(totals <= np.array(rhi, dtype=np.int64)))


def objective_value(model, values):
    obj = model.Proto().objective
    return obj.offset + sum(c * values[vi] for vi, c in zip(obj.vars, obj.coeffs))
