import pytest
from pydantic import ValidationError

from skillforge_kb.ontology.models import DepthLevel
from skillforge_kb.ontology.resource_blueprints import ResourceBlueprint, ResourceType
from skillforge_kb.planning.adaptation import (
    FactorContribution,
    NodeAdaptationDecision,
    NodeAdaptationPayload,
    SupportIntensity,
    build_adaptation_digest,
)
from skillforge_kb.resources import (
    QuotaVector,
    ResourceAllocation,
    ResourceAllocationPolicy,
    allocate_resources,
)


def test_intro_standard_allocation_uses_depth_plus_support_quota() -> None:
    allocation = allocate_resources(
        _blueprint(DepthLevel.INTRO, estimated_minutes=45),
        _adaptation(DepthLevel.INTRO, 0.40, SupportIntensity.STANDARD),
    )

    assert allocation.estimated_minutes == 65
    assert allocation.worked_example_count == 2
    assert allocation.guided_exercise_count == 4
    assert allocation.assessment_item_count == 5
    assert allocation.project_checkpoint_count == 1


def test_resource_types_gate_unavailable_quotas() -> None:
    allocation = allocate_resources(
        _blueprint(
            DepthLevel.ADVANCED,
            resource_types=(ResourceType.LECTURE,),
        ),
        _adaptation(DepthLevel.ADVANCED, 0.70, SupportIntensity.SCAFFOLDED),
    )

    assert allocation.worked_example_count == 0
    assert allocation.guided_exercise_count == 0
    assert allocation.assessment_item_count == 0
    assert allocation.project_checkpoint_count == 0


def test_increasing_support_never_reduces_time_or_quotas() -> None:
    blueprint = _blueprint(DepthLevel.INTRO)
    scenarios = (
        (0.10, SupportIntensity.COMPACT),
        (0.40, SupportIntensity.STANDARD),
        (0.70, SupportIntensity.SCAFFOLDED),
        (1.00, SupportIntensity.REMEDIATION),
    )
    allocations = tuple(
        allocate_resources(blueprint, _adaptation(DepthLevel.INTRO, score, intensity))
        for score, intensity in scenarios
    )

    for left, right in zip(allocations, allocations[1:], strict=False):
        assert left.estimated_minutes <= right.estimated_minutes
        assert left.worked_example_count <= right.worked_example_count
        assert left.guided_exercise_count <= right.guided_exercise_count
        assert left.assessment_item_count <= right.assessment_item_count
        assert left.project_checkpoint_count <= right.project_checkpoint_count


def test_increasing_depth_never_reduces_base_quotas() -> None:
    allocations = tuple(
        allocate_resources(
            _blueprint(depth),
            _adaptation(depth, 0.10, SupportIntensity.COMPACT),
        )
        for depth in DepthLevel
    )

    for left, right in zip(allocations, allocations[1:], strict=False):
        assert left.worked_example_count <= right.worked_example_count
        assert left.guided_exercise_count <= right.guided_exercise_count
        assert left.assessment_item_count <= right.assessment_item_count
        assert left.project_checkpoint_count <= right.project_checkpoint_count


def test_allocation_is_deterministic_and_digest_protected() -> None:
    blueprint = _blueprint(DepthLevel.INTERMEDIATE)
    adaptation = _adaptation(
        DepthLevel.INTERMEDIATE,
        0.70,
        SupportIntensity.SCAFFOLDED,
    )

    first = allocate_resources(blueprint, adaptation)
    second = allocate_resources(blueprint, adaptation)
    assert first == second
    assert ResourceAllocation.model_validate_json(first.model_dump_json()) == first

    payload = first.model_dump()
    payload["reason_codes"] = (*payload["reason_codes"], "tampered")
    with pytest.raises(ValidationError, match="allocation digest"):
        ResourceAllocation.model_validate(payload)


def test_nonmonotonic_policy_is_rejected() -> None:
    with pytest.raises(ValidationError, match="support quotas"):
        ResourceAllocationPolicy(
            standard_addition=QuotaVector(
                worked_examples=3,
                guided_exercises=3,
                assessment_items=3,
                project_checkpoints=3,
            ),
            scaffolded_addition=QuotaVector(
                worked_examples=2,
                guided_exercises=2,
                assessment_items=2,
                project_checkpoints=2,
            ),
        )


def test_blueprint_and_adaptation_scope_must_match() -> None:
    blueprint = _blueprint(DepthLevel.INTRO)

    with pytest.raises(ValueError, match="depth"):
        allocate_resources(
            blueprint,
            _adaptation(DepthLevel.INTERMEDIATE, 0.4, SupportIntensity.STANDARD),
        )
    changed = blueprint.model_copy(update={"concept_id": "math.linear-algebra.vector"})
    with pytest.raises(ValueError, match="concept"):
        allocate_resources(
            changed,
            _adaptation(DepthLevel.INTRO, 0.4, SupportIntensity.STANDARD),
        )


def _blueprint(
    depth: DepthLevel,
    *,
    estimated_minutes: int | None = None,
    resource_types: tuple[ResourceType, ...] = tuple(ResourceType),
) -> ResourceBlueprint:
    minutes = estimated_minutes or {
        DepthLevel.INTRO: 45,
        DepthLevel.INTERMEDIATE: 60,
        DepthLevel.ADVANCED: 75,
    }[depth]
    return ResourceBlueprint(
        graph_version="ai-course-v1",
        concept_id="math.linear-algebra.scalar",
        depth=depth,
        learning_outcomes=("Explain the concept",),
        assessment_kinds=("short_answer",),
        resource_types=resource_types,
        estimated_minutes=minutes,
    )


def _adaptation(
    depth: DepthLevel,
    support_score: float,
    intensity: SupportIntensity,
) -> NodeAdaptationDecision:
    contributions = ()
    if support_score:
        contributions = (
            FactorContribution(
                factor="test_support",
                normalized_value=support_score,
                coefficient=1.0,
                contribution=support_score,
            ),
        )
    payload = NodeAdaptationPayload(
        concept_id="math.linear-algebra.scalar",
        delivery_depth=depth,
        readiness_score=0.0,
        support_need_score=support_score,
        support_intensity=intensity,
        effort_multiplier=1.0 + support_score,
        reason_codes=(f"support_{intensity.value}",),
        support_contributions=contributions,
        readiness_contributions=(),
        profile_digest="profile_" + "1" * 64,
        policy_digest="policy_" + "2" * 64,
        node_weight_policy_digest="node_policy_" + "3" * 64,
    )
    return NodeAdaptationDecision(
        **payload.model_dump(),
        adaptation_digest=build_adaptation_digest(payload.model_dump(mode="json")),
    )
