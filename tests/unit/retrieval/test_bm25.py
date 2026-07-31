import json
from pathlib import Path

from skillforge_kb.retrieval.bm25 import Bm25KnowledgeRetriever
from skillforge_kb.retrieval.corpus import KnowledgeCorpus
from skillforge_kb.retrieval.models import KnowledgeQuery, KnowledgeRetrievalStatus


def corpus(tmp_path: Path) -> KnowledgeCorpus:
    path = tmp_path / "chunks.jsonl"
    rows = [
        {
            "chunk_id": "rag",
            "doc_id": "d1",
            "source_title": "RAG",
            "heading_path": [],
            "text": "检索增强生成 RAG 使用外部知识。",
            "page_no": None,
            "domain_tag": "ai-knowledge",
            "difficulty": "进阶",
            "token_count": 20,
        },
        {
            "chunk_id": "lora",
            "doc_id": "d2",
            "source_title": "LoRA",
            "heading_path": [],
            "text": "LoRA 通过低秩矩阵减少微调参数。",
            "page_no": None,
            "domain_tag": "ai-knowledge",
            "difficulty": "进阶",
            "token_count": 20,
        },
    ]
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return KnowledgeCorpus.load(path)


def test_bm25_ranks_keyword_match_and_is_stable(tmp_path: Path) -> None:
    retriever = Bm25KnowledgeRetriever(corpus(tmp_path))

    first = retriever.retrieve(KnowledgeQuery(query="LoRA 参数", top_k=2))
    second = retriever.retrieve(KnowledgeQuery(query="LoRA 参数", top_k=2))

    assert first.status is KnowledgeRetrievalStatus.OK
    assert first.hits[0].chunk_id == "lora"
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_bm25_returns_no_results_for_unknown_terms(tmp_path: Path) -> None:
    result = Bm25KnowledgeRetriever(corpus(tmp_path)).retrieve(
        KnowledgeQuery(query="不存在的术语")
    )

    assert result.status is KnowledgeRetrievalStatus.NO_RESULTS
    assert result.hits == ()
