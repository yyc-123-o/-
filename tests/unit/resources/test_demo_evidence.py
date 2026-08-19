from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

import pytest

from skillforge_kb.resources.demo_evidence import (
    EvidenceBundleManifest,
    FrozenEvidence,
    as_allowed_evidence,
    derive_exercise,
)


def _official() -> FrozenEvidence:
    text = "Conv2d applies a two dimensional convolution."
    return FrozenEvidence(
        evidence_id="E-1",
        evidence_type="definition",
        source_type="official_source",
        source_url="https://example.com/conv2d",
        resolved_url="https://example.com/conv2d",
        source_title="Conv2d",
        source_version="stable",
        retrieved_at=datetime.now(UTC),
        page_text_hash=sha256(b"page").hexdigest(),
        span_text=text,
        span_hash=sha256(text.encode()).hexdigest(),
        span_locator="description",
        license_status="unverified",
        review_status="candidate",
    )


def test_derived_exercise_records_parent_evidence() -> None:
    exercise = derive_exercise(
        evidence_id="E-2",
        prompt="Predict the output shape.",
        parent_evidence_ids=("E-1",),
    )
    bundle = EvidenceBundleManifest.create(records=(_official(), exercise))
    assert bundle.records[1].source_type == "system_derived"
    assert bundle.records[1].parent_evidence_ids == ("E-1",)
    assert as_allowed_evidence(bundle)[0].evidence_id == "E-1"


def test_reviewed_evidence_requires_named_reviewer() -> None:
    payload = _official().model_dump(mode="json")
    payload["review_status"] = "reviewed"
    with pytest.raises(ValueError, match="reviewed evidence"):
        FrozenEvidence(**payload)
