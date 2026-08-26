from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skillforge_kb.domain.enums import ContentKind, LicenseStatus
from skillforge_kb.evidence.models import EvidenceReviewStatus
from skillforge_kb.ontology.models import CONCEPT_ID_PATTERN, DepthLevel


class RetrievalMethod(StrEnum):
    PUBLISHED_INDEX = "published_index"
    BM25 = "bm25"
    ONTOLOGY_METADATA = "ontology_metadata"


class DomainRetrievalRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    original_query: str = Field(min_length=1)
    rewritten_queries: tuple[str, ...] = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    depth: DepthLevel
    top_k: int = Field(default=5, ge=1, le=20)


class RetrievedEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_key: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_title: str = Field(min_length=1)
    heading_path: tuple[str, ...] = ()
    excerpt: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    page_no: int | None = Field(default=None, gt=0)
    code_location: str | None = None
    score: float = Field(ge=0)
    retrieval_method: RetrievalMethod
    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    depth: DepthLevel
    content_kind: ContentKind
    review_status: EvidenceReviewStatus
    license_status: LicenseStatus
    evidence_status: Literal["formal", "candidate"]


class EvidenceSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    formal_count: int = Field(default=0, ge=0)
    candidate_count: int = Field(default=0, ge=0)
    available_content_kinds: tuple[ContentKind, ...] = ()
    missing_content_kinds: tuple[ContentKind, ...] = ()


class EvidenceGap(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    missing_content_kinds: tuple[ContentKind, ...] = Field(min_length=1)
    message: str = Field(min_length=1)


class DomainRetrievalResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request: DomainRetrievalRequest
    evidence: tuple[RetrievedEvidence, ...] = ()
    candidate_evidence: tuple[RetrievedEvidence, ...] = ()
    concept_evidence: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    evidence_summary: EvidenceSummary
    evidence_gap: EvidenceGap | None = None

    @model_validator(mode="after")
    def validate_scope_and_status(self) -> "DomainRetrievalResult":
        expected = self.request
        all_items = self.evidence + self.candidate_evidence
        if any(
            item.concept_id != expected.concept_id or item.depth is not expected.depth
            for item in all_items
        ):
            raise ValueError("retrieval evidence scope does not match request")
        if any(
            item.evidence_status != "formal"
            or item.review_status is not EvidenceReviewStatus.PUBLISHED
            or item.license_status is not LicenseStatus.ALLOWED
            for item in self.evidence
        ):
            raise ValueError("formal retrieval evidence must be published and allowed")
        if any(
            item.evidence_status != "candidate"
            for item in self.candidate_evidence
        ):
            raise ValueError("candidate retrieval evidence cannot be promoted")
        if self.evidence_summary.formal_count != len(self.evidence):
            raise ValueError("formal evidence count does not match evidence list")
        if self.evidence_summary.candidate_count != len(self.candidate_evidence):
            raise ValueError("candidate evidence count does not match candidate list")
        expected_gap = self.evidence_summary.missing_content_kinds
        if expected_gap and self.evidence_gap is None:
            raise ValueError("missing formal evidence requires an evidence gap")
        if not expected_gap and self.evidence_gap is not None:
            raise ValueError("complete formal evidence cannot contain an evidence gap")
        for concept_id, evidence_keys in self.concept_evidence.items():
            if concept_id != expected.concept_id:
                raise ValueError("concept evidence contains an unrelated concept")
            known_keys = {item.evidence_key for item in all_items}
            if not set(evidence_keys).issubset(known_keys):
                raise ValueError("concept evidence references an unknown evidence key")
        return self
