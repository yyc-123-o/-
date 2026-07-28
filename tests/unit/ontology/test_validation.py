import pytest

from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import Relation, RelationDocument, RelationKind
from skillforge_kb.ontology.validation import GraphValidationError, validate_catalog


def test_validation_rejects_hard_prerequisite_cycle(catalog: OntologyCatalog) -> None:
    cycle = Relation(
        source="rag.evaluation.ragas",
        target="math.linear-algebra.vector",
        kind=RelationKind.HARD_PREREQUISITE,
        min_mastery=0.6,
        review_status="reviewed",
    )
    cyclic_catalog = OntologyCatalog.from_documents(
        catalog.course_document,
        RelationDocument(
            version=catalog.relation_document.version,
            relations=[*catalog.relations(), cycle],
        ),
    )

    with pytest.raises(GraphValidationError, match="hard prerequisite cycle"):
        validate_catalog(cyclic_catalog)


def test_validation_accepts_course_and_reports_key_path(catalog: OntologyCatalog) -> None:
    report = validate_catalog(catalog)

    assert report.chapter_count == 11
    assert report.concept_count == 140
    assert report.key_path_ids == [
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


def test_validation_rejects_mismatched_document_versions(catalog: OntologyCatalog) -> None:
    mismatched_course = catalog.course_document.model_copy(
        update={"version": "ai-course-v2"}
    )
    mismatched_catalog = OntologyCatalog.from_documents(
        mismatched_course,
        catalog.relation_document,
    )

    with pytest.raises(GraphValidationError, match="relation document version mismatch"):
        validate_catalog(mismatched_catalog)

    nested_version_mismatch = catalog.course_document.model_copy(
        update={
            "course": catalog.course_document.course.model_copy(
                update={"version": "ai-course-v2"}
            )
        }
    )
    nested_mismatch_catalog = OntologyCatalog.from_documents(
        nested_version_mismatch,
        catalog.relation_document,
    )

    with pytest.raises(GraphValidationError, match="course version mismatch"):
        validate_catalog(nested_mismatch_catalog)


def test_validation_rejects_multiple_prerequisite_kinds_for_one_concept_pair(
    catalog: OntologyCatalog,
) -> None:
    duplicate = Relation(
        source="math.linear-algebra.scalar",
        target="math.linear-algebra.vector",
        kind=RelationKind.SOFT_PREREQUISITE,
        min_mastery=0.4,
        review_status="reviewed",
    )
    duplicate_catalog = OntologyCatalog.from_documents(
        catalog.course_document,
        RelationDocument(
            version=catalog.relation_document.version,
            relations=[*catalog.relations(), duplicate],
        ),
    )

    with pytest.raises(GraphValidationError, match="duplicate prerequisite relation"):
        validate_catalog(duplicate_catalog)
