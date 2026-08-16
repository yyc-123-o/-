import pytest

from skillforge_kb.agents.retrieval_agent_models import (
    DomainRetrievalRequest,
    DomainRetrievalResult,
    EvidenceGap,
    EvidenceSummary,
    RetrievalMethod,
    RetrievedEvidence,
)
from skillforge_kb.domain.enums import ContentKind, LicenseStatus
from skillforge_kb.evidence.models import EvidenceReviewStatus
from skillforge_kb.ontology.models import DepthLevel


@pytest.fixture
def retrieval_request() -> DomainRetrievalRequest:
    return DomainRetrievalRequest(
        original_query="卷积运算",
        rewritten_queries=("卷积运算 CNN",),
        profile_id="PROFILE-2026-0001-DEMO",
        concept_id="dl.cnn.convolution",
        depth=DepthLevel.INTRO,
        top_k=5,
    )


def _evidence(
    request: DomainRetrievalRequest,
    *,
    key: str,
    kind: ContentKind,
    status: EvidenceReviewStatus,
    evidence_status: str,
) -> RetrievedEvidence:
    return RetrievedEvidence(
        evidence_key=key,
        chunk_id=f"chunk-{key}",
        source_id="source-cnn",
        source_title="CNN reference",
        heading_path=("CNN", kind.value),
        excerpt=f"{kind.value} evidence for convolution",
        locator=f"section:{kind.value}",
        score=1.0,
        retrieval_method=(
            RetrievalMethod.PUBLISHED_INDEX
            if evidence_status == "formal"
            else RetrievalMethod.BM25
        ),
        concept_id=request.concept_id,
        depth=request.depth,
        content_kind=kind,
        review_status=status,
        license_status=(
            LicenseStatus.ALLOWED
            if evidence_status == "formal"
            else LicenseStatus.PENDING
        ),
        evidence_status=evidence_status,  # type: ignore[arg-type]
    )


def test_retrieval_result_separates_formal_and_candidate_evidence(
    retrieval_request: DomainRetrievalRequest,
) -> None:
    formal = _evidence(
        retrieval_request,
        key="formal-definition",
        kind=ContentKind.DEFINITION,
        status=EvidenceReviewStatus.PUBLISHED,
        evidence_status="formal",
    )
    candidate = _evidence(
        retrieval_request,
        key="candidate-code",
        kind=ContentKind.CODE,
        status=EvidenceReviewStatus.CANDIDATE,
        evidence_status="candidate",
    )
    result = DomainRetrievalResult(
        request=retrieval_request,
        evidence=(formal,),
        candidate_evidence=(candidate,),
        concept_evidence={
            retrieval_request.concept_id: (
                formal.evidence_key,
                candidate.evidence_key,
            )
        },
        evidence_summary=EvidenceSummary(
            formal_count=1,
            candidate_count=1,
            available_content_kinds=(ContentKind.DEFINITION, ContentKind.CODE),
            missing_content_kinds=(ContentKind.CODE, ContentKind.EXERCISE),
        ),
        evidence_gap=EvidenceGap(
            missing_content_kinds=(ContentKind.CODE, ContentKind.EXERCISE),
            message="published code and exercise evidence is missing",
        ),
    )
    assert result.evidence[0].review_status is EvidenceReviewStatus.PUBLISHED
    assert result.candidate_evidence[0].evidence_status == "candidate"


def test_retrieval_result_rejects_identity_mismatch(
    retrieval_request: DomainRetrievalRequest,
) -> None:
    mismatched = _evidence(
        retrieval_request,
        key="formal-definition",
        kind=ContentKind.DEFINITION,
        status=EvidenceReviewStatus.PUBLISHED,
        evidence_status="formal",
    ).model_copy(update={"concept_id": "dl.cnn.pooling"})
    with pytest.raises(ValueError, match="retrieval evidence scope"):
        DomainRetrievalResult(
            request=retrieval_request,
            evidence=(mismatched,),
            evidence_summary=EvidenceSummary(
                formal_count=1,
                missing_content_kinds=(ContentKind.CODE, ContentKind.EXERCISE),
            ),
            evidence_gap=EvidenceGap(
                missing_content_kinds=(ContentKind.CODE, ContentKind.EXERCISE),
                message="missing",
            ),
        )
