import re
from collections.abc import Iterable

from skillforge_kb.domain.enums import ContentKind, LicenseStatus
from skillforge_kb.evidence.manifest import EvidenceIndex
from skillforge_kb.evidence.models import EvidenceReviewStatus
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.resources.handoff import ResourceHandoffContract
from skillforge_kb.retrieval.corpus import KnowledgeCorpus
from skillforge_kb.retrieval.models import KnowledgeChunk, KnowledgeHit, KnowledgeQuery
from skillforge_kb.retrieval.tool import KnowledgeRetrievalTool

from .retrieval_agent_models import (
    DomainRetrievalRequest,
    DomainRetrievalResult,
    EvidenceGap,
    EvidenceSummary,
    RetrievalMethod,
    RetrievedEvidence,
)


class DomainRetrievalAgent:
    """Build a typed, candidate-safe retrieval result for one planner node."""

    def __init__(
        self,
        corpus: KnowledgeCorpus,
        retrieval_tool: KnowledgeRetrievalTool,
        evidence_index: EvidenceIndex,
        *,
        catalog: OntologyCatalog | None = None,
    ) -> None:
        if corpus.digest == "":
            raise ValueError("retrieval corpus digest must be available")
        self._chunks_by_id = {chunk.chunk_id: chunk for chunk in corpus.chunks}
        self._retrieval_tool = retrieval_tool
        self._evidence_index = evidence_index
        self._catalog = catalog

    def retrieve(
        self,
        request: DomainRetrievalRequest,
        handoff: ResourceHandoffContract,
    ) -> DomainRetrievalResult:
        request = DomainRetrievalRequest.model_validate(request.model_dump())
        self._validate_request_scope(request, handoff)
        required_kinds = tuple(handoff.evidence_filters.content_kinds)
        formal = self._formal_evidence(request, required_kinds)
        candidates = self._candidate_evidence(request, required_kinds)
        candidates = (*candidates, *self._metadata_candidates(request, required_kinds, candidates))
        available = tuple(
            kind
            for kind in required_kinds
            if any(item.content_kind is kind for item in formal + candidates)
        )
        missing = tuple(kind for kind in required_kinds if kind not in {
            item.content_kind for item in formal
        })
        gap = (
            EvidenceGap(
                missing_content_kinds=missing,
                message=(
                    "published evidence is missing for: "
                    + ", ".join(kind.value for kind in missing)
                ),
            )
            if missing
            else None
        )
        all_items = formal + candidates
        return DomainRetrievalResult(
            request=request,
            evidence=formal,
            candidate_evidence=candidates,
            concept_evidence={
                request.concept_id: tuple(item.evidence_key for item in all_items)
            },
            evidence_summary=EvidenceSummary(
                formal_count=len(formal),
                candidate_count=len(candidates),
                available_content_kinds=available,
                missing_content_kinds=missing,
            ),
            evidence_gap=gap,
        )

    def _metadata_candidates(
        self,
        request: DomainRetrievalRequest,
        required_kinds: tuple[ContentKind, ...],
        existing: tuple[RetrievedEvidence, ...],
    ) -> tuple[RetrievedEvidence, ...]:
        """Create scoped, non-publishable structure candidates from graph metadata.

        Ontology metadata is a fallback for nodes absent from the text corpus. It
        describes the intended learning scope, but is never treated as sourced
        teaching content or formal evidence.
        """
        if self._catalog is None:
            return ()
        concept = self._catalog.get_concept(request.concept_id)
        section = self._catalog.section_for(request.concept_id)
        level = next(item for item in concept.levels if item.level is request.depth)
        existing_kinds = {item.content_kind for item in existing}
        candidates: list[RetrievedEvidence] = []
        if (
            ContentKind.DEFINITION in required_kinds
            and ContentKind.DEFINITION not in existing_kinds
        ):
            candidates.append(
                self._metadata_candidate(
                    request,
                    ContentKind.DEFINITION,
                    section_title=section.title.zh,
                    text=(
                        f"知识点：{concept.names.zh} ({concept.names.en})。"
                        f"{concept.summary}"
                        f"本层学习目标：{'；'.join(level.learning_outcomes)}"
                    ),
                )
            )
        if (
            ContentKind.EXERCISE in required_kinds
            and ContentKind.EXERCISE not in existing_kinds
            and level.assessment_kinds
        ):
            candidates.append(
                self._metadata_candidate(
                    request,
                    ContentKind.EXERCISE,
                    section_title=section.title.zh,
                    text=(
                        f"练习结构候选（非正式题目）：围绕“{concept.names.zh}”"
                        f"检查学习目标“{'；'.join(level.learning_outcomes)}”。"
                        f"建议题型：{'、'.join(level.assessment_kinds)}。"
                    ),
                )
            )
        if ContentKind.CODE in required_kinds and ContentKind.CODE not in existing_kinds:
            candidates.append(
                self._metadata_candidate(
                    request,
                    ContentKind.CODE,
                    section_title=section.title.zh,
                    text=(
                        f"实操结构候选（非执行代码）：围绕“{concept.names.zh}”"
                        f"设计与学习目标“{'；'.join(level.learning_outcomes)}”对应的代码练习。"
                    ),
                )
            )
        return tuple(candidates)

    @staticmethod
    def _metadata_candidate(
        request: DomainRetrievalRequest,
        content_kind: ContentKind,
        *,
        section_title: str,
        text: str,
    ) -> RetrievedEvidence:
        key_suffix = f"{request.concept_id}_{request.depth.value}_{content_kind.value}"
        return RetrievedEvidence(
            evidence_key=f"candidate_ontology_{key_suffix}",
            chunk_id=f"ontology:{key_suffix}",
            source_id="ontology-catalog",
            source_title="AI course ontology metadata",
            heading_path=(section_title, request.concept_id, request.depth.value),
            excerpt=text,
            locator=f"ontology:{request.concept_id}:{request.depth.value}:{content_kind.value}",
            score=0.0,
            retrieval_method=RetrievalMethod.ONTOLOGY_METADATA,
            concept_id=request.concept_id,
            depth=request.depth,
            content_kind=content_kind,
            review_status=EvidenceReviewStatus.CANDIDATE,
            license_status=LicenseStatus.METADATA_ONLY,
            evidence_status="candidate",
        )

    def _formal_evidence(
        self,
        request: DomainRetrievalRequest,
        required_kinds: tuple[ContentKind, ...],
    ) -> tuple[RetrievedEvidence, ...]:
        records: list[RetrievedEvidence] = []
        for record in self._evidence_index.records:
            if (
                record.concept_id != request.concept_id
                or record.depth is not request.depth
                or record.content_kind not in required_kinds
                or record.review_status is not EvidenceReviewStatus.PUBLISHED
                or record.license_status is not LicenseStatus.ALLOWED
            ):
                continue
            chunk = self._chunks_by_id.get(record.chunk_id)
            if chunk is None:
                continue
            records.append(
                RetrievedEvidence(
                    evidence_key=record.evidence_id,
                    chunk_id=record.chunk_id,
                    source_id=record.source_id,
                    source_title=chunk.source_title,
                    heading_path=chunk.heading_path,
                    excerpt=chunk.text,
                    locator=record.locator,
                    page_no=chunk.page_no,
                    code_location=(
                        record.locator
                        if record.content_kind is ContentKind.CODE
                        else None
                    ),
                    score=1.0,
                    retrieval_method=RetrievalMethod.PUBLISHED_INDEX,
                    concept_id=record.concept_id,
                    depth=record.depth,
                    content_kind=record.content_kind,
                    review_status=record.review_status,
                    license_status=record.license_status,
                    evidence_status="formal",
                )
            )
        return _sort_evidence(records)

    def _candidate_evidence(
        self,
        request: DomainRetrievalRequest,
        required_kinds: tuple[ContentKind, ...],
    ) -> tuple[RetrievedEvidence, ...]:
        rows: list[RetrievedEvidence] = []
        for index, content_kind in enumerate(required_kinds):
            query_text = (
                request.rewritten_queries[index]
                if index < len(request.rewritten_queries)
                else f"{request.original_query} {content_kind.value}"
            )
            anchors = self._concept_anchors(request)
            query = KnowledgeQuery(
                query=query_text,
                top_k=request.top_k,
                concept_id=request.concept_id,
                anchors=anchors,
            )
            result = self._retrieval_tool.invoke(query)
            for hit in result.hits:
                chunk = self._chunks_by_id.get(hit.chunk_id)
                if chunk is None:
                    continue
                if _infer_content_kind(chunk) is not content_kind:
                    continue
                if not _is_relevant_chunk(
                    chunk,
                    request.concept_id,
                    concept_terms=self._concept_terms(request),
                ):
                    continue
                rows.append(self._candidate_from_hit(hit, request, content_kind))
        deduplicated: dict[tuple[str, ContentKind], RetrievedEvidence] = {}
        for row in rows:
            key = (row.chunk_id, row.content_kind)
            previous = deduplicated.get(key)
            if previous is None or row.score > previous.score:
                deduplicated[key] = row
        return _sort_evidence(deduplicated.values())

    def _concept_anchors(self, request: DomainRetrievalRequest) -> tuple[str, ...]:
        if self._catalog is None:
            return (request.concept_id,)
        concept = self._catalog.get_concept(request.concept_id)
        return (concept.names.zh, concept.names.en, *concept.aliases)

    def _concept_terms(self, request: DomainRetrievalRequest) -> tuple[str, ...]:
        return self._concept_anchors(request)

    def _candidate_from_hit(
        self,
        hit: KnowledgeHit,
        request: DomainRetrievalRequest,
        content_kind: ContentKind,
    ) -> RetrievedEvidence:
        chunk = self._chunks_by_id.get(hit.chunk_id)
        return RetrievedEvidence(
            evidence_key=f"candidate_{hit.chunk_id}_{content_kind.value}",
            chunk_id=hit.chunk_id,
            source_id=hit.doc_id,
            source_title=hit.source_title,
            heading_path=hit.heading_path,
            excerpt=hit.text,
            locator=(
                f"page:{chunk.page_no}"
                if chunk is not None and chunk.page_no is not None
                else f"chunk:{hit.chunk_id}"
            ),
            page_no=chunk.page_no if chunk is not None else None,
            code_location=(
                "/".join(hit.heading_path)
                if content_kind is ContentKind.CODE
                else None
            ),
            score=hit.score,
            retrieval_method=RetrievalMethod.BM25,
            concept_id=request.concept_id,
            depth=request.depth,
            content_kind=content_kind,
            review_status=EvidenceReviewStatus.CANDIDATE,
            license_status=LicenseStatus.PENDING,
            evidence_status="candidate",
        )

    @staticmethod
    def _validate_request_scope(
        request: DomainRetrievalRequest,
        handoff: ResourceHandoffContract,
    ) -> None:
        if (
            request.profile_id != handoff.profile_id
            or request.concept_id != handoff.concept_id
            or request.depth is not handoff.delivery_depth
        ):
            raise ValueError("retrieval request does not match resource handoff")


def _sort_evidence(items: Iterable[RetrievedEvidence]) -> tuple[RetrievedEvidence, ...]:
    return tuple(
        sorted(
            items,
            key=lambda item: (item.content_kind.value, -item.score, item.evidence_key),
        )
    )


_CODE_MARKERS = re.compile(
    r"(?:```|\b(?:import|from|def|class|return)\b|torch\.|numpy\.|np\.)",
    re.IGNORECASE,
)
_EXERCISE_MARKERS = re.compile(
    r"(?:练习|习题|题目|请计算|答案|解析|作答|选择题|填空题|exercise|question|solution)",
    re.IGNORECASE,
)
def _infer_content_kind(chunk: KnowledgeChunk) -> ContentKind:
    """Return the declared kind or a conservative legacy-chunk classification."""
    if chunk.content_kind is not None:
        return chunk.content_kind
    searchable = " ".join((*chunk.heading_path, chunk.text))
    if _EXERCISE_MARKERS.search(searchable):
        return ContentKind.EXERCISE
    if _CODE_MARKERS.search(searchable):
        return ContentKind.CODE
    return ContentKind.DEFINITION


def _is_relevant_chunk(
    chunk: KnowledgeChunk,
    concept_id: str,
    *,
    concept_terms: tuple[str, ...] = (),
) -> bool:
    """Reject lexical false positives before they become typed evidence."""
    searchable = " ".join((*chunk.heading_path, chunk.source_title, chunk.text))
    return not concept_terms or any(
        re.search(re.escape(term), searchable, re.IGNORECASE)
        for term in concept_terms
    )
