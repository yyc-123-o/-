import json
from hashlib import sha256
from typing import Annotated, Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from skillforge_kb.ontology.models import CONCEPT_ID_PATTERN, DepthLevel
from skillforge_kb.ontology.resource_blueprints import ResourceType

from .evidence_bundle import EvidenceBundle
from .models import ResourceBrief

NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class EvidenceBoundItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: NonEmptyString
    citations: tuple["CitationRecord", ...] = Field(min_length=1)

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(citation.evidence_id for citation in self.citations)


class CitationRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str = Field(pattern=r"^evidence_[0-9a-f]{64}$")
    source_id: NonEmptyString
    chunk_id: NonEmptyString
    locator: NonEmptyString
    normalized_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ResourceArtifactBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path_id: str = Field(pattern=r"^path_[0-9a-f]{64}$")
    graph_version: NonEmptyString
    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    delivery_depth: DepthLevel
    sequence: int = Field(ge=1)
    hard_prerequisite_ids: tuple[str, ...] = ()
    covered_learning_outcomes: tuple[NonEmptyString, ...] = Field(min_length=1)
    items: tuple[EvidenceBoundItem, ...] = Field(min_length=1)


class LectureResource(ResourceArtifactBase):
    resource_type: Literal[ResourceType.LECTURE] = ResourceType.LECTURE


class PracticalGuideResource(ResourceArtifactBase):
    resource_type: Literal[ResourceType.PRACTICAL_GUIDE] = ResourceType.PRACTICAL_GUIDE


class AssessmentResource(ResourceArtifactBase):
    resource_type: Literal[ResourceType.ASSESSMENT] = ResourceType.ASSESSMENT
    assessment_kinds: tuple[NonEmptyString, ...] = Field(min_length=1)


class ProjectResource(ResourceArtifactBase):
    resource_type: Literal[ResourceType.PROJECT] = ResourceType.PROJECT


GeneratedArtifact = Annotated[
    LectureResource
    | PracticalGuideResource
    | AssessmentResource
    | ProjectResource,
    Field(discriminator="resource_type"),
]


class ValidatedResourcePackage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    result_id: str = Field(pattern=r"^resource_result_[0-9a-f]{64}$")
    brief_id: str = Field(pattern=r"^brief_[0-9a-f]{64}$")
    bundle_id: str = Field(pattern=r"^bundle_[0-9a-f]{64}$")
    artifacts: tuple[GeneratedArtifact, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result_id(self) -> "ValidatedResourcePackage":
        expected = build_resource_result_id(
            self.model_dump(mode="json", exclude={"result_id"})
        )
        if self.result_id != expected:
            raise ValueError("resource result ID does not match package content")
        return self


def build_resource_result_id(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"resource_result_{sha256(canonical.encode('utf-8')).hexdigest()}"


class ResourceGenerator(Protocol):
    def generate(
        self,
        brief: ResourceBrief,
        bundle: EvidenceBundle,
    ) -> tuple[GeneratedArtifact, ...]: ...
