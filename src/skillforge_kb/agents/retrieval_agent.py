import re
from collections.abc import Iterable

from skillforge_kb.domain.enums import ContentKind, LicenseStatus
from skillforge_kb.evidence.manifest import EvidenceIndex
from skillforge_kb.evidence.models import EvidenceReviewStatus
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

_QUERY_TERMS: dict[ContentKind, str] = {
    ContentKind.DEFINITION: "卷积运算 CNN 互相关 卷积核 输入输出通道 padding stride 输出尺寸",
    ContentKind.CODE: "Python PyTorch nn.Conv2d 卷积 输入输出 shape 参数",
    ContentKind.EXERCISE: "卷积输出尺寸计算 卷积核参数量 padding stride 练习 答案 解析",
}


class DomainRetrievalAgent:
    """Build a typed, candidate-safe retrieval result for one planner node."""

    def __init__(
        self,
        corpus: KnowledgeCorpus,
        retrieval_tool: KnowledgeRetrievalTool,
        evidence_index: EvidenceIndex,
    ) -> None:
        if corpus.digest == "":
            raise ValueError("retrieval corpus digest must be available")
        self._chunks_by_id = {chunk.chunk_id: chunk for chunk in corpus.chunks}
        self._retrieval_tool = retrieval_tool
        self._evidence_index = evidence_index

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
        for content_kind in required_kinds:
            query_text = _QUERY_TERMS.get(content_kind, request.original_query)
            query = KnowledgeQuery(
                query=query_text,
                top_k=request.top_k,
                concept_id=request.concept_id,
                anchors=(request.concept_id, "CNN", "卷积"),
            )
            result = self._retrieval_tool.invoke(query)
            for hit in result.hits:
                chunk = self._chunks_by_id.get(hit.chunk_id)
                if chunk is None:
                    continue
                if _infer_content_kind(chunk) is not content_kind:
                    continue
                if not _is_relevant_chunk(chunk, request.concept_id):
                    continue
                rows.append(self._candidate_from_hit(hit, request, content_kind))
        deduplicated: dict[tuple[str, ContentKind], RetrievedEvidence] = {}
        for row in rows:
            key = (row.chunk_id, row.content_kind)
            previous = deduplicated.get(key)
            if previous is None or row.score > previous.score:
                deduplicated[key] = row
        return _sort_evidence(deduplicated.values())

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
    r"(?:```|\b(?:import|from|def|class|return)\b|nn\.Conv2d|torch\.|numpy\.|np\.)",
    re.IGNORECASE,
)
_EXERCISE_MARKERS = re.compile(
    r"(?:练习|习题|题目|请计算|答案|解析|作答|选择题|填空题|exercise|question|solution)",
    re.IGNORECASE,
)
_CNN_EXCLUDED_MARKERS = re.compile(
    r"(?:GAN|DCGAN|TextCNN|ConvTranspose|转置卷积|生成器|判别器)",
    re.IGNORECASE,
)
_CNN_RELEVANT_MARKERS = re.compile(
    r"(?:卷积|互相关|卷积核|convolution|conv2d|padding|stride|输出尺寸)",
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


def _is_relevant_chunk(chunk: KnowledgeChunk, concept_id: str) -> bool:
    """Reject lexical false positives before they become typed evidence."""
    if concept_id != "dl.cnn.convolution":
        return True
    searchable = " ".join((*chunk.heading_path, chunk.source_title, chunk.text))
    if _CNN_EXCLUDED_MARKERS.search(searchable):
        return False
    return bool(_CNN_RELEVANT_MARKERS.search(searchable))
