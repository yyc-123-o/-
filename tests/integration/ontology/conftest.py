from collections.abc import Iterator

import pytest
from neo4j import Driver

Neo4jContainer = pytest.importorskip(
    "testcontainers.neo4j",
    reason="Neo4j integration tests require testcontainers",
).Neo4jContainer


@pytest.fixture
def driver() -> Iterator[Driver]:
    with (
        Neo4jContainer("neo4j:5.26-community", password="password") as container,
        container.get_driver() as driver,
    ):
        yield driver
