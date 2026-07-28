from skillforge_kb.planning.serialization import build_path_id


def test_path_id_is_stable_and_order_sensitive() -> None:
    first = build_path_id(
        "profile-1", "ai-course-v1", "planner-policy.v1", ["a", "b"]
    )
    repeated = build_path_id(
        "profile-1", "ai-course-v1", "planner-policy.v1", ["a", "b"]
    )
    reversed_id = build_path_id(
        "profile-1", "ai-course-v1", "planner-policy.v1", ["b", "a"]
    )

    assert first == repeated
    assert first != reversed_id
    assert first.startswith("path_")
