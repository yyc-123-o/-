from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from skillforge_kb.domain.enums import ContentKind, Language, LicenseStatus
from skillforge_kb.ontology.models import CONCEPT_ID_PATTERN, DepthLevel


class EvidenceReviewStatus(StrEnum):
    CANDIDATE = "candidate"
    REVIEWED = "reviewed"
    PUBLISHED = "published"
    REJECTED = "rejected"
    REVOKED = "revoked"


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
        return self
