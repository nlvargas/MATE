"""
Tests for model_common.py's pre-solve model-size estimate and closed-form
feasibility checks: estimate_variable_count() (mirrors _build_vars()'s
variable counts exactly, without building a model) and
validate_feasibility() (sound, cheap, sufficient conditions for guaranteed
infeasibility -- see both functions' docstrings for the constraints each
check traces back to).
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


# -------------------- validate_feasibility() --------------------

def test_validate_feasibility_flags_zero_section_availability(params_factory, student_type_factory):
    # T0 marked unavailable ("a") for every configured module -- gets no
    # y[i, g] variables at all, so its headcount can never be placed.
    t0 = student_type_factory("T0", students=5, preferences={"1": "Math"}, a={"mod1": 0, "mod2": 0})
    params = params_factory(
        students_types={"T0": t0},
        preferences={"Math": {"min": 0, "max": 5}},
        modules=["mod1", "mod2"],
        groups_number=1, lower_number=1, upper_number=10,
    )
    issues = mc.validate_feasibility(params)
    assert any("aren't available for any" in msg for msg in issues)


def test_validate_feasibility_flags_too_many_requested_groups(params_factory, student_type_factory):
    t0 = student_type_factory("T0", students=3, preferences={"1": "Math"})
    params = params_factory(
        students_types={"T0": t0},
        preferences={"Math": {"min": 0, "max": 1}},  # only 1 candidate group
        modules=[],
        groups_number=5, lower_number=1, upper_number=10,
    )
    issues = mc.validate_feasibility(params)
    assert any("candidate group" in msg for msg in issues)


def test_validate_feasibility_flags_group_size_band_mismatch(params_factory, student_type_factory):
    t0 = student_type_factory("T0", students=100, preferences={"1": "Math"})
    params = params_factory(
        students_types={"T0": t0},
        preferences={"Math": {"min": 0, "max": 10}},
        modules=[],
        groups_number=2, lower_number=1, upper_number=5,  # band covers 2-10, roster is 100
    )
    issues = mc.validate_feasibility(params)
    assert any("can't be split into" in msg for msg in issues)


def test_validate_feasibility_flags_non_solo_attribute_bound(params_factory, student_type_factory):
    t0 = student_type_factory("T0", students=10, preferences={"1": "Math"})
    params = params_factory(
        students_types={"T0": t0},
        preferences={"Math": {"min": 0, "max": 5}},
        attributes={"gender": {"F": {"min": 1, "max": 2, "solo": False}}},
        modules=[],
        groups_number=2, lower_number=1, upper_number=10,
        students_types_attr={"T0": {"gender:F": 1}},
    )
    # 10 students have gender:F, but 2 groups requiring 1-2 each need a
    # total between 2 and 4 -- 10 is out of band.
    issues = mc.validate_feasibility(params)
    assert any("gender: F" in msg for msg in issues)


def test_validate_feasibility_skips_solo_attribute_bound(params_factory, student_type_factory):
    # Same numbers as the test above, but "solo": True -- the free P[g, attr]
    # opt-out variable means no closed-form total-headcount check is sound,
    # so this must NOT be flagged.
    t0 = student_type_factory("T0", students=10, preferences={"1": "Math"})
    params = params_factory(
        students_types={"T0": t0},
        preferences={"Math": {"min": 0, "max": 5}},
        attributes={"gender": {"F": {"min": 1, "max": 2, "solo": True}}},
        modules=[],
        groups_number=2, lower_number=1, upper_number=10,
        students_types_attr={"T0": {"gender:F": 1}},
    )
    issues = mc.validate_feasibility(params)
    assert not any("gender: F" in msg for msg in issues)


def test_validate_feasibility_flags_insufficient_section_capacity(params_factory, student_type_factory):
    t0 = student_type_factory("T0", students=50, preferences={"1": "Math"}, a={"mod1": 1})
    params = params_factory(
        students_types={"T0": t0},
        preferences={"Math": {"min": 0, "max": 5}},
        modules=["mod1"],
        capacity={"mod1": 10},
        groups_number=2, lower_number=1, upper_number=50,
    )
    issues = mc.validate_feasibility(params)
    assert any("section capacity totals" in msg for msg in issues)


def test_validate_feasibility_flags_topic_coverage_max_too_low(params_factory, student_type_factory):
    t0 = student_type_factory("T0", students=4, preferences={"1": "Math"})
    params = params_factory(
        students_types={"T0": t0},
        preferences={"Math": {"min": 0, "max": 1}},  # can host at most 1 group
        modules=[],
        groups_number=3, lower_number=1, upper_number=10,
    )
    issues = mc.validate_feasibility(params)
    assert any("can host at most" in msg for msg in issues)


def test_validate_feasibility_flags_topic_coverage_min_too_high_when_all_used(params_factory, student_type_factory):
    t0 = student_type_factory("T0", students=10, preferences={"1": "Math"})
    params = params_factory(
        students_types={"T0": t0},
        preferences={
            "Math": {"min": 3, "max": 5},
            "Physics": {"min": 3, "max": 5},
        },
        modules=[],
        groups_number=2,  # min_sum (3 + 3 = 6) > groups_number (2)
        lower_number=1, upper_number=10,
        used_preferences=2,  # every configured topic must be used
    )
    issues = mc.validate_feasibility(params)
    assert any("require at least" in msg for msg in issues)


def test_validate_feasibility_skips_topic_min_when_not_all_topics_required(params_factory, student_type_factory):
    # Same min bounds as above, but used_preferences < the number of
    # configured topics -- the model only enforces the per-topic minimum
    # when every configured topic must be used, so this must NOT fire.
    t0 = student_type_factory("T0", students=10, preferences={"1": "Math"})
    params = params_factory(
        students_types={"T0": t0},
        preferences={
            "Math": {"min": 3, "max": 5},
            "Physics": {"min": 3, "max": 5},
        },
        modules=[],
        groups_number=2,
        lower_number=1, upper_number=10,
        used_preferences=1,
    )
    issues = mc.validate_feasibility(params)
    assert not any("require at least" in msg for msg in issues)


def test_validate_feasibility_returns_empty_for_a_feasible_roster(params_factory, student_type_factory):
    t0 = student_type_factory("T0", students=10, preferences={"1": "Math"}, a={"mod1": 1})
    params = params_factory(
        students_types={"T0": t0},
        preferences={"Math": {"min": 0, "max": 5}},
        attributes={"gender": {"F": {"min": 0, "max": 10, "solo": False}}},
        modules=["mod1"],
        capacity={"mod1": 20},
        groups_number=2, lower_number=1, upper_number=10,
        students_types_attr={"T0": {"gender:F": 1}},
        used_preferences=1,
    )
    assert mc.validate_feasibility(params) == []
