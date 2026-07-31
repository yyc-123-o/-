from pathlib import Path

from skillforge_kb.retrieval.bm25 import Bm25KnowledgeRetriever
from skillforge_kb.retrieval.corpus import KnowledgeCorpus
from skillforge_kb.retrieval.models import KnowledgeQuery, KnowledgeRetrievalStatus


def test_verified_candidate_corpus_retrieves_without_services() -> None:
    corpus = KnowledgeCorpus.load(Path("data/index_chunks.jsonl"))
    result = Bm25KnowledgeRetriever(corpus).retrieve(
        KnowledgeQuery(query="RAG 向量检索 BM25", top_k=5)
    )

    assert len(corpus.chunks) == 710
    assert result.status is KnowledgeRetrievalStatus.OK
    assert result.hits
    assert all(hit.evidence_state == "candidate" for hit in result.hits)
