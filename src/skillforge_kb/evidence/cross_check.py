from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from skillforge_kb.binding.matcher import build_candidate_bindings
from skillforge_kb.ingestion.normalize import (
    is_near_duplicate,
    jaccard_similarity,
    normalize_text,
    sha256_text,
)
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.retrieval.corpus import KnowledgeCorpus

from .external_corpus import ExternalCorpus, infer_external_content_kind

_REQUIRED_KINDS = ("definition", "code", "exercise")


@dataclass(frozen=True)
class CrossCheckRow:
    chunk_id: str
    peer_chunk_id: str | None
    concept_ids: tuple[str, ...]
    status: str
    content_kind: str
    peer_content_kind: str | None
    kind_source: str
    peer_kind_source: str | None
    similarity: float
    source_title: str
    peer_source_title: str | None


def build_cross_check_report(
    primary: KnowledgeCorpus,
    external: ExternalCorpus,
    catalog: OntologyCatalog,
    *,
    core_concept_ids: Sequence[str] | None = None,
) -> dict[str, object]:
    primary_bindings = build_candidate_bindings(catalog, primary)
    external_corpus = external.to_knowledge_corpus()
    external_bindings = build_candidate_bindings(catalog, external_corpus)

    primary_binding_map = _bindings_by_chunk(primary_bindings)
    external_binding_map = _bindings_by_chunk(external_bindings)

    core_ids = (
        tuple(core_concept_ids)
        if core_concept_ids is not None
        else tuple(concept.id for concept in catalog.concepts())
    )
    core_set = set(core_ids)

    primary_chunks = {chunk.chunk_id: chunk for chunk in primary.chunks}
    external_chunks = {chunk.chunk_id: chunk for chunk in external_corpus.chunks}
    primary_kinds = {
        chunk_id: _effective_content_kind(chunk.content_kind, chunk.source_title, chunk.heading_path, chunk.text)
        for chunk_id, chunk in primary_chunks.items()
    }
    external_kinds = {
        chunk_id: _effective_content_kind(chunk.content_kind, chunk.source_title, chunk.heading_path, chunk.text)
        for chunk_id, chunk in external_chunks.items()
    }
    primary_kind_source = {chunk_id: "inferred" for chunk_id in primary_chunks}
    external_kind_source = {
        chunk_id: (
            "declared"
            if external_record.declared_content_kind is not None
            else "inferred"
        )
        for chunk_id, external_record in ((record.chunk_id, record) for record in external.records)
    }
    primary_hashes = {
        chunk_id: sha256_text(chunk.text)
        for chunk_id, chunk in primary_chunks.items()
    }
    external_hashes = {
        chunk_id: record.content_hash
        for chunk_id, record in ((record.chunk_id, record) for record in external.records)
    }
    primary_chunks_by_hash: dict[str, list[str]] = defaultdict(list)
    external_chunks_by_hash: dict[str, list[str]] = defaultdict(list)
    for chunk_id, digest in primary_hashes.items():
        primary_chunks_by_hash[digest].append(chunk_id)
    for chunk_id, digest in external_hashes.items():
        external_chunks_by_hash[digest].append(chunk_id)

    rows: list[CrossCheckRow] = []
    matched_primary: set[str] = set()
    matched_external: set[str] = set()
    agreement_count = 0
    conflict_count = 0
    duplicate_overlap_count = 0
    external_only_count = 0
    needs_review_count = 0

    external_to_concepts = _concepts_by_chunk(external_binding_map)
    primary_to_concepts = _concepts_by_chunk(primary_binding_map)

    for external_chunk_id, external_chunk in external_chunks.items():
        external_concepts = _filter_core(
            external_to_concepts.get(external_chunk_id, set()),
            core_set,
        )
        if not external_concepts:
            rows.append(
                CrossCheckRow(
                    chunk_id=external_chunk_id,
                    peer_chunk_id=None,
                    concept_ids=(),
                    status="needs_review",
                    content_kind=external_kinds[external_chunk_id].value,
                    peer_content_kind=None,
                    kind_source=external_kind_source[external_chunk_id],
                    peer_kind_source=None,
                    similarity=0.0,
                    source_title=external_chunk.source_title,
                    peer_source_title=None,
                )
            )
            needs_review_count += 1
            continue

        duplicate_peer_id = _first_matching_hash_peer(
            external_hashes[external_chunk_id],
            primary_chunks_by_hash,
            core_set,
            primary_to_concepts,
            external_concepts,
        )
        if duplicate_peer_id is not None:
            matched_primary.add(duplicate_peer_id)
            matched_external.add(external_chunk_id)
            rows.append(
                CrossCheckRow(
                    chunk_id=external_chunk_id,
                    peer_chunk_id=duplicate_peer_id,
                    concept_ids=tuple(sorted(external_concepts)),
                    status="duplicate_overlap",
                    content_kind=external_kinds[external_chunk_id].value,
                    peer_content_kind=primary_kinds[duplicate_peer_id].value,
                    kind_source=external_kind_source[external_chunk_id],
                    peer_kind_source=primary_kind_source[duplicate_peer_id],
                    similarity=1.0,
                    source_title=external_chunk.source_title,
                    peer_source_title=primary_chunks[duplicate_peer_id].source_title,
                )
            )
            duplicate_overlap_count += 1
            continue

        primary_peer_id, similarity = _best_primary_peer(
            external_chunk_id,
            external_chunk.text,
            external_concepts,
            primary_chunks,
            primary_to_concepts,
        )
        if primary_peer_id is None:
            rows.append(
                CrossCheckRow(
                    chunk_id=external_chunk_id,
                    peer_chunk_id=None,
                    concept_ids=tuple(sorted(external_concepts)),
                    status="external_only",
                    content_kind=external_kinds[external_chunk_id].value,
                    peer_content_kind=None,
                    kind_source=external_kind_source[external_chunk_id],
                    peer_kind_source=None,
                    similarity=0.0,
                    source_title=external_chunk.source_title,
                    peer_source_title=None,
                )
            )
            external_only_count += 1
            continue

        matched_primary.add(primary_peer_id)
        matched_external.add(external_chunk_id)
        primary_kind = primary_kinds[primary_peer_id]
        external_kind = external_kinds[external_chunk_id]
        status = (
            "agreement"
            if primary_kind is external_kind
            else "conflict"
        )
        if status == "agreement":
            agreement_count += 1
        else:
            conflict_count += 1
        rows.append(
            CrossCheckRow(
                chunk_id=external_chunk_id,
                peer_chunk_id=primary_peer_id,
                concept_ids=tuple(sorted(external_concepts)),
                status=status,
                content_kind=external_kind.value,
                peer_content_kind=primary_kind.value,
                kind_source=external_kind_source[external_chunk_id],
                peer_kind_source=primary_kind_source[primary_peer_id],
                similarity=similarity,
                source_title=external_chunk.source_title,
                peer_source_title=primary_chunks[primary_peer_id].source_title,
            )
        )

    primary_only_count = 0
    for primary_chunk_id, primary_chunk in primary_chunks.items():
        primary_concepts = _filter_core(
            primary_to_concepts.get(primary_chunk_id, set()),
            core_set,
        )
        if not primary_concepts:
            continue
        if primary_chunk_id in matched_primary:
            continue
        rows.append(
            CrossCheckRow(
                chunk_id=primary_chunk_id,
                peer_chunk_id=None,
                concept_ids=tuple(sorted(primary_concepts)),
                status="primary_only",
                content_kind=primary_kinds[primary_chunk_id].value,
                peer_content_kind=None,
                kind_source=primary_kind_source[primary_chunk_id],
                peer_kind_source=None,
                similarity=0.0,
                source_title=primary_chunk.source_title,
                peer_source_title=None,
            )
        )
        primary_only_count += 1

    rows.sort(key=lambda item: (item.status, item.chunk_id, item.peer_chunk_id or ""))

    concept_summary = _build_concept_summary(
        catalog,
        core_ids,
        primary_binding_map,
        external_binding_map,
        primary_chunks,
        external_chunks,
        primary_kinds,
        external_kinds,
        matched_primary,
        matched_external,
        rows,
    )

    evidence_gap = {
        "missing_content_kinds": sorted(
            {
                kind
                for summary in concept_summary.values()
                for kind in summary["missing_content_kinds"]
            }
        ),
        "needs_review_count": needs_review_count,
    }

    return {
        "schema_version": "external-corpus-cross-check.v1",
        "request": {
            "primary_corpus_digest": primary.digest,
            "external_corpus_digest": external.digest,
            "core_concept_ids": list(core_ids),
        },
        "summary": {
            "agreement_count": agreement_count,
            "conflict_count": conflict_count,
            "duplicate_overlap_count": duplicate_overlap_count,
            "external_only_count": external_only_count,
            "primary_only_count": primary_only_count,
            "needs_review_count": needs_review_count,
            "primary_binding_count": len(primary_bindings),
            "external_binding_count": len(external_bindings),
        },
        "concept_evidence": concept_summary,
        "rows": [asdict(row) for row in rows],
        "evidence_gap": evidence_gap,
        "gate_decision": {
            "allowed_for_draft": True,
            "allowed_for_published_resource": False,
            "reason": "external corpus is verification-only and must not publish evidence",
        },
    }


def write_cross_check_report(report: Mapping[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output_path)


def _bindings_by_chunk(bindings: Sequence[Any]) -> dict[str, tuple[Any, ...]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for binding in bindings:
        grouped[binding.chunk_id].append(binding)
    return {key: tuple(value) for key, value in grouped.items()}


def _concepts_by_chunk(bindings_by_chunk: Mapping[str, tuple[Any, ...]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for chunk_id, bindings in bindings_by_chunk.items():
        result[chunk_id] = {binding.concept_id for binding in bindings}
    return result


def _filter_core(concepts: set[str], core_set: set[str]) -> set[str]:
    if not core_set:
        return set(concepts)
    return set(concept for concept in concepts if concept in core_set)


def _first_matching_hash_peer(
    digest: str,
    primary_chunks_by_hash: Mapping[str, list[str]],
    core_set: set[str],
    primary_to_concepts: Mapping[str, set[str]],
    external_concepts: set[str],
) -> str | None:
    candidates = primary_chunks_by_hash.get(digest, [])
    for candidate in sorted(candidates):
        primary_concepts = _filter_core(primary_to_concepts.get(candidate, set()), core_set)
        if primary_concepts & external_concepts:
            return candidate
    return None


def _best_primary_peer(
    external_chunk_id: str,
    external_text: str,
    external_concepts: set[str],
    primary_chunks: Mapping[str, Any],
    primary_to_concepts: Mapping[str, set[str]],
) -> tuple[str | None, float]:
    best_id: str | None = None
    best_score = 0.0
    for primary_chunk_id, primary_chunk in primary_chunks.items():
        primary_concepts = primary_to_concepts.get(primary_chunk_id, set())
        if not primary_concepts & external_concepts:
            continue
        score = _similarity(external_text, primary_chunk.text)
        if score > best_score or (score == best_score and (best_id is None or primary_chunk_id < best_id)):
            best_id = primary_chunk_id
            best_score = score
    return best_id, best_score


def _build_concept_summary(
    catalog: OntologyCatalog,
    core_ids: tuple[str, ...],
    primary_binding_map: Mapping[str, tuple[Any, ...]],
    external_binding_map: Mapping[str, tuple[Any, ...]],
    primary_chunks: Mapping[str, Any],
    external_chunks: Mapping[str, Any],
    primary_kinds: Mapping[str, Any],
    external_kinds: Mapping[str, Any],
    matched_primary: set[str],
    matched_external: set[str],
    rows: list[CrossCheckRow],
) -> dict[str, dict[str, object]]:
    primary_by_concept: dict[str, set[str]] = defaultdict(set)
    external_by_concept: dict[str, set[str]] = defaultdict(set)
    for chunk_id, bindings in primary_binding_map.items():
        for binding in bindings:
            if binding.concept_id in core_ids:
                primary_by_concept[binding.concept_id].add(chunk_id)
    for chunk_id, bindings in external_binding_map.items():
        for binding in bindings:
            if binding.concept_id in core_ids:
                external_by_concept[binding.concept_id].add(chunk_id)

    row_by_concept: dict[str, list[CrossCheckRow]] = defaultdict(list)
    for row in rows:
        for concept_id in row.concept_ids:
            row_by_concept[concept_id].append(row)

    required = set(_REQUIRED_KINDS)
    summary: dict[str, dict[str, object]] = {}
    for concept_id in core_ids:
        section = catalog.section_for(concept_id)
        chapter = next(
            chapter for chapter in catalog.chapters() if chapter.id == section.chapter_id
        )
        primary_chunk_ids = sorted(primary_by_concept.get(concept_id, set()))
        external_chunk_ids = sorted(external_by_concept.get(concept_id, set()))
        kinds = {
            primary_kinds[chunk_id].value for chunk_id in primary_chunk_ids
        } | {
            external_kinds[chunk_id].value for chunk_id in external_chunk_ids
        }
        ordered_kinds = [kind for kind in _REQUIRED_KINDS if kind in kinds]
        ordered_kinds.extend(sorted(kinds - set(ordered_kinds)))
        missing_kinds = [kind for kind in _REQUIRED_KINDS if kind not in kinds]
        concept_rows = row_by_concept.get(concept_id, [])
        summary[concept_id] = {
            "chapter_id": chapter.id,
            "section_id": section.id,
            "primary_chunk_ids": primary_chunk_ids,
            "external_chunk_ids": external_chunk_ids,
            "agreement_chunk_ids": sorted(
                row.chunk_id for row in concept_rows if row.status == "agreement"
            ),
            "conflict_chunk_ids": sorted(
                row.chunk_id for row in concept_rows if row.status == "conflict"
            ),
            "duplicate_overlap_chunk_ids": sorted(
                row.chunk_id for row in concept_rows if row.status == "duplicate_overlap"
            ),
            "primary_only_chunk_ids": sorted(
                row.chunk_id for row in rows if row.status == "primary_only" and concept_id in row.concept_ids
            ),
            "external_only_chunk_ids": sorted(
                row.chunk_id for row in rows if row.status == "external_only" and concept_id in row.concept_ids
            ),
            "available_content_kinds": ordered_kinds,
            "missing_content_kinds": missing_kinds,
            "ready_for_human_review": bool(primary_chunk_ids or external_chunk_ids),
        }
    return summary


def _effective_content_kind(kind: Any, source_title: str, heading_path: tuple[str, ...], text: str):
    if kind is not None:
        return kind
    inferred, _ = infer_external_content_kind(text, heading_path, None)
    return inferred


def _similarity(left: str, right: str) -> float:
    if normalize_text(left) == normalize_text(right):
        return 1.0
    if is_near_duplicate(left, right):
        return 0.95
    return jaccard_similarity(left, right)
