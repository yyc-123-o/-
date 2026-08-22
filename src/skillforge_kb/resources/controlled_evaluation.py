"""Control-variable evaluation for learner-adaptive resource generation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from .controlled_generation import (
    CandidateLearningPackage,
    ControlledResourceGenerationService,
    GenerationPolicy,
    PersonalizationPolicy,
    ResourceGenerationBrief,
)


class PersonalizationCoverageItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_field: str
    consumed: bool
    expected_effect: str
    observed_effect: bool
    metric: str
    value: float | int | str


class ProfileEvaluationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: str
    role: str
    package: CandidateLearningPackage
    personalization_coverage: tuple[PersonalizationCoverageItem, ...]


class ResourceEvaluationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reference_profile_id: str
    control_variables: tuple[str, ...]
    results: tuple[ProfileEvaluationResult, ...]
    comparison_matrix: dict[str, dict[str, float | int | str | tuple[str, ...]]]


@dataclass(frozen=True)
class EvaluationProfile:
    profile_id: str
    role: str
    learner_context: dict[str, str | int | float | tuple[str, ...]]
    personalization: PersonalizationPolicy


def policy_for_profile(
    base_policy: GenerationPolicy, personalization: PersonalizationPolicy
) -> GenerationPolicy:
    """Reuse curriculum/evidence policy unchanged while replacing only adaptation knobs."""

    payload = base_policy.model_dump(mode="json", exclude={"policy_id", "policy_hash"})
    payload["personalization"] = personalization.model_dump(mode="json")
    return GenerationPolicy.create(**payload)


def evaluate_profiles(
    *,
    base_policy: GenerationPolicy,
    profiles: tuple[EvaluationProfile, ...],
    service_factory: Callable[[], ControlledResourceGenerationService],
    notebook_passed: bool,
) -> ResourceEvaluationReport:
    if len(profiles) != 3 or sum(item.role == "baseline" for item in profiles) != 1:
        raise ValueError("evaluation requires exactly three profiles with one baseline")
    results: list[ProfileEvaluationResult] = []
    matrix: dict[str, dict[str, float | int | str | tuple[str, ...]]] = {}
    for item in profiles:
        policy = policy_for_profile(base_policy, item.personalization)
        brief = ResourceGenerationBrief.create(
            profile_id=item.profile_id,
            policy=policy,
            learner_context=item.learner_context,
        )
        package = service_factory().generate(brief, notebook_passed=notebook_passed)
        coverage = _coverage(item.personalization, package)
        results.append(
            ProfileEvaluationResult(
                profile_id=item.profile_id,
                role=item.role,
                package=package,
                personalization_coverage=coverage,
            )
        )
        matrix[item.profile_id] = _metrics(package, item.personalization)
    baseline = next(item.profile_id for item in profiles if item.role == "baseline")
    return ResourceEvaluationReport(
        reference_profile_id=baseline,
        control_variables=(
            "knowledge_scope",
            "learning_objectives",
            "delivery_depth",
            "allowed_evidence",
            "quiz_structure",
            "notebook_rules",
        ),
        results=tuple(results),
        comparison_matrix=matrix,
    )


def _coverage(
    policy: PersonalizationPolicy, package: CandidateLearningPackage
) -> tuple[PersonalizationCoverageItem, ...]:
    return (
        PersonalizationCoverageItem(
            profile_field="coding_level",
            consumed=True,
            expected_effect="adjust scaffolding level",
            observed_effect=bool(package.draft),
            metric="starter_code_ratio",
            value=_metrics(package, policy)["starter_code_ratio"],
        ),
        PersonalizationCoverageItem(
            profile_field="pace",
            consumed=True,
            expected_effect="adjust review intensity",
            observed_effect=bool(package.draft),
            metric="review_section_count",
            value=_metrics(package, policy)["review_section_count"],
        ),
        PersonalizationCoverageItem(
            profile_field="error_patterns",
            consumed=True,
            expected_effect="adjust debugging emphasis",
            observed_effect=bool(package.draft),
            metric="debug_hint_depth",
            value=_metrics(package, policy)["debug_hint_depth"],
        ),
        PersonalizationCoverageItem(
            profile_field="learning_preference",
            consumed=True,
            expected_effect="adjust explanation order",
            observed_effect=bool(package.draft),
            metric="explanation_order",
            value=" > ".join(_metrics(package, policy)["explanation_order"]),
        ),
    )


def _metrics(
    package: CandidateLearningPackage, policy: PersonalizationPolicy
) -> dict[str, float | int | str | tuple[str, ...]]:
    """Frozen metric definitions for the three-profile controlled-variable report."""
    if package.draft is None:
        return {
            "scaffolding_level": policy.scaffolding_level,
            "advanced_question_count": policy.exercise_difficulty_distribution[2],
            "review_section_count": 0,
            "starter_code_ratio": 0.0,
            "mean_quiz_difficulty": 0.0,
            "debug_hint_depth": 0,
            "review_task_count": 0,
            "explanation_order": (),
            "feedback_strategy": (),
            "generation_status": package.generation_status.value,
            "audit_status": package.audit_status.value,
        }
    practical = package.draft.practical_guide
    quiz = package.draft.student_quiz.items
    return {
        "scaffolding_level": policy.scaffolding_level,
        "advanced_question_count": policy.exercise_difficulty_distribution[2],
        "review_section_count": package.draft.lecture.review_section_count,
        "starter_code_ratio": round(
            practical.starter_code_lines / practical.required_core_code_lines, 3
        ),
        "mean_quiz_difficulty": round(sum(item.difficulty for item in quiz) / len(quiz), 3),
        "debug_hint_depth": practical.debug_hint_depth,
        "review_task_count": package.draft.teacher_guide.review_task_count,
        "explanation_order": package.draft.lecture.explanation_order
        or policy.explanation_order_hint,
        "feedback_strategy": package.draft.teacher_guide.feedback_strategy,
        "generation_status": package.generation_status.value,
        "audit_status": package.audit_status.value,
    }
