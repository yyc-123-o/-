import json
from datetime import UTC, datetime
from pathlib import Path

from skillforge_kb.agents.planning_agent import CoursePlanningAgent
from skillforge_kb.agents.resource_agent import ResourceGenerationAgent
from skillforge_kb.agents.retrieval_agent import DomainRetrievalAgent
from skillforge_kb.domain.enums import ContentKind, Language, LicenseStatus
from skillforge_kb.evidence.manifest import EvidenceIndex
from skillforge_kb.evidence.models import (
    EvidenceRecord,
    EvidenceReviewStatus,
    build_evidence_id,
)
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.concept_attributes import load_concept_attributes
from skillforge_kb.ontology.models import DepthLevel, LearnerProfileSnapshot
from skillforge_kb.ontology.resource_blueprints import load_resource_blueprints
from skillforge_kb.platform.graph import PlatformGraphDependencies, PlatformService
from skillforge_kb.platform.models import (
    ExecutionMode,
    PlatformRunRequest,
    PlatformRunStatus,
)
from skillforge_kb.platform.repository import InMemoryPlatformRunRepository
from skillforge_kb.platform.runtime import (
    ResourceHandoffFactory,
    SystemClock,
    build_default_platform_service,
)
from skillforge_kb.retrieval.bm25 import Bm25KnowledgeRetriever
from skillforge_kb.retrieval.corpus import KnowledgeCorpus, build_corpus_digest
from skillforge_kb.retrieval.models import KnowledgeChunk
from skillforge_kb.retrieval.tool import KnowledgeRetrievalTool


def _cnn_ready_profile(project_root: Path) -> LearnerProfileSnapshot:
    payload = json.loads(
        (project_root / "tests" / "fixtures" / "profile-2026-0001-demo.json")
        .read_text(encoding="utf-8")
    )
    return LearnerProfileSnapshot.model_validate(payload)


def test_strict_run_blocks_without_published_evidence() -> None:
    project_root = Path(__file__).parents[3]
    profile = _cnn_ready_profile(project_root)
    service = build_default_platform_service(project_root)

    result = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="cnn-strict-e2e",
            execution_mode=ExecutionMode.STRICT,
        )
    )

    assert result.status is PlatformRunStatus.BLOCKED
    assert result.handoff is not None
    assert result.handoff.concept_id == "dl.cnn.convolution"
    assert result.resources is None
    assert result.evidence_gap is not None


def test_candidate_preview_completes_without_publish_rights() -> None:
    project_root = Path(__file__).parents[3]
    profile = _cnn_ready_profile(project_root)
    service = build_default_platform_service(project_root)
    request = PlatformRunRequest(
        profile=profile,
        idempotency_key="cnn-preview-e2e",
        execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
    )

    first = service.run(request)
    replay = service.run(request)

    assert first.status is PlatformRunStatus.COMPLETED
    assert first.resources is not None
    assert first.resources.publication_status == "candidate_draft"
    assert first.resources.formal_package is None
    assert first.resources.preview_package is not None
    assert replay == first


def test_published_fixture_completes_formal_run() -> None:
    project_root = Path(__file__).parents[3]
    profile = _cnn_ready_profile(project_root)
    service = _published_service(project_root)

    result = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="cnn-formal-e2e",
            execution_mode=ExecutionMode.STRICT,
        )
    )

    assert result.status is PlatformRunStatus.COMPLETED
    assert result.resources is not None
    assert result.resources.publication_status == "formal"
    assert result.resources.formal_package is not None


def _published_service(project_root: Path) -> PlatformService:
    ontology_root = project_root / "resources" / "ontology"
    catalog = OntologyCatalog.load(
        ontology_root / "ai_course_v1.yaml",
        ontology_root / "ai_relations_v1.yaml",
    )
    attributes = load_concept_attributes(
        catalog,
        ontology_root / "concept_attributes_v1.yaml",
    )
    blueprints = load_resource_blueprints(
        catalog,
        ontology_root / "resource_blueprints_v1.yaml",
    )
    chunks = tuple(
        KnowledgeChunk(
            chunk_id=f"published-{kind.value}",
            doc_id="published-cnn",
            source_title="CNN published fixture",
            heading_path=("CNN", kind.value),
            text=f"卷积 CNN {kind.value} evidence with padding stride Conv2d output size.",
            page_no=index,
            domain_tag="ai-knowledge",
            difficulty="入门",
            token_count=30,
        )
        for index, kind in enumerate(
            (ContentKind.DEFINITION, ContentKind.CODE, ContentKind.EXERCISE),
            start=1,
        )
    )
    corpus = KnowledgeCorpus(chunks=chunks, digest=build_corpus_digest(chunks))
    records = tuple(
        _published_record(catalog.course_document.version, chunk, kind)
        for chunk, kind in zip(
            chunks,
            (ContentKind.DEFINITION, ContentKind.CODE, ContentKind.EXERCISE),
            strict=True,
        )
    )
    evidence_index = EvidenceIndex(
        version="evidence-manifest-test-v1",
        graph_version=catalog.course_document.version,
        records=records,
    )
    dependencies = PlatformGraphDependencies(
        planning_agent=CoursePlanningAgent.create(catalog, attributes),
        retrieval_agent=DomainRetrievalAgent(
            corpus,
            KnowledgeRetrievalTool(Bm25KnowledgeRetriever(corpus)),
            evidence_index,
        ),
        resource_agent=ResourceGenerationAgent(),
        handoff_factory=ResourceHandoffFactory(catalog, blueprints, evidence_index),
        evidence_index=evidence_index,
        clock=SystemClock(),
    )
    return PlatformService(dependencies, InMemoryPlatformRunRepository())


def _published_record(
    graph_version: str,
    chunk: KnowledgeChunk,
    kind: ContentKind,
) -> EvidenceRecord:
    normalized_hash = f"{chunk.page_no:064x}"
    locator = f"page {chunk.page_no}"
    evidence_id = build_evidence_id(
        graph_version=graph_version,
        source_id=chunk.doc_id,
        chunk_id=chunk.chunk_id,
        concept_id="dl.cnn.convolution",
        depth=DepthLevel.INTRO,
        locator=locator,
        normalized_hash=normalized_hash,
        language=Language.ZH,
        content_kind=kind,
    )
    return EvidenceRecord(
        evidence_id=evidence_id,
        graph_version=graph_version,
        source_id=chunk.doc_id,
        chunk_id=chunk.chunk_id,
        concept_id="dl.cnn.convolution",
        depth=DepthLevel.INTRO,
        source_url=f"https://example.edu/cnn/{kind.value}",
        locator=locator,
        normalized_hash=normalized_hash,
        language=Language.ZH,
        content_kind=kind,
        difficulty=1,
        license_status=LicenseStatus.ALLOWED,
        review_status=EvidenceReviewStatus.PUBLISHED,
        reviewed_by="test-reviewer",
        reviewed_at=datetime(2026, 8, 16, tzinfo=UTC),
    )
