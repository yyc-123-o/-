"""Candidate-only evidence governance for the course knowledge graph.

This module prepares an auditable human-review queue. It deliberately does not
turn a candidate chunk into an :class:`EvidenceRecord`: publication still
requires an explicit reviewer decision and a separately validated manifest.
"""

import re
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlparse

from skillforge_kb.ontology.catalog import OntologyCatalog

_REQUIRED_KINDS = ("definition", "code", "exercise")
_SUPPORTED_KINDS = {
    "definition",
    "derivation",
    "code",
    "example",
    "exercise",
    "misconception",
}
_SUPPORTED_LANGUAGES = {"zh", "en"}
_DEPTH_BY_DIFFICULTY = {1: "intro", 2: "intro", 3: "intermediate", 4: "advanced"}
_HASH_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def build_review_queue(
    rows: Iterable[Mapping[str, object]],
    catalog: OntologyCatalog,
    *,
    core_concept_ids: Iterable[str] | None = None,
) -> dict[str, object]:
    """Normalize candidate rows and report deterministic governance gaps.

    A row with multiple known concept IDs produces one candidate per concept so
    later publication can construct concept-specific evidence identities. A row
    containing any unknown concept ID is excluded as a whole; silently dropping
    only part of its binding would make its provenance ambiguous.
    """

    known_ids = {concept.id for concept in catalog.concepts()}
    core_ids = tuple(core_concept_ids or sorted(known_ids))
    core_set = set(core_ids)
    unknown_core = sorted(set(core_ids) - known_ids)
    if unknown_core:
        raise ValueError(f"core concept IDs are not in the catalog: {unknown_core}")

    candidates: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    seen_chunk_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            excluded.append({"chunk_id": "unknown", "reason": "row_not_object"})
            continue
        chunk_id = _text(row.get("chunk_id")) or "unknown"
        duplicate = chunk_id in seen_chunk_ids
        if not duplicate:
            seen_chunk_ids.add(chunk_id)
        reason = _exclusion_reason(row, known_ids, duplicate)
        if reason is not None:
            record: dict[str, object] = {"chunk_id": chunk_id, "reason": reason}
            concept_ids = row.get("concept_ids")
            if isinstance(concept_ids, list):
                record["concept_ids"] = [str(item) for item in concept_ids]
            excluded.append(record)
            continue
        bound_ids = _concept_ids(row)
        scoped_ids = tuple(concept_id for concept_id in bound_ids if concept_id in core_set)
        if not scoped_ids:
            excluded.append(
                {
                    "chunk_id": chunk_id,
                    "reason": "outside_core_scope",
                    "concept_ids": list(bound_ids),
                }
            )
            continue
        for concept_id in scoped_ids:
            candidates.append(_candidate(row, concept_id))

    candidates.sort(
        key=lambda item: (
            str(item["concept_id"]),
            str(item["content_kind"]),
            str(item["source_id"]),
            str(item["locator"]),
            str(item["chunk_id"]),
        )
    )
    excluded.sort(key=lambda item: (item["chunk_id"], item["reason"]))

    concept_summary: dict[str, dict[str, object]] = {}
    for concept_id in core_ids:
        scoped = [item for item in candidates if item["concept_id"] == concept_id]
        available = {
            str(item["content_kind"])
            for item in scoped
        }
        available_ordered = [kind for kind in _REQUIRED_KINDS if kind in available]
        available_ordered.extend(
            sorted(available - set(available_ordered))
        )
        missing = [kind for kind in _REQUIRED_KINDS if kind not in available]
        concept_summary[concept_id] = {
            "candidate_count": len(scoped),
            "available_content_kinds": available_ordered,
            "missing_content_kinds": missing,
            "ready_for_human_review": bool(scoped),
        }

    covered_ids = {
        concept_id
        for concept_id, summary in concept_summary.items()
        if summary["candidate_count"]
    }
    complete_count = sum(
        not summary["missing_content_kinds"]
        for summary in concept_summary.values()
    )
    core_count = len(core_ids)
    coverage = {
        "core_concept_count": core_count,
        "covered_concept_count": len(covered_ids),
        "coverage_rate": len(covered_ids) / core_count if core_count else 0.0,
        "complete_three_kind_count": complete_count,
        "complete_three_kind_rate": complete_count / core_count if core_count else 0.0,
    }
    return {
        "schema_version": "evidence-review-queue.v1",
        "graph_version": catalog.course_document.version,
        "core_concept_ids": list(core_ids),
        "candidate_count": len(candidates),
        "excluded_count": len(excluded),
        "publishable": False,
        "candidates": candidates,
        "excluded": excluded,
        "concepts": concept_summary,
        "coverage_summary": coverage,
    }


def _exclusion_reason(
    row: Mapping[str, object],
    known_ids: set[str],
    duplicate_chunk_id: bool,
) -> str | None:
    if duplicate_chunk_id:
        return "duplicate_chunk_id"
    concept_ids = row.get("concept_ids")
    if not isinstance(concept_ids, list) or not concept_ids or not all(
        isinstance(item, str) and item.strip() for item in concept_ids
    ):
        return "missing_concept_binding"
    if set(concept_ids) - known_ids:
        return "unknown_concept_id"
    if _text(row.get("license_status")) != "allowed":
        return "license_not_allowed"
    if _text(row.get("content_kind")) not in _SUPPORTED_KINDS:
        return "unsupported_content_kind"
    if _text(row.get("language")) not in _SUPPORTED_LANGUAGES:
        return "unsupported_language"
    required_fields = (
        "chunk_id",
        "source_id",
        "source_title",
        "source_url",
        "license_status",
        "license",
        "language",
        "content_kind",
        "locator",
        "text",
        "content_hash",
    )
    if any(not _text(row.get(field)) for field in required_fields):
        return "missing_required_metadata"
    parsed_url = urlparse(_text(row.get("source_url")))
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return "invalid_source_url"
    difficulty = row.get("difficulty")
    if not isinstance(difficulty, int) or isinstance(difficulty, bool) or difficulty not in {
        1,
        2,
        3,
        4,
    }:
        return "invalid_difficulty"
    if not _HASH_PATTERN.fullmatch(_text(row.get("content_hash"))):
        return "invalid_content_hash"
    return None


def _candidate(row: Mapping[str, object], concept_id: str) -> dict[str, object]:
    difficulty = int(row["difficulty"])
    explicit_depth = _text(row.get("depth"))
    proposed_depth = explicit_depth if explicit_depth in {
        "intro",
        "intermediate",
        "advanced",
    } else _DEPTH_BY_DIFFICULTY[difficulty]
    return {
        "chunk_id": _text(row.get("chunk_id")),
        "source_id": _text(row.get("source_id")),
        "source_title": _text(row.get("source_title")),
        "source_url": _text(row.get("source_url")),
        "license_status": _text(row.get("license_status")),
        "license": _text(row.get("license")),
        "tier": _text(row.get("tier")) or None,
        "language": _text(row.get("language")),
        "content_kind": _text(row.get("content_kind")),
        "concept_id": concept_id,
        "difficulty": difficulty,
        "depth": explicit_depth or None,
        "proposed_depth": proposed_depth,
        "depth_inference": "explicit" if explicit_depth else "difficulty_mapping",
        "locator": _text(row.get("locator")),
        "page": row.get("page") if isinstance(row.get("page"), int) else None,
        "normalized_hash": _text(row.get("content_hash")).lower(),
        "excerpt": _text(row.get("text")),
        "review_status": "candidate",
        "publishable": False,
    }


def _concept_ids(row: Mapping[str, object]) -> tuple[str, ...]:
    value = row.get("concept_ids")
    if not isinstance(value, list):
        return ()
    return tuple(dict.fromkeys(str(item).strip() for item in value))


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
