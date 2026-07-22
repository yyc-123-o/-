import json
from hashlib import sha256
from pathlib import Path

from skillforge_kb.fusion.models import FusionDisposition, ReasonCode
from skillforge_kb.fusion.pilot import adapt_pilot, has_english_word_concatenation
from skillforge_kb.ingestion.normalize import sha256_text


def _write_pilot(path: Path, source_path: str, text: str, content_hash: str) -> None:
    row = {
        "chunk_id": "paper_attention_chunk_1",
        "source_id": "paper_attention_2017",
        "source_title": "Attention Is All You Need",
        "source_path": source_path,
        "source_url": "https://arxiv.org/abs/1706.03762",
        "tier": "S1",
        "license_status": "allowed",
        "license": "arXiv",
        "language": "en",
        "module": "transformer",
        "content_kind": "definition",
        "concept_ids": ["llm.transformer.attention"],
        "difficulty": 3,
        "locator": "page 1",
        "text": text,
        "content_hash": content_hash,
        "review_status": "candidate",
    }
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")


def test_pilot_adapter_accepts_structural_candidate_and_preserves_citation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"source bytes")
    text = "Self-attention relates every sequence position to every other position."
    input_path = tmp_path / "pilot.jsonl"
    _write_pilot(input_path, "source.pdf", text, sha256_text(text))

    outcome = adapt_pilot(input_path, tmp_path)[0]

    assert outcome.disposition is FusionDisposition.ACCEPTED
    assert outcome.publishable is False
    assert outcome.candidate is not None
    assert outcome.candidate.citation_url == "https://arxiv.org/abs/1706.03762"
    assert outcome.candidate.locator == "page 1"
    assert ReasonCode.LICENSE_REVIEW_REQUIRED in outcome.reason_codes
    assert ReasonCode.HUMAN_REVIEW_REQUIRED in outcome.reason_codes


def test_pilot_adapter_supersedes_concatenated_english_and_flags_hash_change(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"source bytes")
    text = "Weproposeanewarchitecturebasedsolelyonattentionmechanismswithoutrecurrence."
    input_path = tmp_path / "pilot.jsonl"
    stored_text = text + "  "
    raw_hash = sha256(stored_text.encode("utf-8")).hexdigest()
    _write_pilot(input_path, "source.pdf", stored_text, raw_hash)

    outcome = adapt_pilot(input_path, tmp_path)[0]

    assert outcome.disposition is FusionDisposition.SUPERSEDED
    assert ReasonCode.ENGLISH_WORD_CONCATENATION in outcome.reason_codes
    assert ReasonCode.NORMALIZED_HASH_MISMATCH in outcome.reason_codes
    assert has_english_word_concatenation(text)


def test_pilot_adapter_rejects_invalid_json_without_dropping_line(tmp_path: Path) -> None:
    input_path = tmp_path / "pilot.jsonl"
    input_path.write_text("{not-json}\n", encoding="utf-8")

    outcome = adapt_pilot(input_path, tmp_path)[0]

    assert outcome.input_line == 1
    assert outcome.disposition is FusionDisposition.REJECTED
    assert outcome.reason_codes == [ReasonCode.INVALID_JSON]
    assert outcome.candidate is None
