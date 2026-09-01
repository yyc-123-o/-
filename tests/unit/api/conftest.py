from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from skillforge_kb.agents.retrieval_agent_models import EvidenceGap
from skillforge_kb.api.app import create_app
from skillforge_kb.domain.enums import ContentKind
from skillforge_kb.evaluation import KnowledgeTracingEvaluationReport
from skillforge_kb.ontology.models import LearnerProfileSnapshot
from skillforge_kb.platform.models import (
    PlanningPathMode,
    PlatformRunRequest,
    PlatformRunResult,
    PlatformRunStatus,
    build_request_digest,
    build_run_id,
)
from skillforge_kb.platform.practice_review import PracticeReviewResult
from skillforge_kb.platform.repository import InMemoryPlatformRunRepository


class StubPlatformService:
    def __init__(self) -> None:
        self.repository = InMemoryPlatformRunRepository()
        self.evaluation_reports: tuple[KnowledgeTracingEvaluationReport, ...] = ()
        self.start_calls: list[tuple[str, str, PlanningPathMode]] = []

    def run(self, request: PlatformRunRequest) -> PlatformRunResult:
        existing = self.repository.reserve(request)
        if existing is not None:
            return existing
        result = PlatformRunResult(
            run_id=build_run_id(request),
            request_digest=build_request_digest(request),
            profile_id=request.profile.profile_id,
            status=PlatformRunStatus.BLOCKED,
            evidence_gap=EvidenceGap(
                missing_content_kinds=(ContentKind.DEFINITION,),
                message="published definition evidence is missing",
            ),
        )
        self.repository.save(result)
        return result

    def peek(self, request: PlatformRunRequest) -> PlatformRunResult | None:
        return self.repository.peek(request)

    def get(self, run_id: str) -> PlatformRunResult | None:
        return self.repository.get(run_id)

    def complete_current_node(self, run_id: str, concept_id: str) -> PlatformRunResult:
        raise ValueError("stub service does not support learning progress")

    def submit_assessment(self, run_id: str, submission) -> PlatformRunResult:
        raise ValueError("stub service does not support assessment updates")

    def refresh_current_resources(self, run_id: str) -> PlatformRunResult:
        raise ValueError("stub service does not support resource refresh")

    def start_node(
        self,
        run_id: str,
        concept_id: str,
        path_mode: PlanningPathMode = PlanningPathMode.PERSONALIZED,
    ) -> PlatformRunResult:
        self.start_calls.append((run_id, concept_id, path_mode))
        result = self.repository.get(run_id)
        if result is None:
            raise KeyError(f"platform run not found: {run_id}")
        return result

    def review_practice(self, run_id: str, submission) -> PracticeReviewResult:
        return PracticeReviewResult(
            concept_id=submission.concept_id,
            accepted=True,
            feedback="静态检查通过。",
            next_step="解释输出结果。",
        )

    def evaluate_profile_knowledge_tracing(
        self,
        profile_id: str,
    ) -> tuple[KnowledgeTracingEvaluationReport, ...]:
        if not self.evaluation_reports:
            raise ValueError("no prediction observations")
        return self.evaluation_reports


@pytest.fixture
def service() -> StubPlatformService:
    return StubPlatformService()


@pytest.fixture
def profile() -> LearnerProfileSnapshot:
    return LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="PROFILE-2026-0001-DEMO",
        learner_ref="0" * 64,
        graph_version="ai-course-v1",
        generated_at=datetime(2026, 8, 16, tzinfo=UTC),
    )


@pytest.fixture
def client(service: StubPlatformService) -> Iterator[TestClient]:
    with TestClient(create_app(service)) as test_client:
        yield test_client


@pytest.fixture
def profile_payload(profile) -> dict[str, object]:
    return profile.model_dump(mode="json")
