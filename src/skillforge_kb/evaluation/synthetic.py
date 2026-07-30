from collections import defaultdict
from datetime import UTC, datetime
from hashlib import sha256
from random import Random

from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import (
    AbilityScore,
    AssessmentStatus,
    DepthLevel,
    KnowledgeMastery,
    LearnerProfileSnapshot,
    Relation,
    RelationKind,
)
from skillforge_kb.planning.models import ABILITY_DIMENSIONS, PlannerPolicy
from skillforge_kb.planning.ordering import stable_required_concept_ids
from skillforge_kb.planning.serialization import build_policy_digest

from .models import (
    ExpectedNodeDecision,
    ScenarioCohort,
    SyntheticPlanningCase,
    SyntheticPlanningDataset,
    build_synthetic_dataset_digest,
)

DEFAULT_SYNTHETIC_CASE_COUNT = 60
DEFAULT_SYNTHETIC_SEED = 20260730
DEFAULT_GENERATED_AT = datetime(2026, 7, 30, tzinfo=UTC)
DEFAULT_DATA_VERSION = "synthetic-planning.v1"


def generate_synthetic_dataset(
    catalog: OntologyCatalog,
    policy: PlannerPolicy | None = None,
    *,
    case_count: int = DEFAULT_SYNTHETIC_CASE_COUNT,
    seed: int = DEFAULT_SYNTHETIC_SEED,
    data_version: str = DEFAULT_DATA_VERSION,
    generated_at: datetime = DEFAULT_GENERATED_AT,
) -> SyntheticPlanningDataset:
    if case_count < len(ScenarioCohort):
        raise ValueError("synthetic generation requires at least eight cases")
    active_policy = PlannerPolicy.model_validate((policy or PlannerPolicy()).model_dump())
    rng = Random(seed)
    cohort_ordinals: defaultdict[ScenarioCohort, int] = defaultdict(int)
    cases: list[SyntheticPlanningCase] = []
    cohorts = tuple(ScenarioCohort)
    for index in range(case_count):
        cohort = cohorts[index % len(cohorts)]
        cohort_ordinals[cohort] += 1
        case_id = f"{cohort.value}-{cohort_ordinals[cohort]:03d}"
        profile, tags = _build_profile(
            catalog,
            active_policy,
            cohort,
            cohort_ordinals[cohort],
            case_id,
            rng,
            generated_at,
        )
        cases.append(
            SyntheticPlanningCase(
                case_id=case_id,
                cohort=cohort,
                tags=tags,
                profile=profile,
                expected_nodes=_expected_nodes(catalog, profile, active_policy),
            )
        )
    case_records = tuple(cases)
    policy_digest = build_policy_digest(active_policy)
    payload = {
        "schema_version": "synthetic-planning-dataset.v1",
        "data_kind": "synthetic",
        "data_version": data_version,
        "graph_version": catalog.course_document.version,
        "policy_version": active_policy.version,
        "policy_digest": policy_digest,
        "seed": seed,
        "generated_at": generated_at,
        "cases": case_records,
    }
    return SyntheticPlanningDataset(
        data_version=data_version,
        graph_version=catalog.course_document.version,
        policy_version=active_policy.version,
        policy_digest=policy_digest,
        seed=seed,
        generated_at=generated_at,
        cases=case_records,
        dataset_digest=build_synthetic_dataset_digest(payload),
    )


def _build_profile(
    catalog: OntologyCatalog,
    policy: PlannerPolicy,
    cohort: ScenarioCohort,
    cohort_ordinal: int,
    case_id: str,
    rng: Random,
    generated_at: datetime,
) -> tuple[LearnerProfileSnapshot, tuple[str, ...]]:
    concept_ids = stable_required_concept_ids(catalog)
    mastery_values: dict[str, tuple[float, float]] = {}
    ability_values: dict[str, tuple[float, float]] = {}
    variant = "default"

    if cohort is ScenarioCohort.BEGINNER:
        mastery_values = _uniform_mastery(concept_ids, rng, 0.10, 0.35, 0.82, 0.95)
        ability_values = _uniform_abilities(rng, 0.15, 0.35, 0.85, 0.95)
    elif cohort is ScenarioCohort.INTERMEDIATE:
        mastery_values = _uniform_mastery(concept_ids, rng, 0.66, 0.78, 0.85, 0.95)
        ability_values = _uniform_abilities(rng, 0.68, 0.80, 0.85, 0.95)
    elif cohort is ScenarioCohort.ADVANCED:
        mastery_values = _uniform_mastery(concept_ids, rng, 0.80, 0.84, 0.88, 0.98)
        ability_values = _uniform_abilities(rng, 0.92, 0.98, 0.88, 0.98)
    elif cohort is ScenarioCohort.UNEVEN:
        for index, concept_id in enumerate(concept_ids):
            if index % 3 == cohort_ordinal % 3:
                mastery_values[concept_id] = (rng.uniform(0.78, 0.84), rng.uniform(0.85, 0.95))
            else:
                mastery_values[concept_id] = (rng.uniform(0.25, 0.48), rng.uniform(0.85, 0.95))
        ability_values = {
            dimension: (
                rng.uniform(0.75, 0.92)
                if index % 2 == cohort_ordinal % 2
                else rng.uniform(0.25, 0.45),
                rng.uniform(0.85, 0.95),
            )
            for index, dimension in enumerate(ABILITY_DIMENSIONS)
        }
        variant = "alternating_strengths"
    elif cohort is ScenarioCohort.LOW_CONFIDENCE:
        low_confidence = max(0.0, policy.minimum_confidence - 0.05)
        mastery_values = {
            concept_id: (rng.uniform(0.75, 0.95), low_confidence)
            for concept_id in concept_ids
        }
        ability_values = {
            dimension: (rng.uniform(0.80, 0.95), low_confidence)
            for dimension in ABILITY_DIMENSIONS
        }
    elif cohort is ScenarioCohort.MISSING_EVIDENCE:
        variant_index = (cohort_ordinal - 1) % 3
        if variant_index in {1, 2}:
            mastery_values = _uniform_mastery(concept_ids, rng, 0.35, 0.55, 0.85, 0.95)
        if variant_index == 1:
            ability_values = {}
            variant = "missing_abilities"
        elif variant_index == 2:
            ability_values = _uniform_abilities(rng, 0.45, 0.65, 0.85, 0.95)
            mastery_values = {}
            variant = "missing_mastery"
        else:
            variant = "missing_mastery_and_abilities"
    elif cohort is ScenarioCohort.CONFLICTING_EVIDENCE:
        if cohort_ordinal % 2:
            mastery_values = _uniform_mastery(concept_ids, rng, 0.80, 0.84, 0.88, 0.96)
            ability_values = _uniform_abilities(rng, 0.10, 0.25, 0.88, 0.96)
            variant = "high_mastery_low_ability"
        else:
            mastery_values = _uniform_mastery(concept_ids, rng, 0.20, 0.40, 0.88, 0.96)
            ability_values = _uniform_abilities(rng, 0.90, 0.98, 0.88, 0.96)
            variant = "low_mastery_high_ability"
    else:
        delta = (-0.001, 0.0, 0.001)[(cohort_ordinal - 1) % 3]
        mastery = _clamp(policy.skip_mastery + delta)
        confidence = _clamp(policy.skip_confidence + delta)
        mastery_values = {
            concept_id: (mastery, confidence) for concept_id in concept_ids
        }
        ability_values = {
            dimension: (_clamp(policy.advanced_threshold + delta), 0.95)
            for dimension in ABILITY_DIMENSIONS
        }
        variant = ("below_threshold", "at_threshold", "above_threshold")[(cohort_ordinal - 1) % 3]

    assessment_run_id = f"assessment-{case_id}"
    mastery_records = [
        KnowledgeMastery(
            concept_id=concept_id,
            mastery_score=score,
            assessment_status=AssessmentStatus.ASSESSED,
            confidence=confidence,
            observed_at=generated_at,
            evidence_refs=[assessment_run_id],
        )
        for concept_id, (score, confidence) in mastery_values.items()
    ]
    abilities = {
        dimension: AbilityScore(
            score=score,
            confidence=confidence,
            assessment_run_id=assessment_run_id,
        )
        for dimension, (score, confidence) in ability_values.items()
    }
    profile = LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id=f"synthetic-{case_id}",
        learner_ref=sha256(case_id.encode("utf-8")).hexdigest(),
        graph_version=catalog.course_document.version,
        observed_at=generated_at,
        generated_at=generated_at,
        assessment_runs=[assessment_run_id] if mastery_records or abilities else [],
        knowledge_mastery=mastery_records,
        abilities=abilities,
    )
    return profile, (cohort.value, variant)


def _uniform_mastery(
    concept_ids: list[str],
    rng: Random,
    score_min: float,
    score_max: float,
    confidence_min: float,
    confidence_max: float,
) -> dict[str, tuple[float, float]]:
    return {
        concept_id: (
            rng.uniform(score_min, score_max),
            rng.uniform(confidence_min, confidence_max),
        )
        for concept_id in concept_ids
    }


def _uniform_abilities(
    rng: Random,
    score_min: float,
    score_max: float,
    confidence_min: float,
    confidence_max: float,
) -> dict[str, tuple[float, float]]:
    return {
        dimension: (
            rng.uniform(score_min, score_max),
            rng.uniform(confidence_min, confidence_max),
        )
        for dimension in ABILITY_DIMENSIONS
    }


def _expected_nodes(
    catalog: OntologyCatalog,
    profile: LearnerProfileSnapshot,
    policy: PlannerPolicy,
) -> tuple[ExpectedNodeDecision, ...]:
    mastery = {item.concept_id: item for item in profile.knowledge_mastery}
    ability_score = _reliable_ability_score(profile, policy)
    incoming: defaultdict[str, list[Relation]] = defaultdict(list)
    for relation in catalog.relations(RelationKind.HARD_PREREQUISITE):
        incoming[relation.target].append(relation)

    decisions: list[ExpectedNodeDecision] = []
    for concept_id in stable_required_concept_ids(catalog):
        concept_mastery = mastery.get(concept_id)
        should_skip = bool(
            concept_mastery is not None
            and concept_mastery.assessment_status is AssessmentStatus.ASSESSED
            and concept_mastery.mastery_score is not None
            and concept_mastery.mastery_score >= policy.skip_mastery
            and concept_mastery.confidence >= policy.skip_confidence
        )
        if should_skip:
            decisions.append(
                ExpectedNodeDecision(
                    concept_id=concept_id,
                    should_skip=True,
                    delivery_depth=None,
                )
            )
            continue

        blocked = any(
            _prerequisite_blocks(mastery.get(relation.source), relation, policy)
            for relation in incoming[concept_id]
        )
        depth = _expected_depth(concept_mastery, ability_score, blocked, policy)
        decisions.append(
            ExpectedNodeDecision(
                concept_id=concept_id,
                should_skip=False,
                delivery_depth=depth,
            )
        )
    return tuple(decisions)


def _reliable_ability_score(
    profile: LearnerProfileSnapshot,
    policy: PlannerPolicy,
) -> float | None:
    if set(profile.abilities) != set(ABILITY_DIMENSIONS):
        return None
    if any(
        profile.abilities[dimension].confidence < policy.minimum_confidence
        for dimension in ABILITY_DIMENSIONS
    ):
        return None
    return sum(
        profile.abilities[dimension].score * policy.ability_weights[dimension]
        for dimension in ABILITY_DIMENSIONS
    )


def _prerequisite_blocks(
    mastery: KnowledgeMastery | None,
    relation: Relation,
    policy: PlannerPolicy,
) -> bool:
    if relation.min_mastery is None:
        raise ValueError("hard prerequisite relation requires min_mastery")
    return bool(
        mastery is None
        or mastery.assessment_status is AssessmentStatus.NOT_ASSESSED
        or mastery.mastery_score is None
        or mastery.confidence < policy.minimum_confidence
        or mastery.mastery_score < relation.min_mastery
    )


def _expected_depth(
    mastery: KnowledgeMastery | None,
    ability_score: float | None,
    blocked: bool,
    policy: PlannerPolicy,
) -> DepthLevel:
    if (
        mastery is None
        or mastery.assessment_status is AssessmentStatus.NOT_ASSESSED
        or mastery.mastery_score is None
        or mastery.confidence < policy.minimum_confidence
        or ability_score is None
        or blocked
    ):
        return DepthLevel.INTRO
    readiness = (
        mastery.mastery_score * policy.mastery_weight
        + ability_score * policy.ability_weight
    )
    if readiness >= policy.advanced_threshold:
        return DepthLevel.ADVANCED
    if readiness >= policy.intermediate_threshold:
        return DepthLevel.INTERMEDIATE
    return DepthLevel.INTRO


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
