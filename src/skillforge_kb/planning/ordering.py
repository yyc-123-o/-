from collections import defaultdict
from dataclasses import dataclass
from heapq import heappop, heappush

from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import RelationKind
from skillforge_kb.ontology.validation import GraphValidationError, validate_catalog


class PlanningError(ValueError):
    pass


@dataclass(frozen=True)
class CoursePosition:
    chapter_order: int
    section_order: int
    teaching_order: int
    chapter_id: str
    section_id: str


def course_positions(catalog: OntologyCatalog) -> dict[str, CoursePosition]:
    chapters = {item.id: item for item in catalog.course_document.chapters}
    sections = {item.id: item for item in catalog.course_document.sections}
    result: dict[str, CoursePosition] = {}
    for assignment in catalog.course_document.teaches:
        section = sections[assignment.section_id]
        chapter = chapters[section.chapter_id]
        result[assignment.concept_id] = CoursePosition(
            chapter_order=chapter.order,
            section_order=section.order,
            teaching_order=assignment.order,
            chapter_id=chapter.id,
            section_id=section.id,
        )
    return result


def stable_required_concept_ids(catalog: OntologyCatalog) -> list[str]:
    try:
        validate_catalog(catalog)
    except GraphValidationError as exc:
        raise PlanningError(f"invalid course graph: {exc}") from exc
    required = {item.id for item in catalog.concepts() if item.required}
    positions = course_positions(catalog)
    incoming = {concept_id: 0 for concept_id in required}
    outgoing: dict[str, set[str]] = defaultdict(set)

    for relation in catalog.relations(RelationKind.HARD_PREREQUISITE):
        if relation.source not in required or relation.target not in required:
            continue
        if relation.target not in outgoing[relation.source]:
            outgoing[relation.source].add(relation.target)
            incoming[relation.target] += 1

    pending: list[tuple[int, int, int, str]] = []
    for concept_id, count in incoming.items():
        if count == 0:
            heappush(pending, _sort_key(concept_id, positions))

    ordered: list[str] = []
    while pending:
        *_, concept_id = heappop(pending)
        ordered.append(concept_id)
        for successor in sorted(outgoing[concept_id]):
            incoming[successor] -= 1
            if incoming[successor] == 0:
                heappush(pending, _sort_key(successor, positions))

    if len(ordered) != len(required):
        raise PlanningError("required concept graph contains a cycle")
    return ordered


def _sort_key(
    concept_id: str,
    positions: dict[str, CoursePosition],
) -> tuple[int, int, int, str]:
    position = positions[concept_id]
    return (
        position.chapter_order,
        position.section_order,
        position.teaching_order,
        concept_id,
    )
