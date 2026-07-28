from typing import Any

from skillforge_kb.ontology.neo4j import Neo4jConceptGraph


class RecordingResult:
    def consume(self) -> None:
        return None


class RecordingTransaction:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **parameters: Any) -> RecordingResult:
        self.calls.append((query, parameters))
        return RecordingResult()


class RecordingSession:
    def __init__(self) -> None:
        self.transaction = RecordingTransaction()

    def __enter__(self) -> "RecordingSession":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def execute_write(self, callback: Any, **parameters: Any) -> None:
        callback(self.transaction, **parameters)


class RecordingDriver:
    def __init__(self) -> None:
        self.session_instance = RecordingSession()

    def session(self) -> RecordingSession:
        return self.session_instance


def test_publish_preserves_governance_fields_and_relation_review_status(catalog) -> None:
    driver = RecordingDriver()

    Neo4jConceptGraph(driver).publish(catalog)

    node_calls = [
        call
        for call in driver.session_instance.transaction.calls
        if "MERGE (node:" in call[0]
    ]
    chapter = next(parameters for query, parameters in node_calls if "Chapter" in query)
    assert chapter["properties"]["summary"]
    assert chapter["properties"]["learning_outcomes"]
    assert chapter["properties"]["review_status"] == "reviewed"

    relation_calls = [
        parameters
        for query, parameters in driver.session_instance.transaction.calls
        if "MERGE (source)-[edge:" in query
    ]
    assert relation_calls
    assert all(row["review_status"] == "reviewed" for row in relation_calls[0]["rows"])
    relation_queries = [
        query
        for query, _ in driver.session_instance.transaction.calls
        if "MERGE (source)-[edge:" in query
    ]
    assert all("}}" not in query for query in relation_queries)


def test_publish_materializes_symmetric_relations_in_both_directions(catalog) -> None:
    driver = RecordingDriver()

    Neo4jConceptGraph(driver).publish(catalog)

    contrast_calls = [
        parameters
        for query, parameters in driver.session_instance.transaction.calls
        if "CONTRASTS_WITH" in query
    ]
    assert len(contrast_calls) == 2
    forward = {(row["source"], row["target"]) for row in contrast_calls[0]["rows"]}
    reverse = {(row["source"], row["target"]) for row in contrast_calls[1]["rows"]}
    assert reverse == {(target, source) for source, target in forward}


def test_publish_attaches_review_status_to_structural_edges(catalog) -> None:
    driver = RecordingDriver()

    Neo4jConceptGraph(driver).publish(catalog)

    structural_queries = {
        "HAS_CHAPTER": "chapter",
        "HAS_SECTION": "section",
        "TEACHES": "teaches",
        "HAS_LEVEL": "level",
    }
    for edge_type, _ in structural_queries.items():
        query, parameters = next(
            (query, parameters)
            for query, parameters in driver.session_instance.transaction.calls
            if f"{edge_type}" in query
        )
        assert "review_status" in query or all(
            "review_status" in row for row in parameters["rows"]
        )
