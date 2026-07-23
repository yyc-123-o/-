from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl, model_validator

from .enums import ContentKind, Language, LicenseStatus, ReviewStatus, SourceTier


class SourceRecord(BaseModel):
    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]+$")
    title: str = Field(min_length=3)
    canonical_url: HttpUrl
    language: Language
    tier: SourceTier
    license_status: LicenseStatus
    license_url: HttpUrl | None = None
    retrieved_at: datetime
    version_label: str | None = None
    review_status: ReviewStatus = ReviewStatus.CANDIDATE

    @model_validator(mode="after")
    def validate_allowed_license(self) -> "SourceRecord":
        if self.license_status is LicenseStatus.ALLOWED and self.license_url is None:
            raise ValueError("allowed sources require license_url")
        return self


class Citation(BaseModel):
    url: HttpUrl
    locator: str = Field(min_length=1)
    title: str | None = None


class EvidenceChunk(BaseModel):
    chunk_id: str = Field(min_length=3)
    source_id: str
    concept_ids: list[str] = Field(min_length=1)
    language: Language
    content_kind: ContentKind
    text: str = Field(min_length=20)
    citation: Citation
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    difficulty: int = Field(default=2, ge=1, le=4)
    reviewed: bool = False
    derived: bool = False
    version_label: str | None = None


class EvidenceQuery(BaseModel):
    text: str = Field(min_length=2)
    language: Language | None = None
    concept_ids: list[str] = Field(default_factory=list)
    difficulty: int | None = Field(default=None, ge=1, le=4)
    top_k: int = Field(default=5, ge=1, le=20)


class EvidenceHit(BaseModel):
    chunk: EvidenceChunk
    sparse_score: float | None = None
    dense_score: float | None = None
    graph_score: float | None = None
    final_score: float = Field(ge=0)
    score_components: dict[str, float] = Field(default_factory=dict)
    risk_flags: list[str] = Field(default_factory=list)


class EvidencePackage(BaseModel):
    query: EvidenceQuery
    normalized_queries: list[str]
    matched_concept_ids: list[str]
    hits: list[EvidenceHit]
    coverage_gap: bool = False
    conflicts: list[str] = Field(default_factory=list)
