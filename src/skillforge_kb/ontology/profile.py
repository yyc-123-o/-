from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import cast

import yaml

from .catalog import OntologyCatalog
from .models import (
    AbilityScore,
    AssessmentStatus,
    ErrorPattern,
    KnowledgeMastery,
    LearnerProfileSnapshot,
    LearningPreferences,
    ProfileIdMapping,
    ProfileMappingDocument,
)

MAPPING_DOCUMENT_VERSION = "profile-id-map-v1"
ASSESSED_LEGACY_STATUSES = frozenset(
    {"mastered", "familiar", "partial", "weak", "not_learned"}
)
ABILITY_DIMENSIONS = (
    "theoretical_understanding",
    "coding_ability",
    "mathematical_foundation",
    "problem_solving",
)
PRESENTATION_FLAGS = (
    ("visual_learner", "visual"),
    ("prefers_diagrams", "diagrams"),
    ("prefers_math_formulas", "math_formulas"),
    ("prefers_step_by_step", "step_by_step"),
    ("prefers_comparison_tables", "comparison_tables"),
)


class ProfileAdaptationError(ValueError):
    pass


class ProfileAdapter:
    def __init__(self, catalog: OntologyCatalog, mappings: list[ProfileIdMapping]) -> None:
        self._catalog = catalog
        self._mappings = {mapping.legacy_id: mapping for mapping in mappings}
        if len(self._mappings) != len(mappings):
            raise ProfileAdaptationError("duplicate legacy profile ID mapping")
        concept_ids = [mapping.concept_id for mapping in mappings]
        if len(set(concept_ids)) != len(concept_ids):
            raise ProfileAdaptationError("duplicate canonical concept mapping")
        for mapping in mappings:
            self._validate_mapping(mapping)

    @classmethod
    def load_mappings(cls, catalog: OntologyCatalog, path: Path) -> "ProfileAdapter":
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        document = ProfileMappingDocument.model_validate(raw)
        if document.version != MAPPING_DOCUMENT_VERSION:
            raise ProfileAdaptationError("mapping document version is not supported")
        if document.graph_version != catalog.course_document.version:
            raise ProfileAdaptationError("mapping graph version does not match catalog")
        return cls(catalog, document.mappings)

    def adapt(self, raw: dict[str, object]) -> LearnerProfileSnapshot:
        self._assert_forbidden_top_level_fields(raw)
        meta = _mapping(raw.get("profile_meta"), "profile_meta")
        basic_info = _mapping(raw.get("basic_info"), "basic_info")
        graph_version = _string(meta.get("graph_version"), "profile_meta.graph_version")
        if graph_version != self._catalog.course_document.version:
            raise ProfileAdaptationError("profile graph version does not match catalog")
        profile_id = _string(meta.get("profile_id"), "profile_meta.profile_id")
        learner_id = _string(basic_info.get("learner_id"), "basic_info.learner_id")

        mastery_dimension = _mapping(
            raw.get("dimension_1_knowledge_mastery"),
            "dimension_1_knowledge_mastery",
        )
        assessed_nodes = _list(
            mastery_dimension.get("assessed_nodes"),
            "dimension_1_knowledge_mastery.assessed_nodes",
        )
        mastery = [
            self._adapt_mastery(_mapping(node, f"assessed_nodes[{index}]"), index)
            for index, node in enumerate(assessed_nodes)
        ]
        _assert_unique(
            [observation.concept_id for observation in mastery],
            "duplicate mastery concept",
        )

        meta_assessment_runs = meta.get("assessment_runs")
        top_level_assessment_runs = raw.get("assessment_runs")
        assessment_runs_declared = (
            meta_assessment_runs is not None or top_level_assessment_runs is not None
        )
        if meta_assessment_runs is not None and top_level_assessment_runs is not None:
            assessment_runs = _unique_string_list(
                meta_assessment_runs, "profile_meta.assessment_runs"
            )
            top_level_runs = _unique_string_list(
                top_level_assessment_runs, "assessment_runs"
            )
            if assessment_runs != top_level_runs:
                raise ProfileAdaptationError("conflicting assessment_runs locations")
        elif top_level_assessment_runs is not None:
            assessment_runs = _unique_string_list(
                top_level_assessment_runs, "assessment_runs"
            )
        else:
            assessment_runs = _unique_string_list(
                meta_assessment_runs or [], "profile_meta.assessment_runs"
            )
        abilities = self._adapt_abilities(raw.get("dimension_2_ability_level"))
        ability_runs = [ability.assessment_run_id for ability in abilities.values()]
        if assessment_runs_declared:
            unknown_runs = sorted(set(ability_runs) - set(assessment_runs))
            if unknown_runs:
                raise ProfileAdaptationError(
                    "ability references undeclared assessment run: " + unknown_runs[0]
                )
        else:
            assessment_runs = list(dict.fromkeys(ability_runs))

        return LearnerProfileSnapshot(
            schema_version="learner-profile.v1",
            profile_id=profile_id,
            learner_ref=sha256(learner_id.encode("utf-8")).hexdigest(),
            graph_version=graph_version,
            observed_at=_parse_datetime(meta.get("observed_at")),
            generated_at=_parse_datetime(meta.get("generated_at")),
            assessment_runs=assessment_runs,
            knowledge_mastery=mastery,
            abilities=abilities,
            error_patterns=self._adapt_error_patterns(
                raw.get("dimension_3_error_patterns")
            ),
            preferences=self._adapt_preferences(
                raw.get("dimension_4_learning_preferences")
            ),
        )

    def _validate_mapping(self, mapping: ProfileIdMapping) -> None:
        if mapping.graph_version != self._catalog.course_document.version:
            raise ProfileAdaptationError(
                f"mapping graph version mismatch: {mapping.legacy_id}"
            )
        try:
            self._catalog.get_concept(mapping.concept_id)
        except KeyError as exc:
            raise ProfileAdaptationError(
                f"mapping targets unknown concept: {mapping.concept_id}"
            ) from exc

    def _adapt_mastery(
        self,
        node: dict[str, object],
        index: int,
    ) -> KnowledgeMastery:
        path = f"dimension_1_knowledge_mastery.assessed_nodes[{index}]"
        legacy_id = _string(node.get("kg_node_id"), f"{path}.kg_node_id")
        concept_id = self._map_legacy_id(legacy_id)

        status = _string(node.get("status"), f"{path}.status")
        if status not in {*ASSESSED_LEGACY_STATUSES, "unexplored"}:
            raise ProfileAdaptationError(f"{path}.unsupported status: {status}")
        score = _optional_score(node.get("mastery_score"), f"{path}.mastery_score")
        observed_at = _parse_datetime(node.get("last_tested"))
        if status == "unexplored":
            if score is not None:
                raise ProfileAdaptationError(f"{path}.unexplored score must be null")
            if observed_at is not None:
                raise ProfileAdaptationError(f"{path}.unexplored timestamp must be null")
            assessment_status = AssessmentStatus.NOT_ASSESSED
        else:
            if score is None:
                raise ProfileAdaptationError(f"{path}.mastery_score is required")
            if observed_at is None:
                raise ProfileAdaptationError(f"{path}.last_tested is required")
            assessment_status = AssessmentStatus.ASSESSED

        confidence = _score(node.get("confidence"), f"{path}.confidence")
        evidence_refs = _unique_string_list(
            node.get("evidence_refs"), f"{path}.evidence_refs"
        )
        return KnowledgeMastery(
            concept_id=concept_id,
            mastery_score=score,
            assessment_status=assessment_status,
            confidence=confidence,
            observed_at=observed_at,
            evidence_refs=evidence_refs,
        )

    def _map_legacy_id(self, legacy_id: str) -> str:
        mapping = self._mappings.get(legacy_id)
        if mapping is None:
            raise ProfileAdaptationError(f"unmapped or composite legacy ID: {legacy_id}")
        return mapping.concept_id

    def _adapt_abilities(self, value: object) -> dict[str, AbilityScore]:
        if value is None:
            return {}
        path = "dimension_2_ability_level"
        dimension = _mapping(value, path)
        sub_dimensions = _mapping(dimension.get("sub_dimensions"), f"{path}.sub_dimensions")
        expected = set(ABILITY_DIMENSIONS)
        actual = set(sub_dimensions)
        if actual != expected:
            missing = sorted(expected - actual)
            unknown = sorted(actual - expected)
            details = [f"missing={missing}"] if missing else []
            if unknown:
                details.append(f"unknown={unknown}")
            raise ProfileAdaptationError(
                f"{path}.sub_dimensions must contain exactly four abilities: "
                + ", ".join(details)
            )

        abilities: dict[str, AbilityScore] = {}
        for name in ABILITY_DIMENSIONS:
            ability_path = f"{path}.sub_dimensions.{name}"
            raw_ability = _mapping(sub_dimensions[name], ability_path)
            abilities[name] = AbilityScore(
                score=_score(raw_ability.get("score"), f"{ability_path}.score"),
                confidence=_score(
                    raw_ability.get("confidence"), f"{ability_path}.confidence"
                ),
                assessment_run_id=_string(
                    raw_ability.get("assessment_run_id"),
                    f"{ability_path}.assessment_run_id",
                ),
            )
        return abilities

    def _adapt_error_patterns(self, value: object) -> list[ErrorPattern]:
        if value is None:
            return []
        path = "dimension_3_error_patterns"
        dimension = _mapping(value, path)
        distribution = _mapping(
            dimension.get("error_distribution"), f"{path}.error_distribution"
        )
        codes = [_string(code, f"{path}.error_distribution code") for code in distribution]
        patterns: list[ErrorPattern] = []
        for code in sorted(codes):
            pattern_path = f"{path}.error_distribution.{code}"
            raw_pattern = _mapping(distribution[code], pattern_path)
            legacy_ids = _unique_string_list(
                raw_pattern.get("kg_nodes_involved", []),
                f"{pattern_path}.kg_nodes_involved",
            )
            concept_ids = [self._map_legacy_id(item) for item in legacy_ids]
            _assert_unique(concept_ids, f"{pattern_path} has duplicate canonical concept")
            patterns.append(
                ErrorPattern(
                    code=code,
                    count=_nonnegative_int(
                        raw_pattern.get("count"), f"{pattern_path}.count"
                    ),
                    ratio=_score(raw_pattern.get("ratio"), f"{pattern_path}.ratio"),
                    concept_ids=concept_ids,
                    evidence_refs=_unique_string_list(
                        raw_pattern.get("evidence_refs", []),
                        f"{pattern_path}.evidence_refs",
                    ),
                )
            )
        return patterns

    @staticmethod
    def _adapt_preferences(value: object) -> LearningPreferences:
        if value is None:
            return LearningPreferences()
        path = "dimension_4_learning_preferences"
        dimension = _mapping(value, path)
        format_preferences = _mapping(
            dimension.get("format_preferences", {}), f"{path}.format_preferences"
        )
        style_preferences = _mapping(
            dimension.get("style_preferences", {}), f"{path}.style_preferences"
        )
        pace_preferences = _mapping(
            dimension.get("pace_preferences", {}), f"{path}.pace_preferences"
        )
        motivation_profile = _mapping(
            dimension.get("motivation_profile", {}), f"{path}.motivation_profile"
        )

        presentation: list[str] = []
        if _boolean(
            format_preferences.get("jupyter_notebook", False),
            f"{path}.format_preferences.jupyter_notebook",
        ):
            presentation.append("jupyter_notebook")
        for source_field, canonical_value in PRESENTATION_FLAGS:
            if _boolean(
                style_preferences.get(source_field, False),
                f"{path}.style_preferences.{source_field}",
            ):
                presentation.append(canonical_value)

        project_driven = _boolean(
            motivation_profile.get("prefers_project_driven", False),
            f"{path}.motivation_profile.prefers_project_driven",
        )
        return LearningPreferences(
            content_order=_unique_string_list(
                format_preferences.get("preferred_content_order", []),
                f"{path}.format_preferences.preferred_content_order",
            ),
            code_language=_optional_string(
                format_preferences.get("code_language"),
                f"{path}.format_preferences.code_language",
            ),
            framework=_optional_string(
                format_preferences.get("framework"),
                f"{path}.format_preferences.framework",
            ),
            presentation=presentation,
            pace_hours_per_week=_optional_positive_number(
                pace_preferences.get("estimated_hours_per_week"),
                f"{path}.pace_preferences.estimated_hours_per_week",
            ),
            project_orientation="project_driven" if project_driven else None,
        )

    @staticmethod
    def _assert_forbidden_top_level_fields(raw: Mapping[str, object]) -> None:
        for field in (
            "learning_path_context",
            "resource_generation_hints",
            "prior_chapter_performance",
        ):
            if field in raw:
                raise ProfileAdaptationError(f"{field} belongs to downstream planner output")
        _assert_no_derived_fields(raw)


def _mapping(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ProfileAdaptationError(f"{path} must be an object")
    return cast(dict[str, object], value)


def _list(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise ProfileAdaptationError(f"{path} must be a list")
    return cast(list[object], value)


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProfileAdaptationError(f"{path} must be a non-empty string")
    return value


def _score(value: object, path: str) -> float:
    score = _optional_score(value, path)
    if score is None:
        raise ProfileAdaptationError(f"{path} must be a number")
    return score


def _optional_score(value: object, path: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ProfileAdaptationError(f"{path} must be a number or null")
    score = float(value)
    if not 0 <= score <= 1:
        raise ProfileAdaptationError(f"{path} must be between 0 and 1")
    return score


def _string_list(value: object, path: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ProfileAdaptationError(f"{path} must be a list of non-empty strings")
    return list(cast(list[str], value))


def _unique_string_list(value: object, path: str) -> list[str]:
    items = _string_list(value, path)
    _assert_unique(items, f"{path} contains duplicates")
    return items


def _assert_unique(values: list[str], message: str) -> None:
    if len(set(values)) != len(values):
        raise ProfileAdaptationError(message)


def _optional_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path)


def _boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise ProfileAdaptationError(f"{path} must be a boolean")
    return value


def _nonnegative_int(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProfileAdaptationError(f"{path} must be a non-negative integer")
    return value


def _optional_positive_number(value: object, path: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise ProfileAdaptationError(f"{path} must be a positive number or null")
    return float(value)


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProfileAdaptationError("timestamp must be an ISO-8601 string or null")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProfileAdaptationError("timestamp must be ISO-8601") from exc


def _assert_no_derived_fields(value: object, path: str = "") -> None:
    derived_fields = {
        "recommendation",
        "depth_prescription",
        "predecessor_nodes",
        "successor_nodes",
        "next_nodes",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if key in derived_fields:
                raise ProfileAdaptationError(f"{child_path} belongs to planner output")
            _assert_no_derived_fields(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_derived_fields(child, f"{path}[{index}]")
