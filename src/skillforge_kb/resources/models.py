import json
from hashlib import sha256
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from skillforge_kb.domain.enums import ContentKind, Language
from skillforge_kb.ontology.models import CONCEPT_ID_PATTERN, DepthLevel
from skillforge_kb.ontology.resource_blueprints import ResourceType
from skillforge_kb.planning.adaptation import (
    NodeAdaptationDecision,
    SupportIntensity,
)
from skillforge_kb.planning.models import PathStatus

NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class EvidenceFilters(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_version: NonEmptyString
    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    depth: DepthLevel
    languages: tuple[Language, ...] = tuple(Language)
    content_kinds: tuple[ContentKind, ...] = Field(min_length=1)
    published_only: Literal[True] = True
    allowed_license_only: Literal[True] = True


class CitationRequirements(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    min_evidence_records: int = Field(default=1, ge=1)
    required_fields: tuple[NonEmptyString, ...] = (
        "evidence_id",
        "source_id",
        "chunk_id",
        "locator",
    )


class AcceptanceChecks(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    required_resource_types: tuple[ResourceType, ...] = Field(min_length=1)
    learning_outcomes: tuple[NonEmptyString, ...] = Field(default=(), min_length=1)
    assessment_kinds: tuple[NonEmptyString, ...] = Field(default=(), min_length=1)
    immutable_path_fields: tuple[NonEmptyString, ...] = (
        "path_id",
        "concept_id",
        "sequence",
        "delivery_depth",
        "hard_prerequisite_ids",
    )


class PresentationPreferences(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    content_order: tuple[NonEmptyString, ...] = ()
    code_language: NonEmptyString | None = None
    framework: NonEmptyString | None = None
    presentation: tuple[NonEmptyString, ...] = ()
    pace_hours_per_week: float | None = Field(default=None, gt=0)
    project_orientation: NonEmptyString | None = None


class ErrorPatternHint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: NonEmptyString
    ratio: float = Field(ge=0, le=1)
    evidence_refs: tuple[NonEmptyString, ...] = ()


class ResourceBriefPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_version: NonEmptyString = "resource-brief.v1"
    path_id: str = Field(pattern=r"^path_[0-9a-f]{64}$")
    graph_version: NonEmptyString
    profile_id: NonEmptyString
    policy_digest: str = Field(pattern=r"^policy_[0-9a-f]{64}$")
    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    chapter_id: NonEmptyString
    section_id: NonEmptyString
    sequence: int = Field(ge=1)
    status: PathStatus
    delivery_depth: DepthLevel
    learning_outcomes: tuple[NonEmptyString, ...] = Field(min_length=1)
    assessment_kinds: tuple[NonEmptyString, ...] = Field(min_length=1)
    hard_prerequisite_ids: tuple[str, ...] = ()
    blocking_prerequisite_ids: tuple[str, ...] = ()
    soft_prerequisite_ids: tuple[str, ...] = ()
    related_confusion_ids: tuple[str, ...] = ()
    required_resource_types: tuple[ResourceType, ...] = Field(min_length=1)
    node_adaptation: NodeAdaptationDecision
    error_pattern_hints: tuple[ErrorPatternHint, ...] = ()
    presentation_preferences: PresentationPreferences
    evidence_filters: EvidenceFilters
    citation_requirements: CitationRequirements
    acceptance_checks: AcceptanceChecks

    @model_validator(mode="after")
    def validate_path_contract(self) -> "ResourceBriefPayload":
        if self.status in {PathStatus.SKIPPED, PathStatus.COMPLETED}:
            raise ValueError("resource briefs require unfinished learning nodes")
        if self.node_adaptation.concept_id != self.concept_id:
            raise ValueError("adaptation concept does not match brief concept")
        if self.node_adaptation.delivery_depth is not self.delivery_depth:
            raise ValueError("adaptation depth does not match brief depth")
        if self.node_adaptation.policy_digest != self.policy_digest:
            raise ValueError("adaptation policy does not match brief policy")
        if (
            self.evidence_filters.graph_version != self.graph_version
            or self.evidence_filters.concept_id != self.concept_id
            or self.evidence_filters.depth is not self.delivery_depth
        ):
            raise ValueError("evidence filters do not match brief scope")
        if (
            self.acceptance_checks.required_resource_types
            != self.required_resource_types
            or self.acceptance_checks.learning_outcomes != self.learning_outcomes
            or self.acceptance_checks.assessment_kinds != self.assessment_kinds
        ):
            raise ValueError("acceptance checks do not match brief requirements")
        if self.citation_requirements.min_evidence_records < len(
            self.evidence_filters.content_kinds
        ):
            raise ValueError("citation requirements do not cover evidence filters")
        if not set(self.blocking_prerequisite_ids).issubset(
            self.hard_prerequisite_ids
        ):
            raise ValueError("blocking prerequisites must be hard prerequisites")
        if self.status is PathStatus.BLOCKED:
            if self.delivery_depth is not DepthLevel.INTRO:
                raise ValueError("blocked resource briefs require intro depth")
            if self.node_adaptation.support_intensity is not SupportIntensity.REMEDIATION:
                raise ValueError("blocked resource briefs require remediation mode")
            if not self.blocking_prerequisite_ids:
                raise ValueError("blocked resource briefs require blocker IDs")
        elif self.blocking_prerequisite_ids:
            raise ValueError("non-blocked resource briefs cannot carry blocker IDs")
        return self


class ResourceBrief(ResourceBriefPayload):
    brief_id: str = Field(pattern=r"^brief_[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_brief_id(self) -> "ResourceBrief":
        expected = build_brief_id(self.model_dump(mode="json", exclude={"brief_id"}))
        if self.brief_id != expected:
            raise ValueError("brief ID does not match brief content")
        return self


def build_brief_id(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"brief_{sha256(canonical.encode('utf-8')).hexdigest()}"
