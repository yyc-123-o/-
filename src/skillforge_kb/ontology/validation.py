from collections import Counter, defaultdict

from .catalog import OntologyCatalog
from .models import (
    Chapter,
    Concept,
    GraphValidationReport,
    RelationKind,
    Section,
    TeachingAssignment,
)

KEY_PATH_IDS = [
    "math.linear-algebra.vector",
    "math.linear-algebra.matrix",
    "math.linear-algebra.matrix-multiplication",
    "dl.representation.embedding",
    "llm.attention.scaled-dot-product",
    "llm.attention.self-attention",
    "llm.transformer.encoder",
    "llm.pretraining.gpt",
    "rag.dense-retrieval",
    "rag.retrieval-augmented-generation",
    "rag.evaluation.ragas",
]


class GraphValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = sorted(errors)
        super().__init__("\n".join(self.errors))


def validate_catalog(catalog: OntologyCatalog) -> GraphValidationReport:
    errors: list[str] = []
    concepts = {concept.id: concept for concept in catalog.concepts()}
    sections = {section.id: section for section in catalog.course_document.sections}
    chapters = {chapter.id: chapter for chapter in catalog.chapters()}
    assignments = catalog.course_document.teaches

    _validate_contiguous_orders(
        [chapter.order for chapter in chapters.values()],
        "chapter",
        errors,
    )
    _validate_sections(sections, chapters, errors)
    _validate_teaching(assignments, concepts, sections, errors)

    canonical_order = _canonical_order(catalog, chapters, sections)
    hard_edges: dict[str, set[str]] = defaultdict(set)
    incoming: dict[str, set[str]] = defaultdict(set)
    seen_symmetric: set[tuple[RelationKind, frozenset[str]]] = set()

    for relation in catalog.relations():
        if relation.source not in concepts or relation.target not in concepts:
            errors.append(f"dangling relation: {relation.source} -> {relation.target}")
            continue
        if relation.kind in {
            RelationKind.CONTRASTS_WITH,
            RelationKind.CONFUSED_WITH,
        }:
            key = (relation.kind, frozenset({relation.source, relation.target}))
            if key in seen_symmetric:
                errors.append(
                    f"duplicate symmetric relation: {relation.source} -> {relation.target}"
                )
            seen_symmetric.add(key)
        if relation.kind is RelationKind.HARD_PREREQUISITE:
            if canonical_order[relation.source] >= canonical_order[relation.target]:
                errors.append(
                    f"hard prerequisite order violation: {relation.source} -> {relation.target}"
                )
            hard_edges[relation.source].add(relation.target)
            incoming[relation.target].add(relation.source)

    _assert_acyclic(hard_edges, errors)
    roots = sorted(concept_id for concept_id in concepts if not incoming[concept_id])
    _validate_reachability(concepts, hard_edges, roots, errors)
    _validate_key_path(concepts, hard_edges, errors)

    if errors:
        raise GraphValidationError(errors)

    relation_counts = Counter(relation.kind.value for relation in catalog.relations())
    return GraphValidationReport(
        version=catalog.course_document.version,
        chapter_count=len(chapters),
        section_count=len(sections),
        concept_count=len(concepts),
        teaching_assignment_count=len(assignments),
        relation_counts=dict(sorted(relation_counts.items())),
        root_ids=roots,
        key_path_ids=KEY_PATH_IDS,
    )


def _validate_contiguous_orders(orders: list[int], label: str, errors: list[str]) -> None:
    expected = list(range(1, len(orders) + 1))
    if sorted(orders) != expected:
        errors.append(f"{label} orders must be contiguous from 1")


def _validate_sections(
    sections: dict[str, Section],
    chapters: dict[str, Chapter],
    errors: list[str],
) -> None:
    orders_by_chapter: dict[str, list[int]] = defaultdict(list)
    for section in sections.values():
        if section.chapter_id not in chapters:
            errors.append(f"dangling section chapter: {section.id}")
            continue
        orders_by_chapter[section.chapter_id].append(section.order)
    for chapter_id, orders in orders_by_chapter.items():
        _validate_contiguous_orders(orders, f"section for {chapter_id}", errors)


def _validate_teaching(
    assignments: list[TeachingAssignment],
    concepts: dict[str, Concept],
    sections: dict[str, Section],
    errors: list[str],
) -> None:
    assignment_counts: Counter[str] = Counter()
    orders_by_section: dict[str, list[int]] = defaultdict(list)
    for assignment in assignments:
        if assignment.concept_id not in concepts:
            errors.append(f"dangling teaching concept: {assignment.concept_id}")
        if assignment.section_id not in sections:
            errors.append(f"dangling teaching section: {assignment.section_id}")
        assignment_counts[assignment.concept_id] += 1
        orders_by_section[assignment.section_id].append(assignment.order)
    for concept_id in concepts:
        if assignment_counts[concept_id] != 1:
            errors.append(f"concept must have one primary section: {concept_id}")
    for section_id, orders in orders_by_section.items():
        _validate_contiguous_orders(orders, f"teaching for {section_id}", errors)


def _canonical_order(
    catalog: OntologyCatalog,
    chapters: dict[str, Chapter],
    sections: dict[str, Section],
) -> dict[str, tuple[int, int, int]]:
    teaching_orders = {
        assignment.concept_id: assignment.order for assignment in catalog.course_document.teaches
    }
    result: dict[str, tuple[int, int, int]] = {}
    for concept in catalog.concepts():
        section = sections[catalog.section_for(concept.id).id]
        chapter = chapters[section.chapter_id]
        result[concept.id] = (chapter.order, section.order, teaching_orders[concept.id])
    return result


def _assert_acyclic(edges: dict[str, set[str]], errors: list[str]) -> None:
    gray: set[str] = set()
    black: set[str] = set()

    def visit(concept_id: str) -> None:
        if concept_id in black:
            return
        if concept_id in gray:
            errors.append(f"hard prerequisite cycle at {concept_id}")
            return
        gray.add(concept_id)
        for successor in sorted(edges[concept_id]):
            visit(successor)
        gray.remove(concept_id)
        black.add(concept_id)

    for concept_id in sorted(edges):
        visit(concept_id)


def _validate_reachability(
    concepts: dict[str, Concept],
    edges: dict[str, set[str]],
    roots: list[str],
    errors: list[str],
) -> None:
    reachable = set(roots)
    pending = list(roots)
    while pending:
        source = pending.pop()
        for target in edges[source]:
            if target not in reachable:
                reachable.add(target)
                pending.append(target)
    for concept_id in sorted(concepts):
        if concept_id not in reachable:
            errors.append(f"required concept is unreachable: {concept_id}")


def _validate_key_path(
    concepts: dict[str, Concept],
    edges: dict[str, set[str]],
    errors: list[str],
) -> None:
    for concept_id in KEY_PATH_IDS:
        if concept_id not in concepts:
            errors.append(f"key path concept missing: {concept_id}")
    if errors:
        return
    reverse: dict[str, set[str]] = defaultdict(set)
    for source, targets in edges.items():
        for target in targets:
            reverse[target].add(source)
    ancestors = {KEY_PATH_IDS[-1]}
    pending = [KEY_PATH_IDS[-1]]
    while pending:
        target = pending.pop()
        for source in reverse[target]:
            if source not in ancestors:
                ancestors.add(source)
                pending.append(source)
    for concept_id in KEY_PATH_IDS[:-1]:
        if concept_id not in ancestors:
            errors.append(f"key path is disconnected from RAGAS: {concept_id}")
