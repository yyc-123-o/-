from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import cast

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .catalog import OntologyCatalog
from .models import (
    CONCEPT_ID_PATTERN,
    AbilityScore,
    AssessmentStatus,
    DiagnosticItemEvidence,
    ErrorPattern,
    KnowledgeMastery,
    LearnerProfileSnapshot,
    LearningPreferences,
)

PROFILE_AGENT_MAP_VERSION = "profile-agent-kp-map-v1"
ADAPTER_VERSION = "profile-agent-adapter.v1"
ASSESSED_LEGACY_STATUSES = frozenset(
    {"mastered", "familiar", "partial", "weak", "not_learned"}
)


class ProfileAgentAdaptationError(ValueError):
    """Raised when a learner-profile Agent payload cannot be normalized."""


class ProfileAgentAdaptationWarning(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    legacy_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class AdaptedLearnerProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot: LearnerProfileSnapshot
    source_profile_version: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)
    suggested_target_concept_id: str | None = Field(
        default=None,
        pattern=CONCEPT_ID_PATTERN,
    )
    warnings: tuple[ProfileAgentAdaptationWarning, ...] = ()


class ProfileAgentMapDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    mappings: dict[str, str] = Field(default_factory=dict)
    expansions: dict[str, tuple[str, ...]] = Field(default_factory=dict)


class LearnerProfileAgentAdapter:
    """Normalize the standalone v2.1 profile output into platform facts."""

    def __init__(
        self,
        catalog: OntologyCatalog,
        mappings: Mapping[str, str],
        *,
        expansions: Mapping[str, tuple[str, ...]] | None = None,
        adapter_version: str = ADAPTER_VERSION,
    ) -> None:
        self._catalog = catalog
        self._adapter_version = adapter_version
        self._mappings = dict(mappings)
        self._expansions = {
            legacy_id: tuple(concept_ids)
            for legacy_id, concept_ids in (expansions or {}).items()
        }
        concept_ids = [*self._mappings.values(), *sum(self._expansions.values(), ())]
        if len(set(concept_ids)) != len(concept_ids):
            raise ProfileAgentAdaptationError("duplicate canonical concept mapping")
        for legacy_id, concept_id in self._mappings.items():
            if not isinstance(legacy_id, str) or not legacy_id:
                raise ProfileAgentAdaptationError("mapping legacy ID must be non-empty")
            if not isinstance(concept_id, str) or not concept_id:
                raise ProfileAgentAdaptationError(
                    f"mapping target must be non-empty: {legacy_id}"
                )
            try:
                catalog.get_concept(concept_id)
            except KeyError as exc:
                raise ProfileAgentAdaptationError(
                    f"mapping targets unknown concept: {concept_id}"
                ) from exc
        for legacy_id, expanded_ids in self._expansions.items():
            if not isinstance(legacy_id, str) or not legacy_id:
                raise ProfileAgentAdaptationError("expansion legacy ID must be non-empty")
            if not expanded_ids:
                raise ProfileAgentAdaptationError(
                    f"expansion must contain at least one concept: {legacy_id}"
                )
            for concept_id in expanded_ids:
                try:
                    catalog.get_concept(concept_id)
                except KeyError as exc:
                    raise ProfileAgentAdaptationError(
                        f"expansion targets unknown concept: {concept_id}"
                    ) from exc

    @classmethod
    def load_mappings(
        cls,
        catalog: OntologyCatalog,
        path: Path,
    ) -> LearnerProfileAgentAdapter:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            document = ProfileAgentMapDocument.model_validate(raw)
        except (OSError, yaml.YAMLError, TypeError, ValueError) as exc:
            raise ProfileAgentAdaptationError(
                f"invalid learner profile mapping file: {path}"
            ) from exc
        if document.version != PROFILE_AGENT_MAP_VERSION:
            raise ProfileAgentAdaptationError("profile Agent map version is not supported")
        if document.graph_version != catalog.course_document.version:
            raise ProfileAgentAdaptationError("profile Agent map graph version mismatch")
        return cls(catalog, document.mappings, expansions=document.expansions)

    def adapt(self, raw: Mapping[str, object]) -> AdaptedLearnerProfile:
        payload = _mapping(raw, "profile")
        profile_version = _string(payload.get("profile_version"), "profile_version")
        if profile_version != "2.1":
            raise ProfileAgentAdaptationError(
                f"unsupported learner profile Agent version: {profile_version}"
            )
        profile_id = _string(payload.get("profile_id"), "profile_id")
        learner_id = _string(payload.get("learner_id"), "learner_id")
        generated_at = _parse_datetime(payload.get("generated_at"), "generated_at")
        graph_version = payload.get("graph_version", self._catalog.course_document.version)
        if graph_version != self._catalog.course_document.version:
            raise ProfileAgentAdaptationError("profile graph version does not match catalog")

        warnings: list[ProfileAgentAdaptationWarning] = []
        _validate_profile_consistency(payload, profile_id, warnings)
        if "graph_version" not in payload:
            warnings.append(
                ProfileAgentAdaptationWarning(
                    legacy_id=profile_id,
                    reason="graph_version inferred from the versioned catalog",
                )
            )

        runs = _assessment_runs(payload, profile_id)
        mastery = self._adapt_mastery(
            payload.get("knowledge_mastery"),
            generated_at,
            warnings,
        )
        diagnostic_evidence = self._adapt_diagnostic_evidence(
            payload.get("diagnostic_evidence", []),
            warnings,
        )
        abilities = self._adapt_abilities(payload.get("ability_level"), runs[0])
        errors = self._adapt_errors(payload.get("error_patterns"), warnings)
        preferences = self._adapt_preferences(payload.get("learning_preferences"))
        suggested_target = self._adapt_target_hint(payload.get("learning_scope"), warnings)
        snapshot = LearnerProfileSnapshot(
            schema_version="learner-profile.v1",
            profile_id=profile_id,
            learner_ref=sha256(learner_id.encode("utf-8")).hexdigest(),
            graph_version=self._catalog.course_document.version,
            generated_at=generated_at,
            assessment_runs=runs,
            knowledge_mastery=mastery,
            diagnostic_evidence=diagnostic_evidence,
            abilities=abilities,
            error_patterns=errors,
            preferences=preferences,
        )
        return AdaptedLearnerProfile(
            snapshot=snapshot,
            source_profile_version=profile_version,
            adapter_version=self._adapter_version,
            suggested_target_concept_id=suggested_target,
            warnings=tuple(warnings),
        )

    def _adapt_diagnostic_evidence(
        self,
        value: object,
        warnings: list[ProfileAgentAdaptationWarning],
    ) -> list[DiagnosticItemEvidence]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ProfileAgentAdaptationError("diagnostic_evidence must be a list")
        result: list[DiagnosticItemEvidence] = []
        for index, raw_item in enumerate(value):
            item = _mapping(raw_item, f"diagnostic_evidence[{index}]")
            item_id = _string(item.get("item_id"), f"diagnostic_evidence[{index}].item_id")
            legacy_id = _string(item.get("concept_id"), f"diagnostic_evidence[{index}].concept_id")
            concept_ids = self._canonical_targets(legacy_id)
            if len(concept_ids) != 1:
                warnings.append(
                    ProfileAgentAdaptationWarning(
                        legacy_id=legacy_id,
                        reason="diagnostic evidence must map to exactly one concept",
                    )
                )
                continue
            correct = item.get("correct")
            if not isinstance(correct, bool):
                raise ProfileAgentAdaptationError(
                    f"diagnostic_evidence[{index}].correct must be a boolean"
                )
            error_code = item.get("error_code")
            if error_code is not None:
                error_code = _string(error_code, f"diagnostic_evidence[{index}].error_code")
            observed_at = item.get("observed_at")
            result.append(
                DiagnosticItemEvidence(
                    item_id=item_id,
                    concept_id=concept_ids[0],
                    correct=correct,
                    error_code=error_code,
                    observed_at=_parse_datetime(
                        observed_at,
                        f"diagnostic_evidence[{index}].observed_at",
                    )
                    if observed_at is not None
                    else None,
                )
            )
        return result

    def _adapt_target_hint(
        self,
        value: object,
        warnings: list[ProfileAgentAdaptationWarning],
    ) -> str | None:
        if value is None:
            return None
        scope = _mapping(value, "learning_scope")
        legacy_id = scope.get("primary_kp_id")
        if legacy_id is None:
            return None
        legacy_id = _string(legacy_id, "learning_scope.primary_kp_id")
        concept_id = self._mappings.get(legacy_id)
        if concept_id is None:
            warnings.append(
                ProfileAgentAdaptationWarning(
                    legacy_id=legacy_id,
                    reason="target hint is unmapped or composite and was ignored",
                )
            )
            return None
        return concept_id

    def _adapt_mastery(
        self,
        value: object,
        fallback_observed_at: datetime,
        warnings: list[ProfileAgentAdaptationWarning],
    ) -> list[KnowledgeMastery]:
        dimension = _mapping(value, "knowledge_mastery")
        points = _mapping(dimension.get("points"), "knowledge_mastery.points")
        result: list[KnowledgeMastery] = []
        seen: set[str] = set()
        for legacy_id, value in points.items():
            concept_ids = self._canonical_targets(legacy_id)
            if not concept_ids:
                warnings.append(
                    ProfileAgentAdaptationWarning(
                        legacy_id=legacy_id,
                        reason="unmapped or composite learner-profile knowledge point",
                    )
                )
                continue
            point = _mapping(value, f"knowledge_mastery.points.{legacy_id}")
            status = _string(
                point.get("status", "unexplored"),
                f"knowledge_mastery.points.{legacy_id}.status",
            )
            if status not in {*ASSESSED_LEGACY_STATUSES, "unexplored"}:
                raise ProfileAgentAdaptationError(
                    f"knowledge_mastery.points.{legacy_id}.unsupported status: {status}"
                )
            score = _optional_score(
                point.get("mastery"),
                f"knowledge_mastery.points.{legacy_id}.mastery",
            )
            confidence = _score(
                point.get("confidence", 0.0),
                f"knowledge_mastery.points.{legacy_id}.confidence",
            )
            evidence_refs = _string_list(
                point.get("evidence_refs", []),
                f"knowledge_mastery.points.{legacy_id}.evidence_refs",
            )
            observed_at = None
            if status != "unexplored":
                if score is None:
                    raise ProfileAgentAdaptationError(
                        f"knowledge_mastery.points.{legacy_id}.mastery is required"
                    )
                observed_at = _parse_datetime(
                    point.get("observed_at") or point.get("last_tested") or fallback_observed_at,
                    f"knowledge_mastery.points.{legacy_id}.observed_at",
                )
            elif score is not None:
                warnings.append(
                    ProfileAgentAdaptationWarning(
                        legacy_id=legacy_id,
                        reason="numeric mastery discarded for unexplored status",
                    )
                )
            for concept_id in concept_ids:
                if concept_id in seen:
                    warnings.append(
                        ProfileAgentAdaptationWarning(
                            legacy_id=legacy_id,
                            reason=f"duplicate canonical concept skipped: {concept_id}",
                        )
                    )
                    continue
                seen.add(concept_id)
                result.append(
                    KnowledgeMastery(
                        concept_id=concept_id,
                        mastery_score=score if status != "unexplored" else None,
                        assessment_status=(
                            AssessmentStatus.ASSESSED
                            if status != "unexplored"
                            else AssessmentStatus.NOT_ASSESSED
                        ),
                        confidence=confidence,
                        observed_at=observed_at,
                        evidence_refs=evidence_refs,
                    )
                )
        return result

    def _canonical_targets(self, legacy_id: str) -> tuple[str, ...]:
        if legacy_id in self._mappings:
            return (self._mappings[legacy_id],)
        return self._expansions.get(legacy_id, ())

    def _adapt_abilities(self, value: object, assessment_run_id: str) -> dict[str, AbilityScore]:
        if value is None:
            return {}
        dimension = _mapping(value, "ability_level")
        raw_dimensions = _mapping(
            dimension.get("sub_dimensions", {}),
            "ability_level.sub_dimensions",
        )
        result: dict[str, AbilityScore] = {}
        for name, raw_value in raw_dimensions.items():
            item = _mapping(raw_value, f"ability_level.sub_dimensions.{name}")
            score = _optional_score(
                item.get("score"),
                f"ability_level.sub_dimensions.{name}.score",
            )
            # The diagnosis Agent now reports unavailable dimensions as null
            # when it has no evidence. Preserve that distinction by omitting
            # the dimension from the canonical snapshot instead of inventing
            # a zero score.
            if score is None:
                continue
            result[name] = AbilityScore(
                score=score,
                confidence=_score(
                    item.get("confidence", 0.0),
                    f"ability_level.sub_dimensions.{name}.confidence",
                ),
                assessment_run_id=assessment_run_id,
            )
        return result

    def _adapt_errors(
        self,
        value: object,
        warnings: list[ProfileAgentAdaptationWarning],
    ) -> list[ErrorPattern]:
        if value is None:
            return []
        dimension = _mapping(value, "error_patterns")
        items = dimension.get("items", [])
        if not isinstance(items, list):
            raise ProfileAgentAdaptationError("error_patterns.items must be a list")
        result: list[ErrorPattern] = []
        for index, raw_value in enumerate(items):
            item = _mapping(raw_value, f"error_patterns.items[{index}]")
            legacy_ids = _string_list(
                item.get("involved_kp_ids", []),
                f"error_patterns.items[{index}].involved_kp_ids",
            )
            concept_ids: list[str] = []
            for legacy_id in legacy_ids:
                concept_id = self._mappings.get(legacy_id)
                if concept_id is None:
                    warnings.append(
                        ProfileAgentAdaptationWarning(
                            legacy_id=legacy_id,
                            reason="error pattern references unmapped knowledge point",
                        )
                    )
                    continue
                if concept_id not in concept_ids:
                    concept_ids.append(concept_id)
            result.append(
                ErrorPattern(
                    code=_string(
                        item.get("category", "unknown"),
                        f"error_patterns.items[{index}].category",
                    ),
                    count=_nonnegative_int(
                        item.get("count", 0),
                        f"error_patterns.items[{index}].count",
                    ),
                    ratio=_score(
                        item.get("ratio", 0.0),
                        f"error_patterns.items[{index}].ratio",
                    ),
                    concept_ids=concept_ids,
                    evidence_refs=_string_list(
                        item.get("evidence_refs", []),
                        f"error_patterns.items[{index}].evidence_refs",
                    ),
                )
            )
        return result

    @staticmethod
    def _adapt_preferences(value: object) -> LearningPreferences:
        if value is None:
            return LearningPreferences()
        preferences = _mapping(value, "learning_preferences")
        format_preferences = _mapping(preferences.get("format", {}), "learning_preferences.format")
        style_preferences = _mapping(preferences.get("style", {}), "learning_preferences.style")
        pace_preferences = _mapping(preferences.get("pace", {}), "learning_preferences.pace")
        motivation = _mapping(
            preferences.get("motivation", {}),
            "learning_preferences.motivation",
        )
        presentation = [
            name
            for source, name in (
                ("visual_learner", "visual"),
                ("prefers_diagrams", "diagrams"),
                ("prefers_math_formulas", "math_formulas"),
                ("prefers_step_by_step", "step_by_step"),
                ("prefers_comparison_tables", "comparison_tables"),
            )
            if style_preferences.get(source, False) is True
        ]
        project_orientation = "project_driven" if motivation.get("project_driven") else None
        return LearningPreferences(
            content_order=_string_list(
                format_preferences.get("content_order", []),
                "learning_preferences.format.content_order",
            ),
            code_language=_optional_string(
                format_preferences.get("code_language"),
                "learning_preferences.format.code_language",
            ),
            framework=_optional_string(
                format_preferences.get("framework"),
                "learning_preferences.format.framework",
            ),
            presentation=presentation,
            pace_hours_per_week=_optional_positive_number(
                pace_preferences.get("weekly_hours"),
                "learning_preferences.pace.weekly_hours",
            ),
            project_orientation=project_orientation,
        )


def _mapping(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ProfileAgentAdaptationError(f"{path} must be an object")
    return dict(cast(Mapping[str, object], value))


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileAgentAdaptationError(f"{path} must be a non-empty string")
    return value.strip()


def _string_list(value: object, path: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ProfileAgentAdaptationError(f"{path} must be a list of strings")
    return [item for item in value if item]


def _score(value: object, path: str) -> float:
    parsed = _optional_score(value, path)
    if parsed is None:
        raise ProfileAgentAdaptationError(f"{path} must be a number")
    return parsed


def _optional_score(value: object, path: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ProfileAgentAdaptationError(f"{path} must be a number or null")
    score = float(value)
    if not 0 <= score <= 1:
        raise ProfileAgentAdaptationError(f"{path} must be between 0 and 1")
    return score


def _nonnegative_int(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProfileAgentAdaptationError(f"{path} must be a non-negative integer")
    return value


def _optional_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path)


def _optional_positive_number(value: object, path: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise ProfileAgentAdaptationError(f"{path} must be a positive number or null")
    return float(value)


def _parse_datetime(value: object, path: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        raise ProfileAgentAdaptationError(f"{path} must be an ISO timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProfileAgentAdaptationError(f"{path} must be an ISO timestamp") from exc


def _assessment_runs(payload: Mapping[str, object], profile_id: str) -> list[str]:
    meta = payload.get("meta")
    if isinstance(meta, Mapping) and isinstance(meta.get("assessment_runs"), list):
        runs = _string_list(meta["assessment_runs"], "meta.assessment_runs")
        if runs:
            return runs
    return [f"{profile_id}:profile-agent-v2.1"]


def _validate_profile_consistency(
    payload: Mapping[str, object],
    profile_id: str,
    warnings: list[ProfileAgentAdaptationWarning],
) -> None:
    """Report contradictions in exported Agent profiles without hiding facts.

    The v2.1 contract intentionally keeps the normalized diagnosis at the top
    level and the original questionnaire under ``uploaded_data``.  These
    checks make common export mistakes visible while preserving compatibility
    with older profiles that do not carry the optional raw section.
    """
    scope = payload.get("learning_scope")
    hints = payload.get("resource_generation_hints")
    if isinstance(scope, Mapping) and isinstance(hints, Mapping):
        scope_depth = scope.get("target_depth")
        hint_depth = hints.get("target_depth")
        if scope_depth and hint_depth and scope_depth != hint_depth:
            warnings.append(
                ProfileAgentAdaptationWarning(
                    legacy_id=profile_id,
                    reason=(
                        "learning_scope.target_depth conflicts with "
                        "resource_generation_hints.target_depth; use learning_scope "
                        "as authoritative"
                    ),
                )
            )

        primary_kp = scope.get("primary_kp_id")
        labels = payload.get("depth_labels")
        if isinstance(primary_kp, str) and isinstance(labels, list) and scope_depth:
            primary_label = next(
                (
                    item.get("depth")
                    for item in labels
                    if isinstance(item, Mapping) and item.get("kp_id") == primary_kp
                ),
                None,
            )
            if primary_label and _depth_token(primary_label) != _depth_token(scope_depth):
                warnings.append(
                    ProfileAgentAdaptationWarning(
                        legacy_id=profile_id,
                        reason=(
                            f"depth_labels for {primary_kp}={primary_label} conflicts "
                            f"with learning_scope.target_depth={scope_depth}"
                        ),
                    )
                )

    raw = payload.get("uploaded_data")
    if not isinstance(raw, Mapping):
        raw = {}
    raw_records = raw.get("test_records")
    if isinstance(raw_records, list) and not isinstance(payload.get("test_records"), list):
        warnings.append(
            ProfileAgentAdaptationWarning(
                legacy_id=profile_id,
                reason=(
                    "raw assessment records are nested under uploaded_data; "
                    "normalized adapter facts are used"
                ),
            )
        )
    meta = payload.get("meta")
    expected = meta.get("total_test_count") if isinstance(meta, Mapping) else None
    if isinstance(raw_records, list) and isinstance(expected, int) and expected != len(raw_records):
        warnings.append(
            ProfileAgentAdaptationWarning(
                legacy_id=profile_id,
                reason=(
                    f"meta.total_test_count={expected} but uploaded_data.test_records "
                    f"contains {len(raw_records)} records"
                ),
            )
        )
    if isinstance(raw_records, list):
        keys = [
            item.get("question_id")
            for item in raw_records
            if isinstance(item, Mapping) and item.get("question_id")
        ]
        if len(keys) != len(set(keys)):
            warnings.append(
                ProfileAgentAdaptationWarning(
                    legacy_id=profile_id,
                    reason="uploaded_data.test_records contains repeated question IDs",
                )
            )

    learner = payload.get("learner")
    self_assessment = learner.get("self_assessment") if isinstance(learner, Mapping) else None
    profile_hours = (
        self_assessment.get("weekly_hours")
        if isinstance(self_assessment, Mapping)
        else None
    )
    preferences = payload.get("learning_preferences")
    pace = preferences.get("pace") if isinstance(preferences, Mapping) else None
    preference_hours = pace.get("weekly_hours") if isinstance(pace, Mapping) else None
    if (
        isinstance(profile_hours, int | float)
        and isinstance(preference_hours, int | float)
        and abs(float(profile_hours) - float(preference_hours)) > 1e-9
    ):
        warnings.append(
            ProfileAgentAdaptationWarning(
                legacy_id=profile_id,
                reason=(
                    f"learner.self_assessment.weekly_hours={profile_hours} conflicts "
                    f"with learning_preferences.pace.weekly_hours={preference_hours}"
                ),
            )
        )


def _depth_token(value: object) -> str:
    return {
        "入门": "entry",
        "回顾": "review",
        "进阶": "advanced",
        "跳过": "skip",
    }.get(str(value).strip().casefold(), str(value).strip().casefold())
