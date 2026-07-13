from datetime import UTC, datetime

import pytest

from skillforge_kb.domain.enums import Language, LicenseStatus, ReviewStatus, SourceTier
from skillforge_kb.domain.models import SourceRecord
from skillforge_kb.governance.policy import AdmissionDecision, SourcePolicy


def source(status: LicenseStatus) -> SourceRecord:
    return SourceRecord(
        source_id="source-1",
        title="Open course",
        canonical_url="https://example.edu/course",
        language=Language.EN,
        tier=SourceTier.S2,
        license_status=status,
        license_url="https://example.edu/license" if status is LicenseStatus.ALLOWED else None,
        retrieved_at=datetime.now(UTC),
    )


def test_allowed_source_can_enter_full_text_pipeline() -> None:
    assert SourcePolicy().evaluate(source(LicenseStatus.ALLOWED)) is AdmissionDecision.FULL_TEXT


def test_metadata_only_source_cannot_enter_full_text_pipeline() -> None:
    assert (
        SourcePolicy().evaluate(source(LicenseStatus.METADATA_ONLY))
        is AdmissionDecision.METADATA_ONLY
    )


def test_published_transition_requires_human_review() -> None:
    with pytest.raises(ValueError, match="human_reviewed"):
        SourcePolicy().assert_transition(ReviewStatus.AUTO_CHECKED, ReviewStatus.PUBLISHED)
