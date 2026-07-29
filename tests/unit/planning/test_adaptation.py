from datetime import UTC, datetime
from pathlib import Path

import pytest

from skillforge_kb.ontology.concept_attributes import load_concept_attributes
from skillforge_kb.ontology.models import (
    AbilityScore,
    AssessmentStatus,
    DepthLevel,
    KnowledgeMastery,
    LearnerProfileSnapshot,
)
from skillforge_kb.planning.adaptation import NodeWeightEngine
from skillforge_kb.planning.models import PathNode, PathStatus, PlannerPolicy


def _profile(
    catalog,
    *,
    mastery: float | None,
    confidence: float = 0.9,
    ability_scores: dict[str, float] | None = None,
    ability_confidence: float = 0.9,
) -> LearnerProfileSnapshot:
    records = []
    if mastery is not None:
        records.append(
            KnowledgeMastery(
                concept_id="math.linear-algebra.scalar",
                mastery_score=mastery,
                assessment_status=AssessmentStatus.ASSESSED,
                confidence=confidence,
                observed_at=datetime(2026, 7, 29, tzinfo=UTC),
            )
        )
    scores = ability_scores or {
        "theoretical_understanding": 0.8,
        "coding_ability": 0.7,
        "mathematical_foundation": 0.9,
        "problem_solving": 0.6,
    }
    abilities = {
        dimension: AbilityScore(
            score=score,
            confidence=ability_confidence,
            assessment_run_id="run-1",
        )
        for dimension, score in scores.items()
    }
    return LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="profile-adaptation",
        learner_ref="a" * 64,
        graph_version=catalog.course_document.version,
        knowledge_mastery=records,
        abilities=abilities,
    )


def _node(status: PathStatus = PathStatus.AVAILABLE) -> PathNode:
    return PathNode(
        concept_id="math.linear-algebra.scalar",
        chapter_id="chapter.01.math-foundations",
        section_id="section.01.linear-algebra",
        sequence=1,
        status=status,
        delivery_depth=None if status is PathStatus.SKIPPED else DepthLevel.INTRO,
    )


def _engine(catalog, policy: PlannerPolicy | None = None) -> NodeWeightEngine:
    attributes = load_concept_attributes(
        catalog,
        Path(__file__).parents[3] / "resources" / "ontology" / "concept_attributes_v1.yaml",
    )
    return NodeWeightEngine(catalog, attributes, policy)


def test_missing_mastery_requires_scaffolded_support(catalog) -> None:
    decision = _engine(catalog, PlannerPolicy()).evaluate(
        _profile(catalog, mastery=None), _node()
    )

    assert decision.support_intensity.value == "scaffolded"
    assert decision.support_need_score == 1.0


def test_blocked_node_requires_remediation_and_cannot_upgrade_depth(catalog) -> None:
    blocked = _node(PathStatus.BLOCKED).model_copy(
        update={"blocking_prerequisite_ids": ("math.linear-algebra.scalar",)}
    )
    decision = _engine(catalog, PlannerPolicy()).evaluate(
        _profile(catalog, mastery=0.9), blocked
    )

    assert decision.support_intensity.value == "remediation"
    assert decision.delivery_depth.value == "intro"


def test_adaptation_is_deterministic_and_path_node_is_unchanged(catalog) -> None:
    node = _node()
    first = _engine(catalog, PlannerPolicy()).evaluate(
        _profile(catalog, mastery=0.4), node
    )
    second = _engine(catalog, PlannerPolicy()).evaluate(
        _profile(catalog, mastery=0.4), node
    )

    assert first == second
    assert node.status is PathStatus.AVAILABLE
    assert node.delivery_depth.value == "intro"


@pytest.mark.parametrize("status", [PathStatus.SKIPPED, PathStatus.COMPLETED])
def test_adaptation_rejects_finished_nodes(catalog, status: PathStatus) -> None:
    node = _node(status)

    with pytest.raises(ValueError, match="unfinished learning nodes"):
        _engine(catalog).evaluate(_profile(catalog, mastery=0.4), node)


def test_math_node_uses_concept_specific_ability_demand(catalog) -> None:
    high_math = _profile(
        catalog,
        mastery=0.4,
        ability_scores={
            "theoretical_understanding": 0.5,
            "coding_ability": 0.2,
            "mathematical_foundation": 0.9,
            "problem_solving": 0.5,
        },
    )
    high_coding = _profile(
        catalog,
        mastery=0.4,
        ability_scores={
            "theoretical_understanding": 0.5,
            "coding_ability": 0.9,
            "mathematical_foundation": 0.2,
            "problem_solving": 0.5,
        },
    )

    assert _engine(catalog).evaluate(high_math, _node()).readiness_score > _engine(
        catalog
    ).evaluate(high_coding, _node()).readiness_score


@pytest.mark.parametrize(
    "profile_factory",
    [
        lambda catalog: _profile(catalog, mastery=0.4, confidence=0.2),
        lambda catalog: _profile(catalog, mastery=0.4, ability_confidence=0.2),
        lambda catalog: _profile(catalog, mastery=0.4).model_copy(update={"abilities": {}}),
    ],
)
def test_low_confidence_or_missing_evidence_is_at_least_scaffolded(
    catalog, profile_factory
) -> None:
    decision = _engine(catalog).evaluate(profile_factory(catalog), _node())

    assert decision.support_need_score >= 0.60
    assert decision.support_intensity.value == "scaffolded"
    assert decision.resource_mode is decision.support_intensity


def test_factor_contributions_reproduce_scores(catalog) -> None:
    decision = _engine(catalog).evaluate(_profile(catalog, mastery=None), _node())

    assert sum(item.contribution for item in decision.support_contributions) == pytest.approx(
        decision.support_need_score
    )
    assert sum(item.contribution for item in decision.readiness_contributions) == pytest.approx(
        decision.readiness_score
    )


def test_adaptation_digest_rejects_content_mutation(catalog) -> None:
    decision = _engine(catalog).evaluate(_profile(catalog, mastery=0.4), _node())
    invalid = decision.model_copy(update={"effort_multiplier": 0.5})

    with pytest.raises(ValueError, match="adaptation digest"):
        type(decision).model_validate(invalid.model_dump())


def test_completed_and_unknown_completion_ids_are_rejected(catalog) -> None:
    engine = _engine(catalog)
    profile = _profile(catalog, mastery=0.4)

    with pytest.raises(ValueError, match="completed node"):
        engine.evaluate(profile, _node(), {"math.linear-algebra.scalar"})
    with pytest.raises(ValueError, match="unknown completed concept"):
        engine.evaluate(profile, _node(), {"unknown.concept"})


def test_lower_mastery_cannot_reduce_support_need(catalog) -> None:
    engine = _engine(catalog)
    low = engine.evaluate(_profile(catalog, mastery=0.2), _node())
    high = engine.evaluate(_profile(catalog, mastery=0.8), _node())

    assert low.support_need_score >= high.support_need_score
