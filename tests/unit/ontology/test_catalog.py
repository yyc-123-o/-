from pathlib import Path

from skillforge_kb.ontology.catalog import OntologyCatalog

RESOURCE_ROOT = Path(__file__).parents[3] / "resources" / "ontology"


def test_course_seed_has_expected_curriculum_shape() -> None:
    catalog = OntologyCatalog.load(
        RESOURCE_ROOT / "ai_course_v1.yaml",
        RESOURCE_ROOT / "ai_relations_v1.yaml",
    )

    assert [chapter.id for chapter in catalog.chapters()] == [
        "chapter.01.math-foundations",
        "chapter.02.classical-machine-learning",
        "chapter.03.neural-networks",
        "chapter.04.training-and-regularization",
        "chapter.05.cnn-representation",
        "chapter.06.embeddings-and-sequences",
        "chapter.07.transformer",
        "chapter.08.large-language-models",
        "chapter.09.alignment-and-peft",
        "chapter.10.rag",
        "chapter.11.rag-evaluation-and-practice",
    ]
    assert len(catalog.concepts()) == 140
    assert catalog.get_concept("rag.evaluation.ragas").names.zh == "RAGAS"
