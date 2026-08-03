import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
SAMPLE_ROOT = ROOT / "examples" / "simulations" / "profile-2026-0001-demo"


def test_cnn_resource_handoff_is_identity_consistent_and_blocked() -> None:
    handoff = json.loads(
        (SAMPLE_ROOT / "resource_agent_handoff_cnn_0803.json").read_text(
            encoding="utf-8"
        )
    )
    planning_result = json.loads(
        (SAMPLE_ROOT / "planning_result.json").read_text(encoding="utf-8")
    )
    path = planning_result["path"]
    node = next(
        item
        for item in path["nodes"]
        if item["concept_id"] == "dl.cnn.convolution"
    )
    adaptation = next(
        item
        for item in planning_result["adaptations"]
        if item["concept_id"] == "dl.cnn.convolution"
    )
    current_node = handoff["current_node"]
    allocation = handoff["resource_requirements"]["allocation"]
    resources = {
        item["type"]: item
        for item in handoff["resource_requirements"]["resources"]
    }

    assert handoff["profile_id"] == path["profile_id"]
    assert handoff["learner_id"] == "LRN-2026-AI02"
    assert handoff["path_id"] == path["path_id"]
    assert handoff["graph_version"] == path["graph_version"]
    assert handoff["concept_id"] == node["concept_id"] == adaptation["concept_id"]
    assert handoff["depth"] == node["delivery_depth"] == adaptation["delivery_depth"]
    assert handoff["identity_consistency"]["path_id_matches_path"] is True
    assert allocation["concept_id"] == handoff["concept_id"]
    assert allocation["delivery_depth"] == handoff["depth"]
    assert current_node["concept_id"] == handoff["concept_id"]
    assert current_node["chapter_id"] == node["chapter_id"]
    assert current_node["section_id"] == node["section_id"]
    assert current_node["sequence"] == node["sequence"] == 58
    assert handoff["node_order"] == {
        "sequence": 58,
        "order_basis": "path.nodes.sequence",
    }
    assert current_node["delivery_depth"] == handoff["depth"]
    assert current_node["status"] == node["status"] == "blocked"
    assert current_node["blocking_prerequisite_ids"] == [
        "dl.vision.image-tensor"
    ]
    assert handoff["learning_requirements"]["delivery_difficulty"] == handoff["depth"]
    assert handoff["learning_requirements"]["learning_outcomes"]
    assert handoff["prerequisites"]["blocking_conditions"]
    assert handoff["identity_consistency"]["passed"] is True
    assert handoff["resource_generation_gate"]["allowed"] is False
    assert handoff["resource_generation_gate"]["draft_generation_allowed"] is False
    assert handoff["retrieval_context"]["evidence"] == []
    retrieval_request = handoff["retrieval_context"]["request"]
    assert retrieval_request["learner_id"] == handoff["learner_id"]
    assert retrieval_request["difficulty_filter"] == handoff["depth"]
    assert retrieval_request["learner_profile"]["level"] == "intermediate"
    assert handoff["retrieval_context"]["concept_evidence"][handoff["concept_id"]][
        "evidence_status"
    ] == "candidate_only"
    assert all(
        item["evidence_status"] == "candidate_only"
        for item in handoff["retrieval_context"]["candidate_evidence"]
    )
    assert sum(
        item["suggested_minutes"]
        for item in handoff["resource_requirements"]["resources"]
    ) == allocation["estimated_minutes"]
    assert handoff["resource_requirements"]["required_resource_types"] == [
        "lecture",
        "practical_guide",
        "assessment",
    ]
    assert set(resources) == {"lecture", "practical_guide", "assessment"}
    assert {
        resource_type: resource["suggested_minutes"]
        for resource_type, resource in resources.items()
    } == {"lecture": 30, "practical_guide": 45, "assessment": 15}
    assert all(resource["content_requirements"] for resource in resources.values())
    assert all(
        resource["status"] == "deferred_until_unblocked"
        for resource in resources.values()
    )
