import json
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from skillforge_kb.ontology.models import (
    CONCEPT_ID_PATTERN,
    DepthLevel,
    LearnerProfileSnapshot,
)

_JSON_ADAPTER = TypeAdapter(object)


class ScenarioCohort(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    UNEVEN = "uneven"
    LOW_CONFIDENCE = "low_confidence"
    MISSING_EVIDENCE = "missing_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    BOUNDARY = "boundary"


class ExpectedNodeDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    should_skip: bool
    delivery_depth: DepthLevel | None

    @model_validator(mode="after")
    def validate_skip_depth(self) -> "ExpectedNodeDecision":
        if self.should_skip and self.delivery_depth is not None:
            raise ValueError("expected skipped nodes must not have a delivery depth")
        if not self.should_skip and self.delivery_depth is None:
            raise ValueError("expected learning nodes require a delivery depth")
        return self


class SyntheticPlanningCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(pattern=r"^[a-z][a-z0-9_-]+$")
    cohort: ScenarioCohort
    tags: tuple[str, ...] = Field(min_length=1)
    profile: LearnerProfileSnapshot
    expected_nodes: tuple[ExpectedNodeDecision, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case(self) -> "SyntheticPlanningCase":
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("synthetic case tags must be unique")
        concept_ids = [item.concept_id for item in self.expected_nodes]
        if len(concept_ids) != len(set(concept_ids)):
            raise ValueError("expected concept IDs must be unique")
        return self


class SyntheticPlanningDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["synthetic-planning-dataset.v1"] = (
        "synthetic-planning-dataset.v1"
    )
    data_kind: Literal["synthetic"] = "synthetic"
    data_version: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_digest: str = Field(pattern=r"^policy_[0-9a-f]{64}$")
    seed: int
    generated_at: datetime
    cases: tuple[SyntheticPlanningCase, ...] = Field(min_length=8)
    dataset_digest: str = Field(pattern=r"^synthetic_dataset_[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_dataset(self) -> "SyntheticPlanningDataset":
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("synthetic case IDs must be unique")
        for case in self.cases:
            if case.profile.graph_version != self.graph_version:
                raise ValueError("synthetic case graph version mismatch")
        expected = build_synthetic_dataset_digest(
            self.model_dump(mode="json", exclude={"dataset_digest"})
        )
        if self.dataset_digest != expected:
            raise ValueError("synthetic dataset digest does not match content")
        return self


def build_synthetic_dataset_digest(payload: object) -> str:
    serializable = _JSON_ADAPTER.dump_python(payload, mode="json")
    canonical = json.dumps(
        serializable,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"synthetic_dataset_{sha256(canonical.encode('utf-8')).hexdigest()}"
