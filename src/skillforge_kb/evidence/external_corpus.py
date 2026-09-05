from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skillforge_kb.domain.enums import ContentKind
from skillforge_kb.ingestion.normalize import normalize_text, sha256_text
from skillforge_kb.retrieval.corpus import KnowledgeCorpus, build_corpus_digest
from skillforge_kb.retrieval.models import KnowledgeChunk, KnowledgeDifficulty


_DIFFICULTY_MAP = {
    "intro": KnowledgeDifficulty.BEGINNER,
    "入门": KnowledgeDifficulty.BEGINNER,
    "beginner": KnowledgeDifficulty.BEGINNER,
    "intermediate": KnowledgeDifficulty.INTERMEDIATE,
    "进阶": KnowledgeDifficulty.INTERMEDIATE,
    "advanced": KnowledgeDifficulty.ADVANCED,
    "高阶": KnowledgeDifficulty.ADVANCED,
}

_CONTENT_KIND_HINTS = {
    "definition": ContentKind.DEFINITION,
    "code": ContentKind.CODE,
    "exercise": ContentKind.EXERCISE,
}


class ExternalCorpusRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_title: str = Field(min_length=1)
    heading_path: tuple[str, ...] = ()
    text: str = Field(min_length=1)
    page_no: int | None = Field(default=None, gt=0)
    domain_tag: str = Field(min_length=1)
    difficulty: KnowledgeDifficulty
    token_count: int = Field(ge=0)
    declared_content_kind: ContentKind | None = None
    content_kind: ContentKind
    content_kind_source: Literal["declared", "inferred"]
    review_status: Literal["candidate"] = "candidate"
    license_status: Literal["metadata_only"] = "metadata_only"
    evidence_status: Literal["external_candidate"] = "external_candidate"
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_heading_path(self) -> "ExternalCorpusRecord":
        if not self.heading_path:
            raise ValueError("heading_path must not be empty")
        return self

    def to_chunk(self) -> KnowledgeChunk:
        return KnowledgeChunk(
            chunk_id=self.chunk_id,
            doc_id=self.doc_id,
            source_title=self.source_title,
            heading_path=self.heading_path,
            text=self.text,
            page_no=self.page_no,
            domain_tag=self.domain_tag,
            difficulty=self.difficulty,
            token_count=self.token_count,
            content_kind=self.content_kind,
        )


class ExternalCorpus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    records: tuple[ExternalCorpusRecord, ...] = ()
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "ExternalCorpus":
        ids = [record.chunk_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate chunk_id in external corpus")
        return self

    @property
    def record_count(self) -> int:
        return len(self.records)

    @property
    def missing_content_kind_count(self) -> int:
        return sum(record.declared_content_kind is None for record in self.records)

    def to_knowledge_corpus(self) -> KnowledgeCorpus:
        chunks = tuple(record.to_chunk() for record in self.records)
        return KnowledgeCorpus(chunks=chunks, digest=build_corpus_digest(chunks))


def load_external_corpus(path: Path) -> ExternalCorpus:
    rows = _read_rows(path)
    records = tuple(_build_record(row, index=index) for index, row in enumerate(rows, start=1))
    digest = _build_digest(records)
    return ExternalCorpus(records=records, digest=digest)


def infer_external_content_kind(
    text: str,
    heading_path: tuple[str, ...],
    declared_kind: str | None,
) -> tuple[ContentKind, Literal["declared", "inferred"]]:
    normalized_declared = _normalize_content_kind(declared_kind)
    if normalized_declared is not None:
        return normalized_declared, "declared"

    searchable = " ".join((*heading_path, text)).casefold()
    if _looks_like_code(searchable):
        return ContentKind.CODE, "inferred"
    if _looks_like_exercise(searchable):
        return ContentKind.EXERCISE, "inferred"
    return ContentKind.DEFINITION, "inferred"


def _build_record(row: Mapping[str, Any], *, index: int) -> ExternalCorpusRecord:
    required_fields = (
        "chunk_id",
        "doc_id",
        "source_title",
        "heading_path",
        "text",
        "page_no",
        "domain_tag",
        "difficulty",
        "token_count",
    )
    missing = [field for field in required_fields if field not in row]
    if missing:
        raise ValueError(f"external corpus row {index} missing fields: {missing}")

    heading_path = _normalize_heading_path(row["heading_path"])
    content_kind, source = infer_external_content_kind(
        str(row["text"]),
        heading_path,
        _text_or_none(row.get("content_kind")),
    )
    declared_kind = _normalize_content_kind(_text_or_none(row.get("content_kind")))
    difficulty = _normalize_difficulty(row["difficulty"])
    text = normalize_text(str(row["text"]))
    return ExternalCorpusRecord(
        chunk_id=str(row["chunk_id"]),
        doc_id=str(row["doc_id"]),
        source_id=f"external:{row['doc_id']}",
        source_title=str(row["source_title"]),
        heading_path=heading_path,
        text=text,
        page_no=_positive_int_or_none(row.get("page_no")),
        domain_tag=str(row["domain_tag"]),
        difficulty=difficulty,
        token_count=_non_negative_int(row["token_count"]),
        declared_content_kind=declared_kind,
        content_kind=content_kind,
        content_kind_source=source,
        content_hash=sha256_text(text),
    )


def _build_digest(records: tuple[ExternalCorpusRecord, ...]) -> str:
    canonical = json.dumps(
        [record.model_dump(mode="json") for record in records],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _read_rows(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"external corpus file unavailable: {path}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON at {path} line {line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"external corpus row {line_number} must be an object")
        rows.append(row)
    return rows


def _normalize_heading_path(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("heading_path must be a non-empty list of strings")
    headings = tuple(str(item).strip() for item in value)
    if any(not item for item in headings):
        raise ValueError("heading_path entries must be non-empty strings")
    return headings


def _normalize_difficulty(value: object) -> KnowledgeDifficulty:
    if isinstance(value, KnowledgeDifficulty):
        return value
    if not isinstance(value, str):
        raise ValueError("difficulty must be a string")
    normalized = _DIFFICULTY_MAP.get(value.strip())
    if normalized is None:
        raise ValueError(f"unsupported difficulty: {value}")
    return normalized


def _normalize_content_kind(value: object) -> ContentKind | None:
    if value is None:
        return None
    if isinstance(value, ContentKind):
        return value
    if not isinstance(value, str):
        raise ValueError("content_kind must be a string when provided")
    normalized = _CONTENT_KIND_HINTS.get(value.strip())
    if normalized is None:
        raise ValueError(f"unsupported content_kind: {value}")
    return normalized


def _positive_int_or_none(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("page_no must be a positive integer when provided")
    return value


def _non_negative_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("token_count must be a non-negative integer")
    return value


def _looks_like_code(text: str) -> bool:
    markers = (
        "```",
        "python",
        "import ",
        "from ",
        "def ",
        "class ",
        "return ",
        "torch.",
        "nn.",
        "conv2d",
        "convtranspose",
        "pip install",
    )
    return any(marker in text for marker in markers)


def _looks_like_exercise(text: str) -> bool:
    markers = (
        "练习",
        "习题",
        "题目",
        "作业",
        "请计算",
        "请完成",
        "答案",
        "解析",
        "exercise",
        "question",
        "solution",
    )
    return any(marker in text for marker in markers)


def _text_or_none(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None
