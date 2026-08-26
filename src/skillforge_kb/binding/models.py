from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ConceptResourceBinding(BaseModel):
    """An auditable, unpublished association between a chunk and a concept."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    binding_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunk_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)
    source_title: str = Field(min_length=1)
    heading_path: tuple[str, ...] = ()
    domain_tag: str = Field(min_length=1)
    concept_id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    chapter_id: str = Field(min_length=1)
    matched_term: str = Field(min_length=1)
    match_type: Literal[
        "title_exact_name",
        "title_alias",
        "title_partial_name",
        "body_exact_name",
        "body_alias",
    ]
    score: float = Field(gt=0, lt=1)
    review_status: Literal["candidate"] = "candidate"
    evidence_state: Literal["candidate"] = "candidate"
