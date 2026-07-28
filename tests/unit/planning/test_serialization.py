from skillforge_kb.planning.models import PlannerPolicy
from skillforge_kb.planning.serialization import build_path_id, build_policy_digest


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


def test_policy_digest_is_stable_and_rule_sensitive() -> None:
    default = build_policy_digest(PlannerPolicy())
    repeated = build_policy_digest(PlannerPolicy())
    altered = build_policy_digest(PlannerPolicy(intermediate_threshold=0.10))

    assert default == repeated
    assert default != altered
    assert default.startswith("policy_")
