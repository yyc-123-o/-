from __future__ import annotations

import json
from pathlib import Path

from skillforge_kb.evidence.cross_check import build_cross_check_report
from skillforge_kb.evidence.external_corpus import load_external_corpus
from skillforge_kb.retrieval.corpus import KnowledgeCorpus


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_cross_check_report_separates_agreement_conflict_and_gaps(
    catalog,
    tmp_path: Path,
) -> None:
    primary_path = tmp_path / "primary.jsonl"
    external_path = tmp_path / "external.jsonl"

    _write_jsonl(
        primary_path,
        [
            {
                "chunk_id": "p-dup",
                "doc_id": "p-doc-1",
                "source_title": "CNN 卷积基础",
                "heading_path": ["CNN", "卷积运算"],
                "text": "卷积运算会在输入上滑动并生成输出特征图。",
                "page_no": 1,
                "domain_tag": "ai-knowledge",
                "difficulty": "进阶",
                "token_count": 12,
            },
            {
                "chunk_id": "p-agree",
                "doc_id": "p-doc-2",
                "source_title": "CNN 卷积基础",
                "heading_path": ["CNN", "卷积运算"],
                "text": "卷积运算可用局部窗口对输入特征进行加权汇总。",
                "page_no": 2,
                "domain_tag": "ai-knowledge",
                "difficulty": "进阶",
                "token_count": 14,
            },
            {
                "chunk_id": "p-conflict",
                "doc_id": "p-doc-3",
                "source_title": "CNN 卷积基础",
                "heading_path": ["CNN", "卷积输出"],
                "text": "卷积运算的输出尺寸由卷积核大小、stride 与 padding 决定。",
                "page_no": 3,
                "domain_tag": "ai-knowledge",
                "difficulty": "进阶",
                "token_count": 13,
            },
        ],
    )
    _write_jsonl(
        external_path,
        [
            {
                "chunk_id": "p-dup",
                "doc_id": "e-doc-1",
                "source_title": "CNN Intro",
                "heading_path": ["CNN", "卷积运算"],
                "text": "卷积运算会在输入上滑动并生成输出特征图。",
                "page_no": 1,
                "domain_tag": "ai-knowledge",
                "difficulty": "进阶",
                "token_count": 12,
                "content_kind": "definition",
            },
            {
                "chunk_id": "e-agree",
                "doc_id": "e-doc-2",
                "source_title": "CNN Intro",
                "heading_path": ["CNN", "卷积运算"],
                "text": "卷积运算可以看作局部窗口对输入特征进行聚合与汇总。",
                "page_no": 2,
                "domain_tag": "ai-knowledge",
                "difficulty": "进阶",
                "token_count": 14,
                "content_kind": "definition",
            },
            {
                "chunk_id": "e-conflict",
                "doc_id": "e-doc-3",
                "source_title": "CNN Practice",
                "heading_path": ["CNN", "卷积运算练习"],
                "text": "卷积运算练习：请计算输出尺寸，并说明 padding 对结果的影响。",
                "page_no": 3,
                "domain_tag": "ai-knowledge",
                "difficulty": "进阶",
                "token_count": 14,
                "content_kind": "exercise",
            },
            {
                "chunk_id": "e-only",
                "doc_id": "e-doc-4",
                "source_title": "图像张量",
                "heading_path": ["图像张量"],
                "text": "图像张量把像素组织为通道、高度和宽度三个维度。",
                "page_no": 4,
                "domain_tag": "ai-knowledge",
                "difficulty": "入门",
                "token_count": 14,
            },
        ],
    )

    primary = KnowledgeCorpus.load(primary_path)
    external = load_external_corpus(external_path)

    report = build_cross_check_report(primary, external, catalog)

    assert report["summary"]["duplicate_overlap_count"] == 1
    assert report["summary"]["agreement_count"] == 1
    assert report["summary"]["conflict_count"] == 1
    assert report["summary"]["external_only_count"] == 1
    assert report["summary"]["primary_only_count"] == 0
    assert report["gate_decision"]["allowed_for_published_resource"] is False
