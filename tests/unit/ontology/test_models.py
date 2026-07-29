import pytest
from pydantic import ValidationError

from skillforge_kb.ontology.models import (
    AssessmentStatus,
    Concept,
    ConceptLevel,
    DepthLevel,
    KnowledgeMastery,
    LocalizedName,
)


def _level(level: DepthLevel, threshold: float | None = None) -> ConceptLevel:
    thresholds = {
        DepthLevel.INTRO: 0.4,
        DepthLevel.INTERMEDIATE: 0.65,
        DepthLevel.ADVANCED: 0.85,
    }
    return ConceptLevel(
        level=level,
        learning_outcomes=[f"Demonstrate {level.value} understanding."],
        mastery_threshold=thresholds[level] if threshold is None else threshold,
        assessment_kinds=["concept"],
    )


def test_concept_requires_three_unique_depth_levels_in_order() -> None:
    concept = Concept(
        id="math.linear-algebra.vector",
        names=LocalizedName(zh="向量", en="Vector"),
        aliases=["向量空间"],
        summary="有序数值表示。",
        difficulty=1,
        required=True,
        evidence_status="coverage_gap",
        review_status="reviewed",
        levels=[
            _level(DepthLevel.INTRO),
            _level(DepthLevel.INTERMEDIATE),
            _level(DepthLevel.ADVANCED),
        ],
    )

    assert [level.level for level in concept.levels] == list(DepthLevel)


def test_concept_requires_increasing_mastery_thresholds() -> None:
    with pytest.raises(ValidationError, match="mastery thresholds must increase"):
        Concept(
            id="math.linear-algebra.invalid-thresholds",
            names=LocalizedName(zh="非法阈值", en="Invalid thresholds"),
            aliases=[],
            summary="Thresholds are intentionally invalid for this test.",
            difficulty=2,
            required=True,
            evidence_status="coverage_gap",
            review_status="reviewed",
            levels=[
                _level(DepthLevel.INTRO, 0.60),
                _level(DepthLevel.INTERMEDIATE, 0.50),
                _level(DepthLevel.ADVANCED, 0.80),
            ],
        )


def test_not_assessed_mastery_rejects_observed_timestamp() -> None:
    with pytest.raises(
        ValidationError,
        match="not_assessed mastery must not have a score or timestamp",
    ):
        KnowledgeMastery(
            concept_id="math.linear-algebra.vector",
            mastery_score=None,
            assessment_status=AssessmentStatus.NOT_ASSESSED,
            confidence=0.0,
            observed_at="2026-07-28T00:00:00Z",
        )


@pytest.mark.parametrize(
    "levels",
    [
        [_level(DepthLevel.INTRO), _level(DepthLevel.INTERMEDIATE)],
        [_level(DepthLevel.INTRO), _level(DepthLevel.INTRO), _level(DepthLevel.ADVANCED)],
    ],
    ids=["missing-advanced", "duplicate-intro"],
)
def test_concept_rejects_missing_or_duplicate_depth_levels(levels: list[ConceptLevel]) -> None:
    with pytest.raises(ValidationError, match="exactly one of each depth level"):
        Concept(
            id="math.linear-algebra.matrix",
            names=LocalizedName(zh="矩阵", en="Matrix"),
            aliases=[],
            summary="二维数值数组。",
            difficulty=1,
            required=True,
            evidence_status="coverage_gap",
            review_status="reviewed",
            levels=levels,
        )
