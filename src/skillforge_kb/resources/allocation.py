import json
from hashlib import sha256
from math import ceil

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skillforge_kb.ontology.models import CONCEPT_ID_PATTERN, DepthLevel
from skillforge_kb.ontology.resource_blueprints import ResourceBlueprint, ResourceType
from skillforge_kb.planning.adaptation import (
    NodeAdaptationDecision,
    SupportIntensity,
)

_QUOTA_FIELDS = (
    "worked_examples",
    "guided_exercises",
    "assessment_items",
    "project_checkpoints",
)


class QuotaVector(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    worked_examples: int = Field(default=0, strict=True, ge=0)
    guided_exercises: int = Field(default=0, strict=True, ge=0)
    assessment_items: int = Field(default=0, strict=True, ge=0)
    project_checkpoints: int = Field(default=0, strict=True, ge=0)

    def plus(self, other: "QuotaVector") -> "QuotaVector":
        return QuotaVector(
            worked_examples=self.worked_examples + other.worked_examples,
            guided_exercises=self.guided_exercises + other.guided_exercises,
            assessment_items=self.assessment_items + other.assessment_items,
            project_checkpoints=self.project_checkpoints + other.project_checkpoints,
        )


class ResourceAllocationPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = Field(default="resource-allocation-policy.v1", min_length=1)
    minute_rounding: int = Field(default=5, strict=True, ge=1, le=30)
    intro_quota: QuotaVector = QuotaVector(
        worked_examples=1,
        guided_exercises=3,
        assessment_items=4,
        project_checkpoints=1,
    )
    intermediate_quota: QuotaVector = QuotaVector(
        worked_examples=2,
        guided_exercises=5,
        assessment_items=6,
        project_checkpoints=2,
    )
    advanced_quota: QuotaVector = QuotaVector(
        worked_examples=3,
        guided_exercises=7,
        assessment_items=8,
        project_checkpoints=3,
    )
    compact_addition: QuotaVector = QuotaVector()
    standard_addition: QuotaVector = QuotaVector(
        worked_examples=1,
        guided_exercises=1,
        assessment_items=1,
    )
    scaffolded_addition: QuotaVector = QuotaVector(
        worked_examples=2,
        guided_exercises=3,
        assessment_items=2,
        project_checkpoints=1,
    )
    remediation_addition: QuotaVector = QuotaVector(
        worked_examples=3,
        guided_exercises=5,
        assessment_items=4,
        project_checkpoints=2,
    )

    @model_validator(mode="after")
    def validate_monotonicity(self) -> "ResourceAllocationPolicy":
        _require_monotonic(
            (self.intro_quota, self.intermediate_quota, self.advanced_quota),
            "depth quotas",
        )
        _require_monotonic(
            (
                self.compact_addition,
                self.standard_addition,
                self.scaffolded_addition,
                self.remediation_addition,
            ),
            "support quotas",
        )
        return self


class ResourceAllocation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_version: str = Field(min_length=1)
    policy_digest: str = Field(pattern=r"^allocation_policy_[0-9a-f]{64}$")
    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    delivery_depth: DepthLevel
    support_intensity: SupportIntensity
    resource_types: tuple[ResourceType, ...] = Field(min_length=1)
    blueprint_estimated_minutes: int = Field(strict=True, ge=1)
    effort_multiplier: float = Field(ge=0.5, le=2)
    minute_rounding: int = Field(strict=True, ge=1, le=30)
    estimated_minutes: int = Field(strict=True, ge=1)
    worked_example_count: int = Field(strict=True, ge=0)
    guided_exercise_count: int = Field(strict=True, ge=0)
    assessment_item_count: int = Field(strict=True, ge=0)
    project_checkpoint_count: int = Field(strict=True, ge=0)
    reason_codes: tuple[str, ...] = Field(min_length=1)
    allocation_digest: str = Field(pattern=r"^resource_allocation_[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_allocation(self) -> "ResourceAllocation":
        if len(self.resource_types) != len(set(self.resource_types)):
            raise ValueError("resource allocation types must be unique")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("resource allocation reason codes must be unique")
        expected_minutes = _rounded_minutes(
            self.blueprint_estimated_minutes,
            self.effort_multiplier,
            self.minute_rounding,
        )
        if self.estimated_minutes != expected_minutes:
            raise ValueError("resource allocation minutes do not match source facts")
        resource_types = set(self.resource_types)
        if ResourceType.PRACTICAL_GUIDE not in resource_types and (
            self.worked_example_count or self.guided_exercise_count
        ):
            raise ValueError("practical quotas require a practical guide")
        if ResourceType.ASSESSMENT not in resource_types and self.assessment_item_count:
            raise ValueError("assessment quotas require an assessment resource")
        if ResourceType.PROJECT not in resource_types and self.project_checkpoint_count:
            raise ValueError("project quotas require a project resource")
        expected_digest = build_resource_allocation_digest(
            self.model_dump(mode="json", exclude={"allocation_digest"})
        )
        if self.allocation_digest != expected_digest:
            raise ValueError("resource allocation digest does not match content")
        return self


def allocate_resources(
    blueprint: ResourceBlueprint,
    adaptation: NodeAdaptationDecision,
    policy: ResourceAllocationPolicy | None = None,
) -> ResourceAllocation:
    blueprint = ResourceBlueprint.model_validate(blueprint.model_dump())
    adaptation = NodeAdaptationDecision.model_validate(adaptation.model_dump())
    active_policy = ResourceAllocationPolicy.model_validate(
        (policy or ResourceAllocationPolicy()).model_dump()
    )
    if blueprint.concept_id != adaptation.concept_id:
        raise ValueError("resource blueprint concept does not match adaptation concept")
    if blueprint.depth is not adaptation.delivery_depth:
        raise ValueError("resource blueprint depth does not match adaptation depth")
    if len(blueprint.resource_types) != len(set(blueprint.resource_types)):
        raise ValueError("resource blueprint types must be unique")

    depth_quota = _depth_quota(active_policy, blueprint.depth)
    support_quota = _support_quota(active_policy, adaptation.support_intensity)
    requested = set(blueprint.resource_types)
    combined = depth_quota.plus(support_quota)
    practical = ResourceType.PRACTICAL_GUIDE in requested
    policy_digest = build_resource_allocation_policy_digest(active_policy)
    estimated_minutes = _rounded_minutes(
        blueprint.estimated_minutes,
        adaptation.effort_multiplier,
        active_policy.minute_rounding,
    )
    worked_example_count = combined.worked_examples if practical else 0
    guided_exercise_count = combined.guided_exercises if practical else 0
    assessment_item_count = (
        combined.assessment_items if ResourceType.ASSESSMENT in requested else 0
    )
    project_checkpoint_count = (
        combined.project_checkpoints if ResourceType.PROJECT in requested else 0
    )
    reason_codes = (
        f"depth_{blueprint.depth.value}",
        f"support_{adaptation.support_intensity.value}",
        "blueprint_minutes_scaled",
        "resource_types_applied",
    )
    payload = {
        "policy_version": active_policy.version,
        "policy_digest": policy_digest,
        "concept_id": blueprint.concept_id,
        "delivery_depth": blueprint.depth,
        "support_intensity": adaptation.support_intensity,
        "resource_types": blueprint.resource_types,
        "blueprint_estimated_minutes": blueprint.estimated_minutes,
        "effort_multiplier": adaptation.effort_multiplier,
        "minute_rounding": active_policy.minute_rounding,
        "estimated_minutes": estimated_minutes,
        "worked_example_count": worked_example_count,
        "guided_exercise_count": guided_exercise_count,
        "assessment_item_count": assessment_item_count,
        "project_checkpoint_count": project_checkpoint_count,
        "reason_codes": reason_codes,
    }
    return ResourceAllocation(
        policy_version=active_policy.version,
        policy_digest=policy_digest,
        concept_id=blueprint.concept_id,
        delivery_depth=blueprint.depth,
        support_intensity=adaptation.support_intensity,
        resource_types=blueprint.resource_types,
        blueprint_estimated_minutes=blueprint.estimated_minutes,
        effort_multiplier=adaptation.effort_multiplier,
        minute_rounding=active_policy.minute_rounding,
        estimated_minutes=estimated_minutes,
        worked_example_count=worked_example_count,
        guided_exercise_count=guided_exercise_count,
        assessment_item_count=assessment_item_count,
        project_checkpoint_count=project_checkpoint_count,
        reason_codes=reason_codes,
        allocation_digest=build_resource_allocation_digest(payload),
    )


def build_resource_allocation_policy_digest(
    policy: ResourceAllocationPolicy,
) -> str:
    return f"allocation_policy_{_hash(policy.model_dump(mode='json'))}"


def build_resource_allocation_digest(payload: object) -> str:
    return f"resource_allocation_{_hash(payload)}"


def _depth_quota(
    policy: ResourceAllocationPolicy,
    depth: DepthLevel,
) -> QuotaVector:
    if depth is DepthLevel.INTRO:
        return policy.intro_quota
    if depth is DepthLevel.INTERMEDIATE:
        return policy.intermediate_quota
    return policy.advanced_quota


def _support_quota(
    policy: ResourceAllocationPolicy,
    intensity: SupportIntensity,
) -> QuotaVector:
    if intensity is SupportIntensity.COMPACT:
        return policy.compact_addition
    if intensity is SupportIntensity.STANDARD:
        return policy.standard_addition
    if intensity is SupportIntensity.SCAFFOLDED:
        return policy.scaffolded_addition
    return policy.remediation_addition


def _require_monotonic(values: tuple[QuotaVector, ...], label: str) -> None:
    for left, right in zip(values, values[1:], strict=False):
        if any(getattr(left, field) > getattr(right, field) for field in _QUOTA_FIELDS):
            raise ValueError(f"resource allocation {label} must be monotonic")


def _rounded_minutes(base_minutes: int, multiplier: float, rounding: int) -> int:
    return ceil(base_minutes * multiplier / rounding) * rounding


def _hash(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
