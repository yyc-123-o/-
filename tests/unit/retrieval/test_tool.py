from pathlib import Path

from skillforge_kb.retrieval.bm25 import Bm25KnowledgeRetriever
from skillforge_kb.retrieval.models import KnowledgeQuery, KnowledgeRetrievalStatus
from skillforge_kb.retrieval.tool import KnowledgeRetrievalTool

from .test_bm25 import corpus


def test_tool_exposes_structured_langchain_tool(tmp_path: Path) -> None:
    wrapper = KnowledgeRetrievalTool(Bm25KnowledgeRetriever(corpus(tmp_path)))

    result = wrapper.invoke({"query": "RAG", "top_k": 1})

    assert wrapper.as_langchain_tool().name == "retrieve_knowledge"
    assert result.status is KnowledgeRetrievalStatus.OK
    assert result.hits[0].chunk_id == "rag"


def test_tool_converts_backend_errors_to_unavailable() -> None:
    class BrokenRetriever:
        def retrieve(self, query: KnowledgeQuery):
            raise RuntimeError("index unavailable")

    wrapper = KnowledgeRetrievalTool(BrokenRetriever())

    result = wrapper.invoke({"query": "RAG"})

    assert result.status is KnowledgeRetrievalStatus.UNAVAILABLE
    assert result.error_code == "retrieval_error"
    assert result.error_message == "index unavailable"
