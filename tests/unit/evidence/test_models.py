from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from skillforge_kb.domain.enums import ContentKind, Language, LicenseStatus
from skillforge_kb.evidence.models import (
    EvidenceRecord,
    EvidenceReviewStatus,
    build_evidence_id,
)
from skillforge_kb.ontology.models import DepthLevel


def test_published_evidence_requires_reviewed_allowed_source() -> None:
    evidence_id = build_evidence_id(
        graph_version="ai-course-v1",
        source_id="source-1",
        chunk_id="chunk-1",
        concept_id="math.linear-algebra.scalar",
        depth=DepthLevel.INTRO,
        locator="section 1",
        normalized_hash="b" * 64,
        language=Language.EN,
        content_kind=ContentKind.DEFINITION,
    )
    with pytest.raises(ValidationError, match="published evidence requires"):
        EvidenceRecord(
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
            license_status=LicenseStatus.PENDING,
            review_status=EvidenceReviewStatus.PUBLISHED,
            reviewed_by="reviewer-1",
            reviewed_at=datetime(2026, 7, 29, tzinfo=UTC),
        )


def published_record() -> EvidenceRecord:
    evidence_id = build_evidence_id(
        graph_version="ai-course-v1",
        source_id="source-1",
        chunk_id="chunk-1",
        concept_id="math.linear-algebra.scalar",
        depth=DepthLevel.INTRO,
        locator="section 1",
        normalized_hash="b" * 64,
        language=Language.EN,
        content_kind=ContentKind.DEFINITION,
    )
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


def test_evidence_id_rejects_identity_field_mutation() -> None:
    record = published_record()
    invalid = record.model_copy(update={"locator": "changed"})

    with pytest.raises(ValidationError, match="evidence ID"):
        EvidenceRecord.model_validate(invalid.model_dump())


def test_review_state_change_preserves_evidence_identity() -> None:
    record = published_record()

    assert record.evidence_id == build_evidence_id(
        graph_version=record.graph_version,
        source_id=record.source_id,
        chunk_id=record.chunk_id,
        concept_id=record.concept_id,
        depth=record.depth,
        locator=record.locator,
        normalized_hash=record.normalized_hash,
        language=record.language,
        content_kind=record.content_kind,
    )
