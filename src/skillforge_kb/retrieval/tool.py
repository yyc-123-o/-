from collections.abc import Mapping
from typing import Protocol

from langchain_core.tools import StructuredTool

from .models import KnowledgeQuery, KnowledgeRetrievalResult


class KnowledgeRetriever(Protocol):
    def retrieve(self, query: KnowledgeQuery) -> KnowledgeRetrievalResult: ...


class KnowledgeRetrievalTool:
    def __init__(self, retriever: KnowledgeRetriever) -> None:
        self._retriever = retriever

    def invoke(
        self,
        request: KnowledgeQuery | Mapping[str, object],
    ) -> KnowledgeRetrievalResult:
        query = KnowledgeQuery.model_validate(request)
        try:
            result = self._retriever.retrieve(query)
            return KnowledgeRetrievalResult.model_validate(result)
        except Exception as exc:
            return KnowledgeRetrievalResult.unavailable(
                query,
                error_code="retrieval_error",
                error_message=str(exc),
            )

    def as_langchain_tool(self) -> StructuredTool:
        def retrieve_knowledge(
            query: str,
            top_k: int = 5,
            concept_id: str | None = None,
        ) -> dict[str, object]:
            result = self.invoke(
                KnowledgeQuery(query=query, top_k=top_k, concept_id=concept_id)
            )
            return result.model_dump(mode="json")

        return StructuredTool.from_function(
            func=retrieve_knowledge,
            name="retrieve_knowledge",
            description=(
                "Retrieve candidate learning evidence for a course concept. "
                "Results are unreviewed context and are not published evidence."
            ),
            args_schema=KnowledgeQuery,
            infer_schema=False,
        )
