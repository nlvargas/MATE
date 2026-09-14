"""
Tests for model_common.py: building the candidate group list and its
indexes (preprocessing/create_subsets' replacement), the display-name and
student-type-key helpers, per-type preference priority, and the
(deliberately quirky) effective section-capacity computation.
"""
import model_common as mc


# -------------------- preprocessing() --------------------

def test_preprocessing_no_modules_builds_one_group_family_per_topic(params_factory, student_type_factory):
    params = params_factory(
        students_types={"T0": student_type_factory("T0", students=3)},
        preferences={"Math": {"min": 1, "max": 3}, "Physics": {"min": 0, "max": 1}},
        modules=[],
    )
    G, G_t, G_d, G_td = mc.preprocessing(params)

    assert G == ["Tema Math (N1)", "Tema Math (N2)", "Tema Math (N3)", "Tema Physics (N1)"]
    assert G_t["Math"] == ["Tema Math (N1)", "Tema Math (N2)", "Tema Math (N3)"]
    assert G_t["Physics"] == ["Tema Physics (N1)"]
    # No modules configured -- section indexes stay empty.
    assert G_d == {}
    assert G_td == {}


def test_preprocessing_with_modules_builds_topic_section_groups(params_factory, student_type_factory):
    # Two students available for mod1, none for mod2 -- disp = {mod1: 2, mod2: 0}.
    t0 = student_type_factory("T0", students=1, preferences={"1": "Math"}, a={"mod1": 1, "mod2": 0})
    t1 = student_type_factory("T1", students=1, preferences={"1": "Math"}, a={"mod1": 1, "mod2": 0})
    params = params_factory(
        students_types={"T0": t0, "T1": t1},
        preferences={"Math": {"min": 0, "max": 5}},
        modules=["mod1", "mod2"],
        upper_number=10,
    )
    G, G_t, G_d, G_td = mc.preprocessing(params)

    # modules_number[mod1]["Math"] = floor(2/10) + 1 = 1 (clipped into [0, 5]).
    # modules_number[mod2]["Math"] = floor(0/10) + 1 = 1 as well (same formula,
    # disp=0 still yields 1 -- there's always at least one candidate group).
    assert G == ["Tema Math - mod1 (N1)", "Tema Math - mod2 (N1)"]
    assert G_t["Math"] == ["Tema Math - mod1 (N1)", "Tema Math - mod2 (N1)"]
    assert G_d["mod1"] == ["Tema Math - mod1 (N1)"]
    assert G_d["mod2"] == ["Tema Math - mod2 (N1)"]
    assert G_td["Math", "mod1"] == ["Tema Math - mod1 (N1)"]


def test_preprocessing_clips_group_count_to_topic_bounds(params_factory, student_type_factory):
    # 50 students available for mod1, upper_number=5 -> floor(50/5)+1 = 11
    # candidate groups, but the topic's own max caps it at 3.
    students_list = [f"s{i}" for i in range(50)]
    t0 = student_type_factory("T0", students=50, preferences={"1": "Math"}, a={"mod1": 1},
                               students_list=students_list)
    params = params_factory(
        students_types={"T0": t0},
        preferences={"Math": {"min": 0, "max": 3}},
        modules=["mod1"],
        upper_number=5,
    )
    G, G_t, G_d, G_td = mc.preprocessing(params)

    assert len(G_t["Math"]) == 3
    assert G == [f"Tema Math - mod1 (N{n})" for n in (1, 2, 3)]


def test_preprocessing_topic_with_space_is_not_mangled(params_factory, student_type_factory):
    # Regression: a topic name containing a space used to break the OLD
    # create_subsets() (it pattern-matched on the topic's first word only).
    # preprocessing() builds G_t directly, so a multi-word topic works the
    # same as a single-word one.
    t0 = student_type_factory("T0", students=1, preferences={"1": "Data Structures"})
    params = params_factory(
        students_types={"T0": t0},
        preferences={"Data Structures": {"min": 0, "max": 2}},
        modules=[],
    )
    G, G_t, G_d, G_td = mc.preprocessing(params)

    assert G_t["Data Structures"] == ["Tema Data Structures (N1)", "Tema Data Structures (N2)"]


# -------------------- group_display_name() --------------------

def test_group_display_name_strips_tema_prefix_and_n_suffix():
    assert mc.group_display_name("Tema Math (N1)") == "Math"
    assert mc.group_display_name("Tema Data Structures - mod1 (N2)") == "Data Structures - mod1"


def test_group_display_name_leaves_a_name_without_the_prefix_alone():
    assert mc.group_display_name("Math (N1)") == "Math"


# -------------------- student_type_key() --------------------

def test_student_type_key_is_order_independent():
    key_a = mc.student_type_key({"level": "adv", "gender": "F"}, {"1": "Math", "2": "Physics"}, [])
    key_b = mc.student_type_key({"gender": "F", "level": "adv"}, {"2": "Physics", "1": "Math"}, [])
    assert key_a == key_b


def test_student_type_key_differs_on_different_content():
    key_a = mc.student_type_key({"level": "adv"}, {"1": "Math"}, [])
    key_b = mc.student_type_key({"level": "intro"}, {"1": "Math"}, [])
    assert key_a != key_b


def test_student_type_key_without_disponibilities_is_a_2_tuple():
    key = mc.student_type_key({"level": "adv"}, {"1": "Math"}, [])
    assert len(key) == 2


def test_student_type_key_with_disponibilities_keeps_position_order():
    # disponibilities is positional (index N = module N), not a dict, so it
    # must NOT be sorted -- two types differing only in module order are
    # genuinely different types.
    key_a = mc.student_type_key({}, {}, [1, 0, 1])
    key_b = mc.student_type_key({}, {}, [1, 1, 0])
    assert len(key_a) == 3
    assert key_a[-1] == (1, 0, 1)
    assert key_a != key_b


# -------------------- compute_priority() --------------------

def test_compute_priority_ranks_groups_by_preference_order(params_factory, student_type_factory):
    t0 = student_type_factory("T0", preferences={"1": "Math", "2": "Physics"})
    students_types = {"T0": t0}
    G_t = {
        "Math": ["Tema Math (N1)"],
        "Physics": ["Tema Physics (N1)"],
        "Chem": ["Tema Chem (N1)"],
    }
    priority = mc.compute_priority(students_types, G_t)

    assert priority["T0"]["Tema Math (N1)"] == 1
    assert priority["T0"]["Tema Physics (N1)"] == 2
    # Chem was never ranked by this type -- falls back to UNRANKED_PRIORITY.
    assert priority["T0"]["Tema Chem (N1)"] == mc.UNRANKED_PRIORITY


def test_compute_priority_handles_multiword_topics(params_factory, student_type_factory):
    # Regression for the bug fixed this session: priority used to be
    # computed by comparing a topic to g.split(" ")[1] (the group name's
    # first word only), so "Data Structures" never matched
    # "Tema Data Structures (N1)" and silently stayed unranked forever.
    # compute_priority() now looks the topic up directly via G_t, so this
    # works regardless of spaces in the topic name.
    t0 = student_type_factory("T0", preferences={"1": "Data Structures"})
    students_types = {"T0": t0}
    G_t = {"Data Structures": ["Tema Data Structures (N1)", "Tema Data Structures (N2)"]}

    priority = mc.compute_priority(students_types, G_t)

    assert priority["T0"]["Tema Data Structures (N1)"] == 1
    assert priority["T0"]["Tema Data Structures (N2)"] == 1


# -------------------- get_min_capacity() --------------------

def test_get_min_capacity_is_bounded_by_configured_capacity(params_factory, student_type_factory):
    # 5 student TYPES available for mod1 (regardless of how many actual
    # students each represents), configured capacity is only 3 -- capacity
    # should come out as the smaller of the two.
    types = {
        f"T{i}": student_type_factory(f"T{i}", students=10, a={"mod1": 1})
        for i in range(5)
    }
    params = params_factory(students_types=types, modules=["mod1"], capacity={"mod1": 3})

    assert mc.get_min_capacity(params) == {"mod1": 3}


def test_get_min_capacity_counts_types_not_students(params_factory, student_type_factory):
    # Documents a real, counterintuitive quirk (found while validating an
    # earlier fix this session): get_min_capacity() counts how many
    # student TYPES marked themselves available for a module, not how many
    # actual students -- so a handful of large types can produce a much
    # smaller effective capacity than the true headcount would suggest.
    # One type, 50 students, available for mod1: disponibilities["mod1"] is
    # 1 (one type), not 50.
    types = {"T0": student_type_factory("T0", students=50, a={"mod1": 1})}
    params = params_factory(students_types=types, modules=["mod1"], capacity={"mod1": 999})

    assert mc.get_min_capacity(params) == {"mod1": 1}


def test_get_min_capacity_ignores_types_not_available(params_factory, student_type_factory):
    types = {
        "T0": student_type_factory("T0", a={"mod1": 1}),
        "T1": student_type_factory("T1", a={"mod1": 0}),
    }
    params = params_factory(students_types=types, modules=["mod1"], capacity={"mod1": 999})

    assert mc.get_min_capacity(params) == {"mod1": 1}
