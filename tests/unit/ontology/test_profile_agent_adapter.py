from hashlib import sha256

import pytest

from skillforge_kb.ontology.profile_agent_adapter import (
    LearnerProfileAgentAdapter,
    ProfileAgentAdaptationError,
)


def _raw_profile() -> dict[str, object]:
    return {
        "profile_id": "PROFILE-LEARNER_TEST_001",
        "profile_version": "2.1",
        "generated_at": "2026-08-19T10:00:00Z",
        "learner_id": "learner_test_001",
        "knowledge_mastery": {
            "points": {
                "kp_012": {
                    "name": "卷积神经网络CNN",
                    "mastery": 0.30,
                    "status": "weak",
                    "confidence": 0.9,
                    "test_count": 2,
                },
                "kp_composite": {
                    "name": "复合概念",
                    "mastery": 0.8,
                    "status": "mastered",
                    "confidence": 0.8,
                },
            }
        },
        "ability_level": {
            "sub_dimensions": {
                "coding_ability": {"score": 0.7, "confidence": 0.8},
                "mathematical_foundation": {"score": 0.6, "confidence": 0.8},
            }
        },
        "error_patterns": {
            "items": [
                {
                    "category": "计算错误",
                    "count": 2,
                    "ratio": 0.5,
                    "involved_kp_ids": ["kp_012"],
                }
            ]
        },
        "learning_preferences": {
            "format": {
                "content_order": ["概念直觉理解", "数学推导", "代码实战"],
                "code_language": "Python",
                "framework": "PyTorch",
            },
            "style": {"visual_learner": True, "prefers_step_by_step": True},
            "pace": {"weekly_hours": 10},
            "motivation": {"project_driven": True},
        },
        "resource_generation_hints": {
            "target_chapter_id": "ch03_cnn",
            "target_depth": "进阶",
        },
    }


def test_adapts_cnn_and_reports_unmapped_legacy_points(catalog) -> None:
    adapter = LearnerProfileAgentAdapter(
        catalog,
        mappings={"kp_012": "dl.cnn.convolution"},
    )

    adapted = adapter.adapt(_raw_profile())

    assert adapted.snapshot.profile_id == "PROFILE-LEARNER_TEST_001"
    assert adapted.snapshot.graph_version == "ai-course-v1"
    assert adapted.snapshot.learner_ref == sha256(
        b"learner_test_001"
    ).hexdigest()
    assert [item.concept_id for item in adapted.snapshot.knowledge_mastery] == [
        "dl.cnn.convolution"
    ]
    assert adapted.snapshot.knowledge_mastery[0].mastery_score == 0.30
    assert adapted.snapshot.abilities["coding_ability"].score == 0.7
    assert adapted.snapshot.error_patterns[0].concept_ids == ["dl.cnn.convolution"]
    assert adapted.snapshot.preferences.framework == "PyTorch"
    assert adapted.snapshot.preferences.pace_hours_per_week == 10
    assert any(item.legacy_id == "kp_composite" for item in adapted.warnings)


def test_adapter_does_not_copy_downstream_resource_decisions(catalog) -> None:
    adapted = LearnerProfileAgentAdapter(
        catalog,
        mappings={"kp_012": "dl.cnn.convolution"},
    ).adapt(_raw_profile())

    assert not hasattr(adapted.snapshot, "resource_generation_hints")


def test_rejects_profile_graph_version_mismatch(catalog) -> None:
    raw = _raw_profile()
    raw["graph_version"] = "ai-course-v2"

    with pytest.raises(ProfileAgentAdaptationError, match="graph version"):
        LearnerProfileAgentAdapter(
            catalog,
            mappings={"kp_012": "dl.cnn.convolution"},
        ).adapt(raw)


def test_rejects_missing_identity_fields(catalog) -> None:
    raw = _raw_profile()
    del raw["learner_id"]

    with pytest.raises(ProfileAgentAdaptationError, match="learner_id"):
        LearnerProfileAgentAdapter(
            catalog,
            mappings={"kp_012": "dl.cnn.convolution"},
        ).adapt(raw)


def test_rejects_duplicate_canonical_mapping(catalog) -> None:
    with pytest.raises(ProfileAgentAdaptationError, match="duplicate canonical concept"):
        LearnerProfileAgentAdapter(
            catalog,
            mappings={
                "kp_012": "dl.cnn.convolution",
                "kp_cnn": "dl.cnn.convolution",
            },
        )


def test_requires_mastery_for_assessed_legacy_status(catalog) -> None:
    raw = _raw_profile()
    point = raw["knowledge_mastery"]["points"]["kp_012"]
    del point["mastery"]

    with pytest.raises(ProfileAgentAdaptationError, match="mastery is required"):
        LearnerProfileAgentAdapter(
            catalog,
            mappings={"kp_012": "dl.cnn.convolution"},
        ).adapt(raw)


def test_discards_numeric_mastery_for_unexplored_status(catalog) -> None:
    raw = _raw_profile()
    point = raw["knowledge_mastery"]["points"]["kp_012"]
    point["status"] = "unexplored"
    point["mastery"] = 0.03

    adapted = LearnerProfileAgentAdapter(
        catalog,
        mappings={"kp_012": "dl.cnn.convolution"},
    ).adapt(raw)

    mastery = adapted.snapshot.knowledge_mastery[0]
    assert mastery.assessment_status.value == "not_assessed"
    assert mastery.mastery_score is None
    assert any(
        warning.legacy_id == "kp_012" and "discarded" in warning.reason
        for warning in adapted.warnings
    )
