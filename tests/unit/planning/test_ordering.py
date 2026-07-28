from skillforge_kb.ontology.models import RelationKind
from skillforge_kb.planning.ordering import (
    course_positions,
    stable_required_concept_ids,
)


def test_required_course_order_covers_every_required_concept(catalog) -> None:
    ordered = stable_required_concept_ids(catalog)
    required = {item.id for item in catalog.concepts() if item.required}

    assert len(ordered) == len(required)
    assert set(ordered) == required


def test_every_required_hard_prerequisite_precedes_its_target(catalog) -> None:
    ordered = stable_required_concept_ids(catalog)
    index = {concept_id: position for position, concept_id in enumerate(ordered)}

    for edge in catalog.relations(RelationKind.HARD_PREREQUISITE):
        if edge.source in index and edge.target in index:
            assert index[edge.source] < index[edge.target]


def test_ordering_is_deterministic(catalog) -> None:
    assert stable_required_concept_ids(catalog) == stable_required_concept_ids(catalog)


def test_course_positions_follow_teaching_assignments(catalog) -> None:
    positions = course_positions(catalog)

    vector = positions["math.linear-algebra.vector"]
    assert vector.chapter_id == "chapter.01.math-foundations"
    assert vector.section_id == "section.01.linear-algebra"
    assert (vector.chapter_order, vector.section_order, vector.teaching_order) == (1, 1, 2)
