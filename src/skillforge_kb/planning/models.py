from datetime import datetime
from enum import StrEnum
from math import isclose

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skillforge_kb.ontology.models import (
    CONCEPT_ID_PATTERN,
    GRAPH_ID_PATTERN,
    DepthLevel,
)

ABILITY_DIMENSIONS = (
    "theoretical_understanding",
    "coding_ability",
    "mathematical_foundation",
    "problem_solving",
)


class PathStatus(StrEnum):
    SKIPPED = "skipped"
    AVAILABLE = "available"
    BLOCKED = "blocked"
    PENDING = "pending"
    COMPLETED = "completed"


class ReasonCode(StrEnum):
    MASTERY_SKIP_THRESHOLD_MET = "mastery_skip_threshold_met"
    MASTERY_MISSING = "mastery_missing"
    MASTERY_LOW_CONFIDENCE = "mastery_low_confidence"
    ABILITY_INCOMPLETE = "ability_incomplete"
    ABILITY_LOW_CONFIDENCE = "ability_low_confidence"
    HARD_PREREQUISITE_UNASSESSED = "hard_prerequisite_unassessed"
    HARD_PREREQUISITE_LOW_CONFIDENCE = "hard_prerequisite_low_confidence"
    HARD_PREREQUISITE_BELOW_THRESHOLD = "hard_prerequisite_below_threshold"
    READY_FOR_INTRO = "ready_for_intro"
    READY_FOR_INTERMEDIATE = "ready_for_intermediate"
    READY_FOR_ADVANCED = "ready_for_advanced"


class AbilityWeights(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    theoretical_understanding: float = Field(default=0.30, ge=0, le=1)
    coding_ability: float = Field(default=0.25, ge=0, le=1)
    mathematical_foundation: float = Field(default=0.25, ge=0, le=1)
    problem_solving: float = Field(default=0.20, ge=0, le=1)

    def values(self) -> tuple[float, float, float, float]:
        return (
            self.theoretical_understanding,
            self.coding_ability,
            self.mathematical_foundation,
            self.problem_solving,
        )

    def __getitem__(self, dimension: str) -> float:
        if dimension == "theoretical_understanding":
            return self.theoretical_understanding
        if dimension == "coding_ability":
            return self.coding_ability
        if dimension == "mathematical_foundation":
            return self.mathematical_foundation
        if dimension == "problem_solving":
            return self.problem_solving
        raise KeyError(dimension)


class PlannerPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str = Field(default="planner-policy.v1", min_length=1)
    minimum_confidence: float = Field(default=0.60, ge=0, le=1)
    skip_mastery: float = Field(default=0.85, ge=0, le=1)
    skip_confidence: float = Field(default=0.80, ge=0, le=1)
    mastery_weight: float = Field(default=0.60, ge=0, le=1)
    ability_weight: float = Field(default=0.40, ge=0, le=1)
    intermediate_threshold: float = Field(default=0.65, ge=0, le=1)
    advanced_threshold: float = Field(default=0.85, ge=0, le=1)
    ability_weights: AbilityWeights = Field(default_factory=AbilityWeights)

    @model_validator(mode="after")
    def validate_policy(self) -> "PlannerPolicy":
        if not isclose(sum(self.ability_weights.values()), 1.0, abs_tol=1e-9):
            raise ValueError("ability weights must sum to 1")
        if not isclose(self.mastery_weight + self.ability_weight, 1.0, abs_tol=1e-9):
            raise ValueError("mastery and ability weights must sum to 1")
        if self.intermediate_threshold >= self.advanced_threshold:
            raise ValueError("intermediate threshold must be below advanced threshold")
        return self


class PathNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    title: str | None = None
    chapter_id: str = Field(pattern=GRAPH_ID_PATTERN)
    section_id: str = Field(pattern=GRAPH_ID_PATTERN)
    sequence: int = Field(ge=1)
    status: PathStatus
    delivery_depth: DepthLevel | None
    hard_prerequisite_ids: tuple[str, ...] = ()
    blocking_prerequisite_ids: tuple[str, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()

    @model_validator(mode="after")
    def validate_node(self) -> "PathNode":
        if self.status is PathStatus.SKIPPED and self.delivery_depth is not None:
            raise ValueError("skipped nodes must not have a delivery depth")
        if self.status is not PathStatus.SKIPPED and self.delivery_depth is None:
            raise ValueError("learning nodes require a delivery depth")
        if len(self.hard_prerequisite_ids) != len(set(self.hard_prerequisite_ids)):
            raise ValueError("hard prerequisite IDs must be unique")
        if len(self.blocking_prerequisite_ids) != len(set(self.blocking_prerequisite_ids)):
            raise ValueError("blocking prerequisite IDs must be unique")
        if not set(self.blocking_prerequisite_ids).issubset(self.hard_prerequisite_ids):
            raise ValueError("blocking prerequisite IDs must be hard prerequisites")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reason codes must be unique")
        return self


class PathDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = Field(default="path-decision.v1", min_length=1)
    path_id: str = Field(pattern=r"^path_[0-9a-f]{64}$")
    profile_id: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_digest: str = Field(pattern=r"^policy_[0-9a-f]{64}$")
    target_concept_id: str | None = Field(default=None, pattern=CONCEPT_ID_PATTERN)
    generated_at: datetime | None = None
    nodes: tuple[PathNode, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_nodes(self) -> "PathDecision":
        if [node.sequence for node in self.nodes] != list(range(1, len(self.nodes) + 1)):
            raise ValueError("path node sequences must be contiguous from 1")
        concept_ids = [node.concept_id for node in self.nodes]
        if len(concept_ids) != len(set(concept_ids)):
            raise ValueError("path concept IDs must be unique")
        if self.target_concept_id is not None and self.target_concept_id not in concept_ids:
            raise ValueError("target concept must be present in path")
        return self
