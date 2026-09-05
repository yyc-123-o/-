from __future__ import annotations

import json
from pathlib import Path

from skillforge_kb.evidence.external_corpus import load_external_corpus


def test_load_external_corpus_marks_missing_content_kind_and_keeps_counts(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "external.jsonl"
    sample.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "chunk_id": "ext-1",
                        "doc_id": "doc-1",
                        "source_title": "CNN Intro",
                        "heading_path": ["CNN", "卷积"],
                        "text": "卷积核在输入上滑动并生成输出特征图。",
                        "page_no": 1,
                        "domain_tag": "ai-knowledge",
                        "difficulty": "进阶",
                        "token_count": 12,
                        "content_kind": "definition",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "chunk_id": "ext-2",
                        "doc_id": "doc-2",
                        "source_title": "CNN Code",
                        "heading_path": ["CNN", "Conv2d"],
                        "text": "torch.nn.Conv2d(3, 8, kernel_size=3, stride=1, padding=1)",
                        "page_no": 2,
                        "domain_tag": "ai-knowledge",
                        "difficulty": "进阶",
                        "token_count": 10,
                    },
                    ensure_ascii=False,
                ),
            ]
        ),
        encoding="utf-8",
    )

    corpus = load_external_corpus(sample)

    assert corpus.record_count == 2
    assert corpus.missing_content_kind_count == 1
    assert corpus.records[0].content_kind_source == "declared"
    assert corpus.records[1].content_kind_source == "inferred"
    assert corpus.to_knowledge_corpus().digest
