from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from skillforge_kb.domain.enums import ContentKind, Language, LicenseStatus
from skillforge_kb.evidence.models import EvidenceRecord, EvidenceReviewStatus


def test_published_evidence_requires_reviewed_allowed_source() -> None:
    with pytest.raises(ValidationError, match="published evidence requires"):
        EvidenceRecord(
            evidence_id="evidence_" + "a" * 64,
            graph_version="ai-course-v1",
            source_id="source-1",
            chunk_id="chunk-1",
            concept_id="math.linear-algebra.scalar",
            depth="intro",
            source_url="https://example.edu/source",
            locator="section 1",
            normalized_hash="b" * 64,
            language=Language.EN,
            content_kind=ContentKind.DEFINITION,
            difficulty=1,
            license_status=LicenseStatus.PENDING,
            review_status=EvidenceReviewStatus.PUBLISHED,
            reviewed_by="reviewer-1",
            reviewed_at=datetime(2026, 7, 29, tzinfo=UTC),
        )


def published_record(evidence_id: str = "evidence_" + "a" * 64) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        graph_version="ai-course-v1",
        source_id="source-1",
        chunk_id="chunk-1",
        concept_id="math.linear-algebra.scalar",
        depth="intro",
        source_url="https://example.edu/source",
        locator="section 1",
        normalized_hash="b" * 64,
        language=Language.EN,
        content_kind=ContentKind.DEFINITION,
        difficulty=1,
        license_status=LicenseStatus.ALLOWED,
        review_status=EvidenceReviewStatus.PUBLISHED,
        reviewed_by="reviewer-1",
        reviewed_at=datetime(2026, 7, 29, tzinfo=UTC),
    )


def test_published_evidence_contract_is_immutable() -> None:
    record = published_record()

    with pytest.raises(ValidationError, match="Instance is frozen"):
        record.locator = "changed"
