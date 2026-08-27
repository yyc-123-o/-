from collections.abc import Mapping
from typing import Protocol

from langchain_core.tools import StructuredTool

from .models import KnowledgeQuery, KnowledgeRetrievalResult, KnowledgeRetrievalStatus


class KnowledgeRetriever(Protocol):
    def retrieve(self, query: KnowledgeQuery) -> KnowledgeRetrievalResult: ...


class KnowledgeRetrievalTool:
    def __init__(self, retriever: KnowledgeRetriever, *, strict_scope: bool = False) -> None:
        self._retriever = retriever
        self._strict_scope = strict_scope

    def invoke(
        self,
        request: KnowledgeQuery | Mapping[str, object],
    ) -> KnowledgeRetrievalResult:
        query = KnowledgeQuery.model_validate(request)
        try:
            result = KnowledgeRetrievalResult.model_validate(self._retriever.retrieve(query))
            if (
                self._strict_scope
                and result.status is KnowledgeRetrievalStatus.OK
                and query.anchors
            ):
                anchors = tuple(item.casefold() for item in query.anchors)
                hits = tuple(
                    hit
                    for hit in result.hits
                    if any(
                        anchor in " ".join((hit.source_title, *hit.heading_path)).casefold()
                        for anchor in anchors
                    )
                )
                if not hits:
                    return KnowledgeRetrievalResult.no_results(
                        query, corpus_digest=result.corpus_digest
                    )
                result = result.model_copy(update={"hits": hits})
            return result
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
