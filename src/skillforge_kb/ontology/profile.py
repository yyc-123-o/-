from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import cast

import yaml

from .catalog import OntologyCatalog
from .models import (
    AssessmentStatus,
    KnowledgeMastery,
    LearnerProfileSnapshot,
    ProfileIdMapping,
    ProfileMappingDocument,
)


class ProfileAdaptationError(ValueError):
    pass


class ProfileAdapter:
    def __init__(self, catalog: OntologyCatalog, mappings: list[ProfileIdMapping]) -> None:
        self._catalog = catalog
        self._mappings = {mapping.legacy_id: mapping for mapping in mappings}
        if len(self._mappings) != len(mappings):
            raise ProfileAdaptationError("duplicate legacy profile ID mapping")

    @classmethod
    def load_mappings(cls, catalog: OntologyCatalog, path: Path) -> "ProfileAdapter":
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        document = ProfileMappingDocument.model_validate(raw)
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

        return LearnerProfileSnapshot(
            schema_version="learner-profile.v1",
            profile_id=profile_id,
            learner_ref=sha256(learner_id.encode("utf-8")).hexdigest(),
            graph_version=graph_version,
            observed_at=_parse_datetime(meta.get("observed_at")),
            generated_at=_parse_datetime(meta.get("generated_at")),
            knowledge_mastery=mastery,
        )

    def _adapt_mastery(
        self,
        node: dict[str, object],
        index: int,
    ) -> KnowledgeMastery:
        path = f"dimension_1_knowledge_mastery.assessed_nodes[{index}]"
        for field in ("recommendation", "depth_prescription"):
            if field in node:
                raise ProfileAdaptationError(f"{path}.{field} belongs to planner output")
        legacy_id = _string(node.get("kg_node_id"), f"{path}.kg_node_id")
        mapping = self._mappings.get(legacy_id)
        if mapping is None:
            raise ProfileAdaptationError(f"unmapped or composite legacy ID: {legacy_id}")
        if mapping.graph_version != self._catalog.course_document.version:
            raise ProfileAdaptationError(f"mapping graph version mismatch: {legacy_id}")
        try:
            self._catalog.get_concept(mapping.concept_id)
        except KeyError as exc:
            raise ProfileAdaptationError(
                f"mapping targets unknown concept: {mapping.concept_id}"
            ) from exc

        status = _string(node.get("status"), f"{path}.status")
        score = _optional_score(node.get("mastery_score"), f"{path}.mastery_score")
        if status == "unexplored":
            if score is not None:
                raise ProfileAdaptationError(f"{path}.unexplored score must be null")
            assessment_status = AssessmentStatus.NOT_ASSESSED
        else:
            if score is None:
                raise ProfileAdaptationError(f"{path}.mastery_score is required")
            assessment_status = AssessmentStatus.ASSESSED

        confidence = _score(node.get("confidence"), f"{path}.confidence")
        evidence_refs = _string_list(node.get("evidence_refs"), f"{path}.evidence_refs")
        return KnowledgeMastery(
            concept_id=mapping.concept_id,
            mastery_score=score,
            assessment_status=assessment_status,
            confidence=confidence,
            observed_at=_parse_datetime(node.get("last_tested")),
            evidence_refs=evidence_refs,
        )

    @staticmethod
    def _assert_forbidden_top_level_fields(raw: Mapping[str, object]) -> None:
        for field in ("learning_path_context", "resource_generation_hints"):
            if field in raw:
                raise ProfileAdaptationError(f"{field} belongs to downstream planner output")
        ability = raw.get("dimension_2_ability_level")
        if isinstance(ability, dict) and "depth_prescription" in ability:
            raise ProfileAdaptationError(
                "dimension_2_ability_level.depth_prescription belongs to planner output"
            )


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


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProfileAdaptationError("timestamp must be an ISO-8601 string or null")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProfileAdaptationError("timestamp must be ISO-8601") from exc
