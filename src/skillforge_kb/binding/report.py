import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.retrieval.corpus import KnowledgeCorpus

from .models import ConceptResourceBinding

BindingReport = dict[str, object]


def build_binding_report(
    catalog: OntologyCatalog,
    corpus: KnowledgeCorpus,
    bindings: Sequence[ConceptResourceBinding],
) -> BindingReport:
    concept_ids = [concept.id for concept in catalog.concepts()]
    concept_counts = Counter(binding.concept_id for binding in bindings)
    bound_chunks = {binding.chunk_id for binding in bindings}
    bound_concepts = set(concept_counts)
    match_counts = Counter(binding.match_type for binding in bindings)
    chapter_counts = Counter(binding.chapter_id for binding in bindings)

    return {
        "version": "concept-resource-binding-v1",
        "graph_version": catalog.course_document.version,
        "course_id": catalog.course_document.course.id,
        "corpus_digest": corpus.digest,
        "input_chunk_count": len(corpus.chunks),
        "concept_count": len(concept_ids),
        "candidate_binding_count": len(bindings),
        "bound_chunk_count": len(bound_chunks),
        "unbound_chunk_count": len(corpus.chunks) - len(bound_chunks),
        "bound_concept_count": len(bound_concepts),
        "unbound_concept_count": len(concept_ids) - len(bound_concepts),
        "concept_coverage_ratio": round(len(bound_concepts) / len(concept_ids), 6),
        "match_type_counts": dict(sorted(match_counts.items())),
        "chapter_binding_counts": dict(sorted(chapter_counts.items())),
        "concept_binding_counts": [
            {"concept_id": concept_id, "binding_count": concept_counts[concept_id]}
            for concept_id in concept_ids
            if concept_counts[concept_id]
        ],
        "unbound_concept_ids": [
            concept_id for concept_id in concept_ids if concept_id not in bound_concepts
        ],
        "review_status_counts": {"candidate": len(bindings)},
        "evidence_state_counts": {"candidate": len(bindings)},
        "publishable": False,
    }


def write_binding_outputs(
    output_dir: Path,
    bindings: Sequence[ConceptResourceBinding],
    report: BindingReport,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = sorted(bindings, key=lambda item: (item.chunk_id, item.concept_id))
    jsonl = "".join(
        json.dumps(
            binding.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
        for binding in rows
    )
    _atomic_write(output_dir / "concept_resource_candidates.jsonl", jsonl)
    _atomic_write(
        output_dir / "concept_resource_binding_report.json",
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _atomic_write(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)
