"""Adapters from upstream Agent handoffs to immutable generation contracts."""

from __future__ import annotations

from typing import Any

from .controlled_generation import (
    AllowedEvidence,
    EvidenceApprovalStatus,
    GenerationPolicy,
    PersonalizationPolicy,
    ResourceGenerationBrief,
)
from .demo_evidence import EvidenceBundleManifest, as_allowed_evidence


def build_brief_from_handoffs(
    *, profile: dict[str, Any], handoff: dict[str, Any], retrieval: dict[str, Any]
) -> ResourceGenerationBrief:
    """Build a draft-safe brief; upstream candidate evidence never gets release rights."""
    requirements = _mapping(handoff.get("learning_requirements"))
    gate = _mapping(handoff.get("resource_generation_gate"))
    adaptation = _mapping(handoff.get("learner_adaptation"))
    preferences = _mapping(adaptation.get("presentation_preferences"))
    ability = _mapping(adaptation.get("ability_summary"))
    mastery = _mapping(adaptation.get("source_mastery"))
    errors = _as_mappings(adaptation.get("error_pattern_hints"))
    candidates = _as_mappings(retrieval.get("candidate_evidence"))
    if not candidates:
        raise ValueError("resource generation requires selected candidate or reviewed evidence")
    prerequisites = _as_mappings(
        _mapping(handoff.get("prerequisites")).get("canonical_hard_prerequisites")
    )
    policy = GenerationPolicy.create(
        concept_id=str(handoff["concept_id"]),
        knowledge_scope=(str(handoff["concept_id"]),),
        forbidden_scope=(
            "resnet",
            "vgg",
            "transfer learning",
            "transposed convolution",
            "dcgan",
            "u-net",
        ),
        learning_objectives=tuple(str(item) for item in requirements.get("learning_outcomes", ())),
        delivery_depth=str(handoff["depth"]),
        prerequisite_gate_passed=gate.get("allowed") is True,
        unresolved_prerequisites=tuple(
            str(item["concept_id"]) for item in prerequisites if item.get("blocking") is True
        ),
        allowed_evidence=tuple(_allowed_evidence(item) for item in candidates),
        personalization=_personalization(
            mastery=float(mastery.get("mastery", 0.0)),
            coding=float(ability.get("coding_ability", 0.0)),
            preferences=preferences,
            errors=errors,
        ),
    )
    return ResourceGenerationBrief.create(
        profile_id=str(handoff.get("profile_id") or profile.get("profile_id")),
        policy=policy,
        learner_context={
            "mastery": float(mastery.get("mastery", 0.0)),
            "coding_level": float(ability.get("coding_ability", 0.0)),
            "math_level": float(ability.get("mathematical_foundation", 0.0)),
            "error_patterns": tuple(str(item.get("code")) for item in errors),
            "pace_hours_per_week": float(preferences.get("pace_hours_per_week", 0.0)),
            "presentation": tuple(str(item) for item in preferences.get("presentation", ())),
        },
    )


def attach_frozen_evidence(
    brief: ResourceGenerationBrief, bundle: EvidenceBundleManifest
) -> ResourceGenerationBrief:
    """Replace retrieval candidates with frozen, reviewable evidence without changing curriculum."""
    payload = brief.policy.model_dump(mode="json", exclude={"policy_id", "policy_hash"})
    payload["allowed_evidence"] = [
        evidence.model_dump(mode="json") for evidence in as_allowed_evidence(bundle)
    ]
    policy = GenerationPolicy.create(**payload)
    return ResourceGenerationBrief.create(
        profile_id=brief.profile_id,
        policy=policy,
        learner_context=brief.learner_context,
    )


def _allowed_evidence(item: dict[str, Any]) -> AllowedEvidence:
    review = str(item.get("review_status") or item.get("evidence_status") or "candidate")
    status = (
        EvidenceApprovalStatus.APPROVED
        if review in {"approved", "published"}
        else EvidenceApprovalStatus.REVIEWED
        if review == "reviewed"
        else EvidenceApprovalStatus.CANDIDATE
    )
    return AllowedEvidence(
        evidence_id=str(item.get("evidence_id") or item["chunk_id"]),
        source_id=str(item.get("source_id") or item.get("doc_id") or item["chunk_id"]),
        span_id=str(item["chunk_id"]),
        text=str(
            item.get("excerpt")
            or item.get("text")
            or item.get("fit_note")
            or item["chunk_id"]
        ),
        approval_status=status,
    )


def _personalization(
    *,
    mastery: float,
    coding: float,
    preferences: dict[str, Any],
    errors: tuple[dict[str, Any], ...],
) -> PersonalizationPolicy:
    scaffolding = 3 if coding < 0.45 or mastery < 0.3 else 2 if coding < 0.8 else 1
    distribution = (5, 2, 1) if scaffolding == 3 else (3, 3, 2) if scaffolding == 2 else (1, 2, 5)
    error_codes = {str(item.get("code")) for item in errors}
    return PersonalizationPolicy(
        scaffolding_level=scaffolding,
        explanation_order_hint=tuple(
            str(item) for item in preferences.get("content_order", ("intuition", "formula", "code"))
        ),
        exercise_difficulty_distribution=distribution,
        review_intensity=3 if mastery < 0.3 else 2 if mastery < 0.7 else 1,
        debugging_emphasis=3 if {"logic_jump", "calculation_error"} & error_codes else 2,
        presentation_preferences=tuple(str(item) for item in preferences.get("presentation", ())),
    )


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_mappings(value: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, dict))
