from datetime import UTC, datetime

import pytest

from skillforge_kb.ontology.models import LearnerProfileSnapshot


@pytest.fixture
def profile() -> LearnerProfileSnapshot:
    return LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="PROFILE-2026-0001-DEMO",
        learner_ref="0" * 64,
        graph_version="ai-course-v1",
        generated_at=datetime(2026, 8, 16, tzinfo=UTC),
    )
