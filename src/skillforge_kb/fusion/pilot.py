import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from skillforge_kb.domain.enums import Language
from skillforge_kb.ingestion.normalize import sha256_text

from .jsonl import JsonlRecord, iter_jsonl
from .models import (
    ChunkCandidate,
    CorpusId,
    FusionDisposition,
    FusionOutcome,
    InputDataset,
    ReasonCode,
    SourceCandidate,
)

LONG_ALPHA_RUN = re.compile(r"[A-Za-z]{40,}")


def _raw_hash(raw: str) -> str:
    return sha256(raw.encode("utf-8")).hexdigest()


def has_english_word_concatenation(text: str) -> bool:
    words = re.findall(r"[A-Za-z]+", text)
    long_words = [word for word in words if len(word) >= 25]
    alpha_characters = sum(map(len, words))
    long_characters = sum(map(len, long_words))
    return bool(long_words) and (
        LONG_ALPHA_RUN.search(text) is not None
        or long_characters / max(alpha_characters, 1) >= 0.12
    )


def _invalid(record: JsonlRecord) -> FusionOutcome:
    return FusionOutcome(
        input_dataset=InputDataset.PILOT,
        input_line=record.line_number,
        raw_line_sha256=_raw_hash(record.raw),
        disposition=FusionDisposition.REJECTED,
        reason_codes=[ReasonCode.INVALID_JSON],
        error=record.error,
    )


def _adapt_record(record: JsonlRecord, workspace_root: Path) -> FusionOutcome:
    if record.value is None:
        return _invalid(record)
    row: dict[str, Any] = record.value
    required = (
        "chunk_id",
        "source_id",
        "source_title",
        "source_path",
        "source_url",
        "language",
        "text",
        "content_hash",
        "locator",
    )
    missing = [field for field in required if not row.get(field)]
    if missing:
        return FusionOutcome(
            input_dataset=InputDataset.PILOT,
            input_line=record.line_number,
            raw_line_sha256=_raw_hash(record.raw),
            disposition=FusionDisposition.REJECTED,
            reason_codes=[ReasonCode.MISSING_REQUIRED_FIELD],
            error=f"missing required fields: {', '.join(missing)}",
        )

    text = str(row["text"])
    language = Language(str(row["language"]))
    source_path = str(row["source_path"])
    resolved_source = workspace_root / Path(source_path.replace("/", "\\"))
    reasons = [
        ReasonCode.LICENSE_REVIEW_REQUIRED,
        ReasonCode.HUMAN_REVIEW_REQUIRED,
        ReasonCode.AUTOMATED_LABEL_REVIEW_REQUIRED,
    ]
    disposition = FusionDisposition.ACCEPTED
    if not resolved_source.exists():
        reasons.append(ReasonCode.MISSING_SOURCE_PATH)
        disposition = FusionDisposition.REFERENCE_ONLY
    normalized_hash = sha256_text(text)
    if normalized_hash != str(row["content_hash"]):
        reasons.append(ReasonCode.NORMALIZED_HASH_MISMATCH)
    if language is Language.EN and has_english_word_concatenation(text):
        reasons.append(ReasonCode.ENGLISH_WORD_CONCATENATION)
        disposition = FusionDisposition.SUPERSEDED

    source = SourceCandidate(
        source_key=f"source:{row['source_id']}",
        source_id=str(row["source_id"]),
        title=str(row["source_title"]),
        corpus_id=CorpusId.LEARNING_EVIDENCE,
        canonical_url=str(row["source_url"]),
        source_path=source_path,
        license_label=str(row.get("license") or "") or None,
        provenance_complete=True,
        input_dataset=InputDataset.PILOT,
        input_line=record.line_number,
    )
    candidate = ChunkCandidate(
        chunk_id=str(row["chunk_id"]),
        source=source,
        language=language,
        text=text,
        locator=str(row["locator"]),
        citation_url=str(row["source_url"]),
        concept_ids=[str(value) for value in row.get("concept_ids", [])],
        content_kind=str(row.get("content_kind") or "") or None,
        difficulty=int(row["difficulty"]) if row.get("difficulty") is not None else None,
        normalized_hash=normalized_hash,
        original_hash=str(row["content_hash"]),
        metadata={"review_status": row.get("review_status"), "module": row.get("module")},
    )
    return FusionOutcome(
        input_dataset=InputDataset.PILOT,
        input_line=record.line_number,
        raw_line_sha256=_raw_hash(record.raw),
        disposition=disposition,
        corpus_id=CorpusId.LEARNING_EVIDENCE,
        reason_codes=reasons,
        candidate=candidate,
    )


def adapt_pilot(path: Path, workspace_root: Path) -> list[FusionOutcome]:
    outcomes: list[FusionOutcome] = []
    for record in iter_jsonl(path):
        try:
            outcome = _adapt_record(record, workspace_root)
        except (TypeError, ValueError) as exc:
            outcome = FusionOutcome(
                input_dataset=InputDataset.PILOT,
                input_line=record.line_number,
                raw_line_sha256=_raw_hash(record.raw),
                disposition=FusionDisposition.REJECTED,
                reason_codes=[ReasonCode.MISSING_REQUIRED_FIELD],
                error=str(exc),
            )
        outcomes.append(outcome)
    return outcomes
