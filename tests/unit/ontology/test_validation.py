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
