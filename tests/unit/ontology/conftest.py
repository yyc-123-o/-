from pathlib import Path

import pytest

from skillforge_kb.ontology.catalog import OntologyCatalog


@pytest.fixture(scope="session")
def catalog() -> OntologyCatalog:
    root = Path(__file__).parents[3] / "resources" / "ontology"
    return OntologyCatalog.load(root / "ai_course_v1.yaml", root / "ai_relations_v1.yaml")
