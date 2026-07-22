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

AUTHORITATIVE_ALIASES = {
    "LoRA_2021": "paper_lora_2021",
    "RAG": "paper_rag_2020",
}
LEARNING_TITLES = {"Graphrag", "LoRA_2021", "QLora", "RAG"}
PROJECT_MARKERS = ("实训手册", "渐进式", "项目", "exploration_summary")


def _raw_hash(raw: str) -> str:
    return sha256(raw.encode("utf-8")).hexdigest()


def classify_corpus(source_title: str) -> CorpusId:
    if source_title in LEARNING_TITLES or "知识点手册" in source_title:
        return CorpusId.LEARNING_EVIDENCE
    if source_title.startswith("ch") and source_title.endswith("_summary"):
        return CorpusId.PROJECT_MATERIAL
    if any(marker in source_title for marker in PROJECT_MARKERS):
        return CorpusId.PROJECT_MATERIAL
    return CorpusId.AGENT_ENGINEERING


def detect_language(text: str) -> Language:
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", text))
    alpha_count = len(re.findall(r"[A-Za-z]", text))
    return Language.ZH if cjk_count >= alpha_count else Language.EN


def _invalid(record: JsonlRecord) -> FusionOutcome:
    return FusionOutcome(
        input_dataset=InputDataset.LEGACY_INDEX,
        input_line=record.line_number,
        raw_line_sha256=_raw_hash(record.raw),
        disposition=FusionDisposition.REJECTED,
        reason_codes=[ReasonCode.INVALID_JSON],
        error=record.error,
    )


def _adapt_record(record: JsonlRecord, seen_hashes: set[str]) -> FusionOutcome:
    if record.value is None:
        return _invalid(record)
    row: dict[str, Any] = record.value
    required = ("chunk_id", "doc_id", "source_title", "text")
    missing = [field for field in required if not row.get(field)]
    if missing:
        return FusionOutcome(
            input_dataset=InputDataset.LEGACY_INDEX,
            input_line=record.line_number,
            raw_line_sha256=_raw_hash(record.raw),
            disposition=FusionDisposition.REJECTED,
            reason_codes=[ReasonCode.MISSING_REQUIRED_FIELD],
            error=f"missing required fields: {', '.join(missing)}",
        )

    text = str(row["text"])
    title = str(row["source_title"])
    corpus_id = classify_corpus(title)
    normalized_hash = sha256_text(text)
    reasons = [ReasonCode.MISSING_PROVENANCE, ReasonCode.HUMAN_REVIEW_REQUIRED]
    disposition = FusionDisposition.REFERENCE_ONLY
    if row.get("token_count") == len(text):
        reasons.append(ReasonCode.TOKEN_COUNT_IS_CHARACTER_COUNT)
    if len(text) < 20:
        reasons.append(ReasonCode.TEXT_TOO_SHORT)
        disposition = FusionDisposition.REJECTED
    elif normalized_hash in seen_hashes:
        reasons.append(ReasonCode.EXACT_DUPLICATE)
        disposition = FusionDisposition.SUPERSEDED
    elif len(text) > 2_000:
        reasons.append(ReasonCode.TEXT_REQUIRES_RECHUNKING)
    seen_hashes.add(normalized_hash)

    source_id = AUTHORITATIVE_ALIASES.get(title, f"legacy-{row['doc_id']}")
    if title in AUTHORITATIVE_ALIASES:
        reasons.append(ReasonCode.OVERLAPS_AUTHORITATIVE_SOURCE)
    source = SourceCandidate(
        source_key=f"source:{source_id}",
        source_id=source_id,
        title=title,
        corpus_id=corpus_id,
        provenance_complete=False,
        input_dataset=InputDataset.LEGACY_INDEX,
        input_line=record.line_number,
    )
    heading_path = [str(item) for item in row.get("heading_path", [])]
    page_no = row.get("page_no")
    locator = f"page {page_no}" if page_no is not None else " > ".join(heading_path) or None
    candidate = ChunkCandidate(
        chunk_id=str(row["chunk_id"]),
        source=source,
        language=detect_language(text),
        text=text,
        locator=locator,
        difficulty=None,
        normalized_hash=normalized_hash,
        metadata={
            "legacy_difficulty": row.get("difficulty"),
            "legacy_domain_tag": row.get("domain_tag"),
            "legacy_token_count": row.get("token_count"),
        },
    )
    return FusionOutcome(
        input_dataset=InputDataset.LEGACY_INDEX,
        input_line=record.line_number,
        raw_line_sha256=_raw_hash(record.raw),
        disposition=disposition,
        corpus_id=corpus_id,
        reason_codes=reasons,
        candidate=candidate,
    )


def adapt_legacy(path: Path) -> list[FusionOutcome]:
    seen_hashes: set[str] = set()
    outcomes: list[FusionOutcome] = []
    for record in iter_jsonl(path):
        try:
            outcome = _adapt_record(record, seen_hashes)
        except (TypeError, ValueError) as exc:
            outcome = FusionOutcome(
                input_dataset=InputDataset.LEGACY_INDEX,
                input_line=record.line_number,
                raw_line_sha256=_raw_hash(record.raw),
                disposition=FusionDisposition.REJECTED,
                reason_codes=[ReasonCode.MISSING_REQUIRED_FIELD],
                error=str(exc),
            )
        outcomes.append(outcome)
    return outcomes
