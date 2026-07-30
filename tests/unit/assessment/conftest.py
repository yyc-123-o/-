from datetime import UTC, datetime

import pytest

from skillforge_kb.ontology.models import LearnerProfileSnapshot


@pytest.fixture
def profile() -> LearnerProfileSnapshot:
    return LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="profile-assessment",
        learner_ref="0" * 64,
        graph_version="ai-course-v1",
        generated_at=datetime(2026, 7, 30, tzinfo=UTC),
    )
