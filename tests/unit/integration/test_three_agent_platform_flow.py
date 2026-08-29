import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

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
    AssessmentModel,
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


@pytest.fixture(autouse=True)
def isolate_platform_state_db(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "SKILLFORGE_PLATFORM_STATE_DB",
        str(tmp_path / "platform.sqlite3"),
    )


def _cnn_ready_profile(project_root: Path) -> LearnerProfileSnapshot:
    payload = json.loads(
        (project_root / "tests" / "fixtures" / "profile-2026-0001-demo.json")
        .read_text(encoding="utf-8")
    )
    return LearnerProfileSnapshot.model_validate(payload)


def test_default_service_does_not_load_cnn_demo_candidate_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = Path(__file__).parents[3]
    loaded_paths: list[Path] = []
    original_load_many = KnowledgeCorpus.load_many

    def capture_loaded_paths(paths: tuple[Path, ...]) -> KnowledgeCorpus:
        loaded_paths.extend(paths)
        return original_load_many(paths)

    monkeypatch.setattr(
        KnowledgeCorpus,
        "load_many",
        staticmethod(capture_loaded_paths),
    )

    build_default_platform_service(project_root)

    assert loaded_paths == [project_root / "data" / "index_chunks.jsonl"]


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


def test_cnn_node_uses_the_same_metadata_query_template_as_every_node() -> None:
    project_root = Path(__file__).parents[3]
    profile = _cnn_ready_profile(project_root)
    service = build_default_platform_service(project_root)

    result = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="metadata-query-template-e2e",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        )
    )

    assert result.handoff is not None
    assert result.retrieval is not None
    queries = result.retrieval.request.rewritten_queries
    assert len(queries) == 3
    assert all(result.handoff.concept_id in query for query in queries)
    assert queries[0].endswith("定义 概念 解释 是什么")
    assert queries[1].endswith("代码 实现 示例 参数")
    assert queries[2].endswith("练习 习题 评估 例题")


def test_completing_current_node_advances_the_existing_learning_run() -> None:
    project_root = Path(__file__).parents[3]
    profile = LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="PROFILE-LEARNING-PROGRESS-TEST",
        learner_ref="0" * 64,
        graph_version="ai-course-v1",
    )
    service = build_default_platform_service(project_root)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            target_concept_id="dl.cnn.convolution",
            idempotency_key="learning-progress-preview",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        )
    )

    with pytest.raises(ValueError, match="completion gate"):
        service.complete_current_node(initial.run_id, "math.linear-algebra.scalar")
    capped = service.record_lecture_progress(
        initial.run_id,
        {"concept_id": "math.linear-algebra.scalar", "progress": 0.80},
    )
    assert capped.learning_progress is not None
    assert capped.learning_progress.lecture_progress == 0.25
    for progress in (0.50, 0.75, 0.80):
        service.record_lecture_progress(
            initial.run_id,
            {"concept_id": "math.linear-algebra.scalar", "progress": progress},
        )
    service.review_practice(
        initial.run_id,
        {
            "concept_id": "math.linear-algebra.scalar",
            "source": "s = 1\nv = 1\nscaled = 1\nresult = 1\nprint(result)",
        },
    )
    updated = service.submit_assessment(
        initial.run_id,
        {
            "assessment_id": "learning-progress-complete",
            "concept_id": "math.linear-algebra.scalar",
            "score": 1.0,
            "response_time_ms": 1000,
            "hint_count": 0,
            "attempt_count": 1,
        },
    )

    assert updated.status is PlatformRunStatus.COMPLETED
    assert updated.planning is not None
    assert updated.planning.current_node is not None
    assert updated.planning.current_node.concept_id == "math.linear-algebra.vector"
    assert updated.handoff is not None
    assert updated.handoff.concept_id == "math.linear-algebra.vector"
    assert updated.resources is not None
    assert updated.resources.publication_status == "candidate_draft"
    completed = next(
        node
        for node in updated.planning.path.nodes
        if node.concept_id == "math.linear-algebra.scalar"
    )
    assert completed.status.value == "completed"


def test_assessment_updates_profile_and_replans_depth_before_advancing() -> None:
    project_root = Path(__file__).parents[3]
    profile = LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="PROFILE-ASSESSMENT-PROGRESS-TEST",
        learner_ref="0" * 64,
        graph_version="ai-course-v1",
    )
    service = build_default_platform_service(project_root)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            target_concept_id="dl.cnn.convolution",
            idempotency_key="assessment-progress-preview",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        )
    )

    updated = service.submit_assessment(
        initial.run_id,
        {
            "assessment_id": "assessment-progress-1",
            "concept_id": "math.linear-algebra.scalar",
            "score": 1.0,
            "response_time_ms": 40000,
            "hint_count": 0,
            "attempt_count": 1,
        },
    )

    assert updated.planning is not None
    assert updated.planning.current_node is not None
    assert updated.planning.current_node.concept_id == "math.linear-algebra.scalar"
    assert updated.handoff is not None
    assert updated.handoff.concept_id == "math.linear-algebra.scalar"
    assert updated.handoff.path_id == initial.handoff.path_id


def test_bkt_assessment_updates_profile_and_replans() -> None:
    project_root = Path(__file__).parents[3]
    profile = LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="PROFILE-BKT-FLOW-TEST",
        learner_ref="0" * 64,
        graph_version="ai-course-v1",
    )
    service = build_default_platform_service(project_root)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="assessment-bkt-flow",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
            assessment_model=AssessmentModel.BKT,
        )
    )
    assert initial.planning is not None
    assert initial.planning.current_node is not None
    concept_id = initial.planning.current_node.concept_id
    submission = {
        "assessment_id": "assessment-bkt-flow-1",
        "concept_id": concept_id,
        "score": 1.0,
        "response_time_ms": 1000,
        "hint_count": 0,
        "attempt_count": 1,
    }

    updated = service.submit_assessment(initial.run_id, submission)
    replay = service.submit_assessment(initial.run_id, submission)
    saved_request = service._repository.get_request(initial.run_id)

    assert replay == updated
    assert updated.planning is not None
    assert updated.planning.current_node is not None
    assert updated.planning.current_node.concept_id == concept_id
    assert updated.learning_progress is not None
    assert updated.learning_progress.practice_completed is False
    assert saved_request is not None
    mastery = next(
        item for item in saved_request.profile.knowledge_mastery
        if item.concept_id == concept_id
    )
    assert mastery.mastery_score == pytest.approx(0.5764705882)


def test_bkt_failed_assessment_keeps_current_node_open() -> None:
    project_root = Path(__file__).parents[3]
    profile = LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="PROFILE-BKT-FAILED-FLOW-TEST",
        learner_ref="0" * 64,
        graph_version="ai-course-v1",
    )
    service = build_default_platform_service(project_root)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="assessment-bkt-failed-flow",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
            assessment_model=AssessmentModel.BKT,
        )
    )
    assert initial.planning is not None
    assert initial.planning.current_node is not None
    concept_id = initial.planning.current_node.concept_id

    updated = service.submit_assessment(
        initial.run_id,
        {
            "assessment_id": "assessment-bkt-failed-1",
            "concept_id": concept_id,
            "score": 0.0,
            "response_time_ms": 150000,
            "hint_count": 2,
            "attempt_count": 2,
        },
    )

    assert updated.planning is not None
    assert updated.planning.current_node is not None
    assert updated.planning.current_node.concept_id == concept_id


def test_correct_candidate_quiz_choices_advance_the_learning_node() -> None:
    project_root = Path(__file__).parents[3]
    profile = LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="PROFILE-CANDIDATE-QUIZ-CORRECT-TEST",
        learner_ref="0" * 64,
        graph_version="ai-course-v1",
    )
    service = build_default_platform_service(project_root)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="candidate-quiz-correct",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        )
    )
    assert initial.resources is not None
    assert initial.resources.preview_package is not None
    assert initial.resources.preview_package.draft is not None
    answers = {
        item.question_id: item.correct_choice
        for item in initial.resources.preview_package.draft.student_quiz.items
    }

    updated = service.submit_assessment(
        initial.run_id,
        {
            "assessment_id": "candidate-quiz-correct-1",
            "concept_id": "math.linear-algebra.scalar",
            "score": 0.0,
            "responses": answers,
            "response_time_ms": 40000,
            "hint_count": 0,
            "attempt_count": 1,
        },
    )

    assert updated.planning is not None
    assert updated.planning.current_node is not None
    assert updated.planning.current_node.concept_id == "math.linear-algebra.scalar"


def test_incorrect_candidate_quiz_choices_keep_the_learning_node_open() -> None:
    project_root = Path(__file__).parents[3]
    profile = LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="PROFILE-CANDIDATE-QUIZ-INCORRECT-TEST",
        learner_ref="0" * 64,
        graph_version="ai-course-v1",
    )
    service = build_default_platform_service(project_root)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="candidate-quiz-incorrect",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        )
    )
    assert initial.resources is not None
    assert initial.resources.preview_package is not None
    assert initial.resources.preview_package.draft is not None
    answers = {
        item.question_id: 1 - item.correct_choice
        for item in initial.resources.preview_package.draft.student_quiz.items
    }

    updated = service.submit_assessment(
        initial.run_id,
        {
            "assessment_id": "candidate-quiz-incorrect-1",
            "concept_id": "math.linear-algebra.scalar",
            "score": 1.0,
            "responses": answers,
            "response_time_ms": 40000,
            "hint_count": 0,
            "attempt_count": 1,
        },
    )

    assert updated.planning is not None
    assert updated.planning.current_node is not None
    assert updated.planning.current_node.concept_id == "math.linear-algebra.scalar"


def test_failed_assessment_keeps_node_open_and_records_error_pattern() -> None:
    project_root = Path(__file__).parents[3]
    profile = LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="PROFILE-ASSESSMENT-FAILED-TEST",
        learner_ref="0" * 64,
        graph_version="ai-course-v1",
    )
    service = build_default_platform_service(project_root)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="assessment-failed-preview",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        )
    )

    updated = service.submit_assessment(
        initial.run_id,
        {
            "assessment_id": "assessment-failed-1",
            "concept_id": "math.linear-algebra.scalar",
            "score": 0.0,
            "response_time_ms": 150000,
            "hint_count": 2,
            "attempt_count": 2,
        },
    )

    assert updated.planning is not None
    assert updated.planning.current_node is not None
    assert updated.planning.current_node.concept_id == "math.linear-algebra.scalar"
    assert updated.handoff is not None
    assert updated.handoff.concept_id == "math.linear-algebra.scalar"


def test_duplicate_assessment_is_idempotent_and_conflicting_payload_is_rejected() -> None:
    project_root = Path(__file__).parents[3]
    profile = LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="PROFILE-ASSESSMENT-IDEMPOTENCY-TEST",
        learner_ref="0" * 64,
        graph_version="ai-course-v1",
    )
    service = build_default_platform_service(project_root)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            target_concept_id="dl.cnn.convolution",
            idempotency_key="assessment-idempotency-preview",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        )
    )
    submission = {
        "assessment_id": "assessment-idempotent-1",
        "concept_id": "math.linear-algebra.scalar",
        "score": 0.0,
        "response_time_ms": 150000,
        "hint_count": 2,
        "attempt_count": 2,
    }

    first = service.submit_assessment(initial.run_id, submission)
    replay = service.submit_assessment(initial.run_id, submission)

    assert replay == first
    assert first.planning is not None
    assert first.planning.current_node is not None
    assert first.planning.current_node.concept_id == "math.linear-algebra.scalar"

    with pytest.raises(ValueError, match="different payload"):
        service.submit_assessment(
            initial.run_id,
            {**submission, "score": 1.0},
        )


def test_start_node_allows_any_unblocked_path_node() -> None:
    project_root = Path(__file__).parents[3]
    profile = LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="PROFILE-START-NODE-TEST",
        learner_ref="0" * 64,
        graph_version="ai-course-v1",
    )
    service = build_default_platform_service(project_root)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            target_concept_id="dl.cnn.convolution",
            idempotency_key="start-node-preview",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        )
    )

    started = service.start_node(initial.run_id, "dl.vision.image-tensor")

    assert started.planning is not None
    assert started.planning.current_node is not None
    assert started.planning.current_node.concept_id == "dl.vision.image-tensor"
    assert started.handoff is not None
    assert started.handoff.concept_id == "dl.vision.image-tensor"


def test_start_node_preserves_mastered_skips_for_adapted_profile() -> None:
    project_root = Path(__file__).parents[3]
    profile = _cnn_ready_profile(project_root)
    service = build_default_platform_service(project_root)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            target_concept_id="dl.cnn.convolution",
            idempotency_key="start-node-adapted-profile-preview",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        )
    )

    started = service.start_node(initial.run_id, "dl.cnn.cross-correlation")

    assert started.status is PlatformRunStatus.COMPLETED
    assert started.planning is not None
    assert started.planning.current_node is not None
    assert started.planning.current_node.concept_id == "dl.cnn.cross-correlation"
    assert started.planning.path is not None
    assert all(
        node.status.value == "skipped"
        for node in started.planning.path.nodes[:57]
    )
    assert started.planning.path.nodes[57].concept_id == "dl.cnn.convolution"
    assert started.planning.path.nodes[57].status.value == "pending"


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
