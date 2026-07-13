from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from skillforge_kb.domain.enums import Language, LicenseStatus, SourceTier
from skillforge_kb.domain.models import Citation, EvidenceChunk, SourceRecord


def test_source_requires_provenance_and_license_status() -> None:
    source = SourceRecord(
        source_id="d2l-en",
        title="Dive into Deep Learning",
        canonical_url="https://d2l.ai/",
        language=Language.EN,
        tier=SourceTier.S2,
        license_status=LicenseStatus.ALLOWED,
        license_url="https://d2l.ai/chapter_appendix-tools-for-deep-learning/notation.html",
        retrieved_at=datetime.now(UTC),
    )
    assert source.source_id == "d2l-en"


def test_published_chunk_requires_resolvable_locator() -> None:
    with pytest.raises(ValidationError, match="locator"):
        EvidenceChunk(
            chunk_id="chunk-1",
            source_id="d2l-en",
            concept_ids=["ml.supervised.logistic-regression"],
            language=Language.EN,
            content_kind="definition",
            text="Logistic regression models a conditional probability.",
            citation=Citation(url="https://d2l.ai/", locator=""),
            content_hash="a" * 64,
            reviewed=True,
        )
