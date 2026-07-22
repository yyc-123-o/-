from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from skillforge_kb.domain.enums import Language


class InputDataset(StrEnum):
    PILOT = "pilot"
    LEGACY_INDEX = "legacy_index"


class CorpusId(StrEnum):
    LEARNING_EVIDENCE = "learning_evidence"
    AGENT_ENGINEERING = "agent_engineering"
    PROJECT_MATERIAL = "project_material"


class FusionDisposition(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    REFERENCE_ONLY = "reference_only"


class ReasonCode(StrEnum):
    INVALID_JSON = "invalid_json"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    MISSING_SOURCE_PATH = "missing_source_path"
    LICENSE_REVIEW_REQUIRED = "license_review_required"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    AUTOMATED_LABEL_REVIEW_REQUIRED = "automated_label_review_required"
    NORMALIZED_HASH_MISMATCH = "normalized_hash_mismatch"
    ENGLISH_WORD_CONCATENATION = "english_word_concatenation"
    MISSING_PROVENANCE = "missing_provenance"
    TOKEN_COUNT_IS_CHARACTER_COUNT = "token_count_is_character_count"
    TEXT_TOO_SHORT = "text_too_short"
    TEXT_REQUIRES_RECHUNKING = "text_requires_rechunking"
    EXACT_DUPLICATE = "exact_duplicate"
    OVERLAPS_AUTHORITATIVE_SOURCE = "overlaps_authoritative_source"


class FileInventoryEntry(BaseModel):
    root: str
    relative_path: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SourceCandidate(BaseModel):
    source_key: str
    source_id: str
    title: str
    corpus_id: CorpusId
    canonical_url: str | None = None
    source_path: str | None = None
    license_label: str | None = None
    provenance_complete: bool = False
    input_dataset: InputDataset
    input_line: int = Field(ge=1)


class ChunkCandidate(BaseModel):
    chunk_id: str
    source: SourceCandidate
    language: Language | None = None
    text: str
    locator: str | None = None
    citation_url: str | None = None
    concept_ids: list[str] = Field(default_factory=list)
    content_kind: str | None = None
    difficulty: int | None = None
    normalized_hash: str
    original_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FusionOutcome(BaseModel):
    input_dataset: InputDataset
    input_line: int = Field(ge=1)
    raw_line_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    disposition: FusionDisposition
    corpus_id: CorpusId | None = None
    publishable: bool = False
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    candidate: ChunkCandidate | None = None
    error: str | None = None


class DryRunSummary(BaseModel):
    input_rows: int = Field(ge=0)
    source_count: int = Field(ge=0)
    input_file_count: int = Field(ge=0)
    outcome_counts: dict[str, int]
    reason_counts: dict[str, int]
    corpus_counts: dict[str, int]
