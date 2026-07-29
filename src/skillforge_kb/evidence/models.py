import json
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from skillforge_kb.domain.enums import ContentKind, Language, LicenseStatus
from skillforge_kb.ontology.models import CONCEPT_ID_PATTERN, DepthLevel


class EvidenceReviewStatus(StrEnum):
    CANDIDATE = "candidate"
    REVIEWED = "reviewed"
    PUBLISHED = "published"
    REJECTED = "rejected"
    REVOKED = "revoked"


def build_evidence_id(
    *,
    graph_version: str,
    source_id: str,
    chunk_id: str,
    concept_id: str,
    depth: DepthLevel,
    locator: str,
    normalized_hash: str,
    language: Language,
    content_kind: ContentKind,
) -> str:
    payload = {
        "chunk_id": chunk_id,
        "concept_id": concept_id,
        "content_kind": content_kind.value,
        "depth": depth.value,
        "graph_version": graph_version,
        "language": language.value,
        "locator": locator,
        "normalized_hash": normalized_hash,
        "source_id": source_id,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"evidence_{sha256(canonical.encode('utf-8')).hexdigest()}"


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str = Field(pattern=r"^evidence_[0-9a-f]{64}$")
    graph_version: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    depth: DepthLevel
    source_url: HttpUrl
    locator: str = Field(min_length=1)
    normalized_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    language: Language
    content_kind: ContentKind
    difficulty: int = Field(ge=1, le=4)
    license_status: LicenseStatus
    review_status: EvidenceReviewStatus
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_publication_gate(self) -> "EvidenceRecord":
        reviewed = self.review_status in {
            EvidenceReviewStatus.REVIEWED,
            EvidenceReviewStatus.PUBLISHED,
        }
        if reviewed and (self.reviewed_by is None or self.reviewed_at is None):
            raise ValueError("reviewed evidence requires reviewer and timestamp")
        if (
            self.review_status is EvidenceReviewStatus.PUBLISHED
            and self.license_status is not LicenseStatus.ALLOWED
        ):
            raise ValueError("published evidence requires an allowed source license")
        expected = build_evidence_id(
            graph_version=self.graph_version,
            source_id=self.source_id,
            chunk_id=self.chunk_id,
            concept_id=self.concept_id,
            depth=self.depth,
            locator=self.locator,
            normalized_hash=self.normalized_hash,
            language=self.language,
            content_kind=self.content_kind,
        )
        if self.evidence_id != expected:
            raise ValueError("evidence ID does not match evidence identity")
        return self
