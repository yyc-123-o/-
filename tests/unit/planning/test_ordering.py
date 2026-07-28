import pytest

from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import Relation, RelationDocument, RelationKind
from skillforge_kb.planning.ordering import (
    PlanningError,
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


def test_invalid_catalog_is_reported_as_planning_error(catalog) -> None:
    cycle = Relation(
        source="rag.evaluation.ragas",
        target="math.linear-algebra.vector",
        kind=RelationKind.HARD_PREREQUISITE,
        min_mastery=0.6,
        review_status="reviewed",
    )
    invalid = OntologyCatalog.from_documents(
        catalog.course_document,
        RelationDocument(
            version=catalog.relation_document.version,
            relations=[*catalog.relations(), cycle],
        ),
    )

    with pytest.raises(PlanningError, match="invalid course graph"):
        stable_required_concept_ids(invalid)
