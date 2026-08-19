import json
from pathlib import Path

import pytest

from skillforge_kb.domain.enums import ContentKind
from skillforge_kb.retrieval.corpus import KnowledgeCorpus
from skillforge_kb.retrieval.models import KnowledgeDifficulty, KnowledgeQuery


def valid_row(chunk_id: str = "chunk-1") -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "doc_id": "doc-1",
        "source_title": "RAG",
        "heading_path": ["检索增强生成"],
        "text": "RAG combines retrieval and generation.",
        "page_no": None,
        "domain_tag": "ai-knowledge",
        "difficulty": "进阶",
        "token_count": 35,
    }


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_load_validates_rows_and_builds_stable_digest(tmp_path: Path) -> None:
    path = tmp_path / "chunks.jsonl"
    write_rows(path, [valid_row()])

    corpus = KnowledgeCorpus.load(path)

    assert corpus.chunks[0].difficulty is KnowledgeDifficulty.INTERMEDIATE
    assert corpus.chunks[0].heading_path == ("检索增强生成",)
    assert corpus.digest == KnowledgeCorpus.load(path).digest


def test_loader_preserves_declared_content_kind(tmp_path: Path) -> None:
    path = tmp_path / "chunks.jsonl"
    row = valid_row()
    row["content_kind"] = "code"
    write_rows(path, [row])

    corpus = KnowledgeCorpus.load(path)

    assert corpus.chunks[0].content_kind is ContentKind.CODE


def test_loader_rejects_duplicate_ids(tmp_path: Path) -> None:
    path = tmp_path / "chunks.jsonl"
    write_rows(path, [valid_row(), valid_row()])

    with pytest.raises(ValueError, match="duplicate chunk_id"):
        KnowledgeCorpus.load(path)


def test_loader_reports_malformed_line_number(tmp_path: Path) -> None:
    path = tmp_path / "chunks.jsonl"
    path.write_text(json.dumps(valid_row()) + "\n{bad json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"line 2"):
        KnowledgeCorpus.load(path)


def test_loader_reports_invalid_difficulty_line_number(tmp_path: Path) -> None:
    path = tmp_path / "chunks.jsonl"
    row = valid_row()
    row["difficulty"] = "未知"
    write_rows(path, [row])

    with pytest.raises(ValueError, match=r"line 1"):
        KnowledgeCorpus.load(path)


def test_query_rejects_invalid_bounds() -> None:
    with pytest.raises(ValueError):
        KnowledgeQuery(query="RAG", top_k=0)
    with pytest.raises(ValueError):
        KnowledgeQuery(query="RAG", top_k=21)
    with pytest.raises(ValueError):
        KnowledgeQuery(query="   ")
