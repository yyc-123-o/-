import pytest

from skillforge_kb.ontology.neo4j import Neo4jConceptGraph


@pytest.mark.integration
def test_publish_is_idempotent_and_reads_direct_rag_prerequisites(driver, catalog) -> None:
    graph = Neo4jConceptGraph(driver)

    graph.publish(catalog)
    graph.publish(catalog)

    assert graph.prerequisites("rag.retrieval-augmented-generation", max_depth=1) == [
        "llm.pretraining.gpt",
        "rag.dense-retrieval",
    ]
