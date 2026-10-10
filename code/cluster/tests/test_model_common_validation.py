"""
Tests for model_common.py's pre-solve model-size estimate:
estimate_variable_count() mirrors _build_vars()'s variable counts exactly,
without building a model, so backend/views.py's run_model() and
sensitivity() can cheaply decide whether a request solves inline or goes
to the cluster (see estimate_variable_count()'s own docstring, and
SYNC_SOLVE_MAX_VARIABLES in project/settings.py).

model_common used to also carry validate_feasibility(), a set of
closed-form pre-flight infeasibility checks run server-side on every
request. That moved to the frontend (frontend/src/containers/
CreateGroups.js's `issues`, mirrored for the parameters it can reach
client-side) so a person gets the same feedback live, while still typing,
instead of after a round-trip -- see docs/ARCHITECTURE.md's Pre-flight
feasibility checks subsection. There's nothing left to test here on the
backend for it.
"""
import model_common as mc


# -------------------- estimate_variable_count() --------------------

def test_estimate_variable_count_no_modules_matches_hand_count(params_factory, student_type_factory):
    # No modules: y is dense (T x G), and the u/o "same-day" family is
    # entirely absent (only ever declared when modules is truthy).
    t0 = student_type_factory("T0", students=3)
    t1 = student_type_factory("T1", students=2)
    params = params_factory(
        students_types={"T0": t0, "T1": t1},
        preferences={"Math": {"min": 0, "max": 2}, "Physics": {"min": 0, "max": 1}},
        attributes={"gender": {"M": {"min": 0, "max": 10}, "F": {"min": 0, "max": 10}}},
        modules=[],
    )
    # G = 2 Math groups + 1 Physics group = 3; A = 2 attribute values.
    G, _, _, _ = mc.preprocessing(params)
    assert len(G) == 3

    count = mc.estimate_variable_count(params)

    T, A = 2, 2
    y = T * len(G)             # 2 * 3 = 6
    w = len(G)                 # 3
    z = T + 1                  # 3
    q = len(G) * A             # 6
    p = len(G) * A             # 6
    m = len(G) + 1             # 4
    u = 0                      # no modules
    o = len(params["preferences"])  # 2
    assert count == y + w + z + q + p + m + u + o


def test_estimate_variable_count_with_modules_counts_sparse_y(params_factory, student_type_factory):
    # T0 is available for mod1 only, T1 for mod2 only -- y should only be
    # created for the (type, group) pairs each type is actually eligible
    # for, not the full T x G product.
    t0 = student_type_factory("T0", students=1, preferences={"1": "Math"}, a={"mod1": 1, "mod2": 0})
    t1 = student_type_factory("T1", students=1, preferences={"1": "Math"}, a={"mod1": 0, "mod2": 1})
    params = params_factory(
        students_types={"T0": t0, "T1": t1},
        preferences={"Math": {"min": 0, "max": 5}},
        modules=["mod1", "mod2"],
        upper_number=10,
    )
    G, G_t, G_d, G_td = mc.preprocessing(params)
    # One candidate group per (topic, module): Math-mod1, Math-mod2.
    assert len(G) == 2

    count = mc.estimate_variable_count(params)

    # Sparse y: T0 only eligible for the mod1 group, T1 only for the mod2
    # group -- 2 total, not 2 (types) * 2 (groups) = 4.
    y = 2
    w = len(G)                       # 2
    z = len(params["students_types"]) + 1  # 3
    A = len(params["A"])             # 0 (no attributes configured)
    q = len(G) * A
    p = len(G) * A
    m = len(G) + 1                   # 3
    u = len(params["preferences"]) * len(params["modules"])  # 1 * 2 = 2
    o = len(params["preferences"])   # 1
    assert count == y + w + z + q + p + m + u + o
