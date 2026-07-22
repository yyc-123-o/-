import json
from pathlib import Path

from skillforge_kb.domain.enums import Language
from skillforge_kb.fusion.legacy import adapt_legacy, classify_corpus
from skillforge_kb.fusion.models import CorpusId, FusionDisposition, ReasonCode


def _row(chunk_id: str, title: str, text: str) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "doc_id": f"doc-{title}",
        "source_title": title,
        "heading_path": [title, "Section"],
        "text": text,
        "page_no": None,
        "domain_tag": "ai-knowledge",
        "difficulty": "进阶",
        "token_count": len(text),
    }


def test_legacy_adapter_routes_domains_and_marks_missing_provenance(tmp_path: Path) -> None:
    rows = [
        _row("paper-1", "RAG", "Retrieval augmented generation combines retrieval and generation."),
        _row(
            "agent-1",
            "langchain部署",
            "LangChain deployment requires explicit runtime configuration.",
        ),
        _row("project-1", "校园项目_实训手册", "项目手册记录课程实施步骤和内部验收方法。"),
    ]
    path = tmp_path / "index_chunks.jsonl"
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    outcomes = adapt_legacy(path)

    assert [outcome.corpus_id for outcome in outcomes] == [
        CorpusId.LEARNING_EVIDENCE,
        CorpusId.AGENT_ENGINEERING,
        CorpusId.PROJECT_MATERIAL,
    ]
    assert all(outcome.disposition is FusionDisposition.REFERENCE_ONLY for outcome in outcomes)
    assert all(ReasonCode.MISSING_PROVENANCE in outcome.reason_codes for outcome in outcomes)
    assert outcomes[0].candidate is not None
    assert outcomes[0].candidate.language is Language.EN
    assert outcomes[0].candidate.source.source_key == "source:paper_rag_2020"


def test_legacy_adapter_rejects_short_text_and_supersedes_exact_duplicate(
    tmp_path: Path,
) -> None:
    duplicate_text = "Embedding models map related text to nearby vectors in representation space."
    rows = [
        _row("short", "faiss_intro", "title"),
        _row("first", "faiss_intro", duplicate_text),
        _row("second", "faiss_intro", duplicate_text),
    ]
    path = tmp_path / "index_chunks.jsonl"
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    outcomes = adapt_legacy(path)

    assert outcomes[0].disposition is FusionDisposition.REJECTED
    assert ReasonCode.TEXT_TOO_SHORT in outcomes[0].reason_codes
    assert outcomes[1].disposition is FusionDisposition.REFERENCE_ONLY
    assert outcomes[2].disposition is FusionDisposition.SUPERSEDED
    assert ReasonCode.EXACT_DUPLICATE in outcomes[2].reason_codes


def test_corpus_classifier_keeps_knowledge_manual_in_learning_domain() -> None:
    assert classify_corpus("GAN生成对抗网络_知识点手册") is CorpusId.LEARNING_EVIDENCE
