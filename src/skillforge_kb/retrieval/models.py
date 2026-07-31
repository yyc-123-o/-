from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class KnowledgeDifficulty(StrEnum):
    BEGINNER = "入门"
    INTERMEDIATE = "进阶"
    ADVANCED = "高阶"


class KnowledgeRetrievalStatus(StrEnum):
    OK = "ok"
    NO_RESULTS = "no_results"
    UNAVAILABLE = "unavailable"


class KnowledgeChunk(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)
    source_title: str = Field(min_length=1)
    heading_path: tuple[str, ...] = ()
    text: str = Field(min_length=1)
    page_no: int | None = Field(default=None, gt=0)
    domain_tag: str = Field(min_length=1)
    difficulty: KnowledgeDifficulty
    token_count: int = Field(ge=0)

    @field_validator("heading_path", mode="before")
    @classmethod
    def normalize_heading_path(cls, value: object) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("heading_path must be a list of strings")
        headings = tuple(value)
        if any(not isinstance(item, str) or not item.strip() for item in headings):
            raise ValueError("heading_path entries must be non-empty strings")
        return headings


class KnowledgeQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    concept_id: str | None = Field(default=None, min_length=1)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


class KnowledgeHit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)
    source_title: str = Field(min_length=1)
    heading_path: tuple[str, ...] = ()
    text: str = Field(min_length=1)
    difficulty: KnowledgeDifficulty
    score: float = Field(ge=0)
    evidence_state: Literal["candidate"] = "candidate"


class KnowledgeRetrievalResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: KnowledgeRetrievalStatus
    query: KnowledgeQuery
    concept_id: str | None = None
    corpus_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    hits: tuple[KnowledgeHit, ...] = ()
    error_code: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> "KnowledgeRetrievalResult":
        if self.status is KnowledgeRetrievalStatus.OK:
            if not self.hits:
                raise ValueError("ok retrieval result requires hits")
            if self.error_code is not None or self.error_message is not None:
                raise ValueError("ok retrieval result cannot contain an error")
        elif self.status is KnowledgeRetrievalStatus.NO_RESULTS:
            if self.hits:
                raise ValueError("no-results retrieval result cannot contain hits")
            if self.error_code is not None or self.error_message is not None:
                raise ValueError("no-results retrieval result cannot contain an error")
        else:
            if self.hits:
                raise ValueError("unavailable retrieval result cannot contain hits")
            if not self.error_code or not self.error_message:
                raise ValueError("unavailable retrieval result requires error details")
        return self

    @classmethod
    def no_results(
        cls,
        query: KnowledgeQuery,
        *,
        corpus_digest: str,
    ) -> "KnowledgeRetrievalResult":
        return cls(
            status=KnowledgeRetrievalStatus.NO_RESULTS,
            query=query,
            concept_id=query.concept_id,
            corpus_digest=corpus_digest,
        )

    @classmethod
    def unavailable(
        cls,
        query: KnowledgeQuery,
        *,
        error_code: str,
        error_message: str,
        corpus_digest: str | None = None,
    ) -> "KnowledgeRetrievalResult":
        return cls(
            status=KnowledgeRetrievalStatus.UNAVAILABLE,
            query=query,
            concept_id=query.concept_id,
            corpus_digest=corpus_digest or ("0" * 64),
            error_code=error_code,
            error_message=error_message,
        )
