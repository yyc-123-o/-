import pytest
from neo4j import Driver

from skillforge_kb.ontology.neo4j import Neo4jConceptGraph


def _graph_counts(driver: Driver) -> tuple[int, int, int]:
    with driver.session() as session:
        node_count = session.run("MATCH (node) RETURN count(node) AS count").single()["count"]
        relation_count = session.run("MATCH ()-[edge]->() RETURN count(edge) AS count").single()[
            "count"
        ]
        constraint_count = session.run(
            "SHOW CONSTRAINTS YIELD name RETURN count(name) AS count"
        ).single()["count"]
    return int(node_count), int(relation_count), int(constraint_count)


@pytest.mark.integration
def test_publish_is_idempotent_and_reads_versioned_rag_prerequisites(driver, catalog) -> None:
    graph = Neo4jConceptGraph(driver)

    graph.publish(catalog)
    first_counts = _graph_counts(driver)
    graph.publish(catalog)

    assert first_counts == (599, 748, 5)
    assert _graph_counts(driver) == first_counts
    assert graph.prerequisites("rag.retrieval-augmented-generation", max_depth=1) == [
        "llm.pretraining.gpt",
        "rag.dense-retrieval",
    ]
    assert graph.prerequisites("rag.retrieval-augmented-generation", max_depth=2) == [
        "llm.language-modeling.autoregressive",
        "llm.pretraining.gpt",
        "rag.dense-retrieval",
        "rag.information-retrieval",
    ]
