import json
from enum import StrEnum
from hashlib import sha256
from math import isclose

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.concept_attributes import (
    AbilityDemand,
    ConceptAttributeCatalog,
    concept_attributes,
)
from skillforge_kb.ontology.models import (
    AssessmentStatus,
    DepthLevel,
    LearnerProfileSnapshot,
)

from .models import ABILITY_DIMENSIONS, PathNode, PathStatus, PlannerPolicy
from .serialization import build_policy_digest


class SupportIntensity(StrEnum):
    COMPACT = "compact"
    STANDARD = "standard"
    SCAFFOLDED = "scaffolded"
    REMEDIATION = "remediation"


class NodeWeightPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = "node-weight-policy.v1"
    mastery_gap_weight: float = Field(default=0.55, ge=0, le=1)
    error_risk_weight: float = Field(default=0.25, ge=0, le=1)
    ability_gap_weight: float = Field(default=0.20, ge=0, le=1)
    compact_threshold: float = Field(default=0.25, ge=0, le=1)
    scaffolded_threshold: float = Field(default=0.60, ge=0, le=1)

    @model_validator(mode="after")
    def validate_policy(self) -> "NodeWeightPolicy":
        total = self.mastery_gap_weight + self.error_risk_weight + self.ability_gap_weight
        if not isclose(total, 1.0, abs_tol=1e-9):
            raise ValueError("node weight factors must sum to 1")
        if self.compact_threshold >= self.scaffolded_threshold:
            raise ValueError("compact threshold must be below scaffolded threshold")
        return self


class FactorContribution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    factor: str = Field(min_length=1)
    normalized_value: float = Field(ge=0, le=1)
    coefficient: float = Field(ge=0, le=1)
    contribution: float = Field(ge=0, le=1)


class NodeAdaptationPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    concept_id: str = Field(min_length=1)
    delivery_depth: DepthLevel
    readiness_score: float = Field(ge=0, le=1)
    support_need_score: float = Field(ge=0, le=1)
    support_intensity: SupportIntensity
    effort_multiplier: float = Field(ge=0.5, le=2)
    assessment_emphasis: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    support_contributions: tuple[FactorContribution, ...] = ()
    readiness_contributions: tuple[FactorContribution, ...] = ()
    profile_digest: str = Field(pattern=r"^profile_[0-9a-f]{64}$")
    policy_digest: str = Field(pattern=r"^policy_[0-9a-f]{64}$")
    node_weight_policy_digest: str = Field(pattern=r"^node_policy_[0-9a-f]{64}$")

    @property
    def contributions(self) -> tuple[FactorContribution, ...]:
        return self.support_contributions

    @property
    def resource_mode(self) -> SupportIntensity:
        """Compatibility name for the canonical support-intensity decision."""
        return self.support_intensity

    @model_validator(mode="after")
    def validate_contribution_sums(self) -> "NodeAdaptationPayload":
        if not isclose(
            sum(item.contribution for item in self.support_contributions),
            self.support_need_score,
            abs_tol=1e-9,
        ):
            raise ValueError("support contributions must sum to support need score")
        if not isclose(
            sum(item.contribution for item in self.readiness_contributions),
            self.readiness_score,
            abs_tol=1e-9,
        ):
            raise ValueError("readiness contributions must sum to readiness score")
        return self


class NodeAdaptationDecision(NodeAdaptationPayload):
    adaptation_digest: str = Field(pattern=r"^adaptation_[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_adaptation_digest(self) -> "NodeAdaptationDecision":
        expected = build_adaptation_digest(
            self.model_dump(mode="json", exclude={"adaptation_digest"})
        )
        if self.adaptation_digest != expected:
            raise ValueError("adaptation digest does not match decision content")
        return self


def build_adaptation_digest(payload: object) -> str:
    return f"adaptation_{_hash(payload)}"


class NodeWeightEngine:
    def __init__(
        self,
        catalog: OntologyCatalog,
        attributes: ConceptAttributeCatalog,
        policy: PlannerPolicy | None = None,
        node_weight_policy: NodeWeightPolicy | None = None,
    ) -> None:
        self._catalog = catalog
        self._concept_ids = frozenset(item.id for item in catalog.concepts())
        if attributes.graph_version != catalog.course_document.version:
            raise ValueError("concept attribute graph version does not match catalog")
        self._attributes = attributes
        self._policy = PlannerPolicy.model_validate(
            (policy or PlannerPolicy()).model_dump()
        )
        self._node_policy = NodeWeightPolicy.model_validate(
            (node_weight_policy or NodeWeightPolicy()).model_dump()
        )
        self._policy_digest = build_policy_digest(self._policy)
        self._node_policy_digest = f"node_policy_{_hash(self._node_policy.model_dump(mode='json'))}"

    def evaluate(
        self,
        profile: LearnerProfileSnapshot,
        path_node: PathNode,
        completed_concept_ids: set[str] | None = None,
    ) -> NodeAdaptationDecision:
        if profile.graph_version != self._catalog.course_document.version:
            raise ValueError("profile graph version does not match catalog")
        if path_node.concept_id not in self._concept_ids:
            raise ValueError(f"unknown concept: {path_node.concept_id}")
        if (
            path_node.status in {PathStatus.SKIPPED, PathStatus.COMPLETED}
            or path_node.delivery_depth is None
        ):
            raise ValueError("node adaptation requires unfinished learning nodes")
        delivery_depth = path_node.delivery_depth
        completed = frozenset(completed_concept_ids or ())
        unknown_completed = completed - self._concept_ids
        if unknown_completed:
            raise ValueError(
                f"unknown completed concept: {sorted(unknown_completed)[0]}"
            )
        if path_node.concept_id in completed:
            raise ValueError("completed node cannot be adapted")
        mastery = next(
            (item for item in profile.knowledge_mastery if item.concept_id == path_node.concept_id),
            None,
        )
        mastery_is_reliable = (
            mastery is not None
            and mastery.assessment_status is AssessmentStatus.ASSESSED
            and mastery.mastery_score is not None
            and mastery.confidence >= self._policy.minimum_confidence
        )
        effective_mastery = (
            mastery.mastery_score
            if mastery_is_reliable and mastery is not None
            and mastery.mastery_score is not None
            else 0.0
        )
        attributes = concept_attributes(self._attributes, path_node.concept_id)
        ability_is_reliable = self._has_reliable_ability_evidence(profile)
        ability_fit = self._ability_fit(profile, attributes.ability_demand)
        difficulty = attributes.difficulty_prior
        ability_gap = max(0.0, difficulty - ability_fit)
        error_risk = self._error_risk(profile, path_node.concept_id)
        support_contributions: tuple[FactorContribution, ...] = (
            FactorContribution(
                factor="mastery_gap",
                normalized_value=1.0 - effective_mastery,
                coefficient=self._node_policy.mastery_gap_weight,
                contribution=self._node_policy.mastery_gap_weight
                * (1.0 - effective_mastery),
            ),
            FactorContribution(
                factor="error_risk",
                normalized_value=error_risk,
                coefficient=self._node_policy.error_risk_weight,
                contribution=self._node_policy.error_risk_weight * error_risk,
            ),
            FactorContribution(
                factor="ability_gap",
                normalized_value=ability_gap,
                coefficient=self._node_policy.ability_gap_weight,
                contribution=self._node_policy.ability_gap_weight * ability_gap,
            ),
        )
        support_floor = 0.0
        if mastery is None or mastery.assessment_status is AssessmentStatus.NOT_ASSESSED:
            support_floor = 1.0
        elif not mastery_is_reliable or not ability_is_reliable:
            support_floor = max(0.60, self._node_policy.scaffolded_threshold)
        base_support_need = sum(
            item.contribution for item in support_contributions
        )
        floor_contribution = max(0.0, support_floor - base_support_need)
        if floor_contribution:
            support_contributions = (
                *support_contributions,
                FactorContribution(
                    factor="conservative_evidence_floor",
                    normalized_value=floor_contribution,
                    coefficient=1.0,
                    contribution=floor_contribution,
                ),
            )
        support_need = sum(item.contribution for item in support_contributions)
        readiness_contributions: tuple[FactorContribution, ...] = (
            FactorContribution(
                factor="mastery_readiness",
                normalized_value=effective_mastery,
                coefficient=self._policy.mastery_weight,
                contribution=self._policy.mastery_weight * effective_mastery,
            ),
            FactorContribution(
                factor="ability_readiness",
                normalized_value=ability_fit,
                coefficient=self._policy.ability_weight,
                contribution=self._policy.ability_weight * ability_fit,
            ),
        )
        if path_node.status is PathStatus.BLOCKED:
            readiness_contributions = ()
        readiness = sum(item.contribution for item in readiness_contributions)
        if path_node.status is PathStatus.BLOCKED:
            intensity = SupportIntensity.REMEDIATION
            reasons: tuple[str, ...] = ("hard_prerequisite_blocked",)
        elif support_need >= self._node_policy.scaffolded_threshold:
            intensity = SupportIntensity.SCAFFOLDED
            reasons = ("support_need_high",)
        elif support_need >= self._node_policy.compact_threshold:
            intensity = SupportIntensity.STANDARD
            reasons = ("support_need_standard",)
        else:
            intensity = SupportIntensity.COMPACT
            reasons = ("support_need_low",)
        if not mastery_is_reliable or not ability_is_reliable:
            reasons = (*reasons, "evidence_uncertain")
        assessment = ("error_correction",) if error_risk > 0 else ()
        payload = NodeAdaptationPayload(
            concept_id=path_node.concept_id,
            delivery_depth=(
                DepthLevel.INTRO
                if path_node.status is PathStatus.BLOCKED
                else delivery_depth
            ),
            readiness_score=readiness,
            support_need_score=support_need,
            support_intensity=intensity,
            effort_multiplier=1.0 + support_need,
            assessment_emphasis=assessment,
            reason_codes=reasons,
            support_contributions=support_contributions,
            readiness_contributions=readiness_contributions,
            profile_digest=_profile_digest(profile),
            policy_digest=self._policy_digest,
            node_weight_policy_digest=self._node_policy_digest,
        )
        return NodeAdaptationDecision(
            **payload.model_dump(),
            adaptation_digest=build_adaptation_digest(payload.model_dump(mode="json")),
        )

    def _ability_fit(
        self,
        profile: LearnerProfileSnapshot,
        demand: AbilityDemand,
    ) -> float:
        if not self._has_reliable_ability_evidence(profile):
            return 0.0
        return sum(
            profile.abilities[dimension].score * demand[dimension]
            for dimension in ABILITY_DIMENSIONS
        )

    def _has_reliable_ability_evidence(
        self,
        profile: LearnerProfileSnapshot,
    ) -> bool:
        return set(profile.abilities) == set(ABILITY_DIMENSIONS) and all(
            profile.abilities[dimension].confidence >= self._policy.minimum_confidence
            for dimension in ABILITY_DIMENSIONS
        )

    @staticmethod
    def _error_risk(profile: LearnerProfileSnapshot, concept_id: str) -> float:
        return min(
            1.0,
            sum(
                pattern.ratio
                for pattern in profile.error_patterns
                if concept_id in pattern.concept_ids
            ),
        )


def _profile_digest(profile: LearnerProfileSnapshot) -> str:
    payload = profile.model_dump(mode="json", exclude={"observed_at", "generated_at"})
    return f"profile_{_hash(payload)}"


def _hash(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()
