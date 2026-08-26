from datetime import UTC, datetime
from pathlib import Path

import pytest

from skillforge_kb.assessment import AssessmentLedger
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import LearnerProfileSnapshot


@pytest.fixture(scope="session")
def catalog() -> OntologyCatalog:
    root = Path(__file__).parents[3] / "resources" / "ontology"
    return OntologyCatalog.load(root / "ai_course_v1.yaml", root / "ai_relations_v1.yaml")


@pytest.fixture
def profile() -> LearnerProfileSnapshot:
    return LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="profile-assessment",
        learner_ref="0" * 64,
        graph_version="ai-course-v1",
        generated_at=datetime(2026, 7, 30, tzinfo=UTC),
    )


@pytest.fixture
def ledger(profile: LearnerProfileSnapshot) -> AssessmentLedger:
    return AssessmentLedger(profile=profile)
