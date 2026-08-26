import pytest

from skillforge_kb.resources.handoff import ResourceHandoffContract


def test_handoff_copies_authoritative_path_fields(resource_case) -> None:
    brief, _ = resource_case

    handoff = ResourceHandoffContract.from_brief(brief)

    assert handoff.profile_id == brief.profile_id
    assert handoff.path_id == brief.path_id
    assert handoff.graph_version == brief.graph_version
    assert handoff.concept_id == brief.concept_id
    assert handoff.chapter_id == brief.chapter_id
    assert handoff.section_id == brief.section_id
    assert handoff.sequence == brief.sequence
    assert handoff.status is brief.status
    assert handoff.delivery_depth is brief.delivery_depth
    assert handoff.generation_gate == brief.generation_gate


def test_handoff_rejects_gate_scope_that_disagrees_with_brief(resource_case) -> None:
    brief, _ = resource_case
    gate = {
        "allowed": False,
        "status": "blocked_missing_published_evidence",
        "blocking_codes": ["blocked_missing_published_evidence"],
        "next_action": "publish evidence",
    }

    with pytest.raises(ValueError, match="generation gate"):
        ResourceHandoffContract.from_brief(brief, gate)
