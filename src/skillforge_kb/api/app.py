from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from skillforge_kb.ontology.profile_agent_adapter import AdaptedLearnerProfile
from skillforge_kb.evaluation import KnowledgeTracingEvaluationReport
from skillforge_kb.platform.models import (
    AssessmentSubmission,
    PlatformRunRequest,
    PlatformRunResult,
    PlatformStepRecord,
    PracticeReviewSubmission,
)
from skillforge_kb.platform.practice_review import PracticeReviewResult
from skillforge_kb.platform.repository import IdempotencyConflict


class PlatformApplicationService(Protocol):
    def run(self, request: PlatformRunRequest) -> PlatformRunResult: ...

    def peek(self, request: PlatformRunRequest) -> PlatformRunResult | None: ...

    def get(self, run_id: str) -> PlatformRunResult | None: ...

    def complete_current_node(
        self,
        run_id: str,
        concept_id: str,
    ) -> PlatformRunResult: ...

    def submit_assessment(
        self,
        run_id: str,
        submission: AssessmentSubmission | dict[str, object],
    ) -> PlatformRunResult: ...

    def start_node(self, run_id: str, concept_id: str) -> PlatformRunResult: ...

    def review_practice(
        self, run_id: str, submission: PracticeReviewSubmission | dict[str, object]
    ) -> PracticeReviewResult: ...

    def evaluate_profile_knowledge_tracing(
        self,
        profile_id: str,
    ) -> tuple[KnowledgeTracingEvaluationReport, ...]: ...


class ProfileAdaptationService(Protocol):
    def adapt(self, raw: Mapping[str, object]) -> AdaptedLearnerProfile: ...


def create_app(
    service: PlatformApplicationService,
    profile_adapter: ProfileAdaptationService | None = None,
) -> FastAPI:
    app = FastAPI(title="SkillForge Platform API", version="1.0.0")
    app.state.platform_service = service
    app.state.profile_adapter = profile_adapter
    static_root = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=static_root), name="static")

    @app.exception_handler(IdempotencyConflict)
    async def idempotency_conflict_handler(
        _request: object,
        error: IdempotencyConflict,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": {
                    "code": "idempotency_conflict",
                    "message": str(error),
                }
            },
        )

    @app.get("/api/v1/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "execution_modes": ["strict", "candidate_preview"],
        }

    @app.post("/api/v1/profiles/adapt")
    def adapt_profile(raw_profile: dict[str, object]) -> dict[str, object]:
        if profile_adapter is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "profile_adapter_unavailable",
                    "message": "learner profile Agent adapter is not configured",
                },
            )
        try:
            adapted = profile_adapter.adapt(raw_profile)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "invalid_profile_agent_output",
                    "message": str(exc) or type(exc).__name__,
                },
            ) from exc
        return adapted.model_dump(mode="json")

    @app.get(
        "/api/v1/profiles/{profile_id}/knowledge-tracing/evaluation",
        response_model=list[KnowledgeTracingEvaluationReport],
    )
    def evaluate_profile_knowledge_tracing(
        profile_id: str,
    ) -> list[KnowledgeTracingEvaluationReport]:
        try:
            return list(service.evaluate_profile_knowledge_tracing(profile_id))
        except ValueError as exc:
            if str(exc) == "no prediction observations":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "code": "knowledge_tracing_not_found",
                        "message": str(exc),
                    },
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "invalid_knowledge_tracing_evaluation",
                    "message": str(exc) or type(exc).__name__,
                },
            ) from exc

    @app.get("/", response_class=FileResponse, include_in_schema=False)
    def console() -> FileResponse:
        return FileResponse(static_root / "index.html")

    @app.post(
        "/api/v1/runs",
        response_model=PlatformRunResult,
        status_code=status.HTTP_201_CREATED,
    )
    def create_run(
        request: PlatformRunRequest,
        response: Response,
    ) -> PlatformRunResult:
        existed = service.peek(request) is not None
        try:
            result = service.run(request)
        except IdempotencyConflict:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "platform_unavailable",
                    "message": str(exc) or type(exc).__name__,
                },
            ) from exc
        response.status_code = (
            status.HTTP_200_OK if existed else status.HTTP_201_CREATED
        )
        return result

    @app.get("/api/v1/runs/{run_id}", response_model=PlatformRunResult)
    def get_run(run_id: str) -> PlatformRunResult:
        result = service.get(run_id)
        if result is None:
            raise _run_not_found(run_id)
        return result

    @app.get(
        "/api/v1/runs/{run_id}/events",
        response_model=list[PlatformStepRecord],
    )
    def get_run_events(run_id: str) -> list[PlatformStepRecord]:
        result = service.get(run_id)
        if result is None:
            raise _run_not_found(run_id)
        return list(result.steps)

    @app.post("/api/v1/runs/{run_id}/complete-node", response_model=PlatformRunResult)
    def complete_node(run_id: str, payload: dict[str, object]) -> PlatformRunResult:
        concept_id = payload.get("concept_id")
        if not isinstance(concept_id, str) or not concept_id.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "invalid_completion", "message": "concept_id is required"},
            )
        try:
            return service.complete_current_node(run_id, concept_id.strip())
        except KeyError as exc:
            raise _run_not_found(run_id) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "invalid_learning_transition", "message": str(exc)},
            ) from exc

    @app.post("/api/v1/runs/{run_id}/assessment", response_model=PlatformRunResult)
    def submit_assessment(
        run_id: str,
        submission: AssessmentSubmission,
    ) -> PlatformRunResult:
        try:
            return service.submit_assessment(run_id, submission)
        except KeyError as exc:
            raise _run_not_found(run_id) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "invalid_assessment", "message": str(exc)},
            ) from exc

    @app.post(
        "/api/v1/runs/{run_id}/practice-review",
        response_model=PracticeReviewResult,
    )
    def review_practice(
        run_id: str,
        submission: PracticeReviewSubmission,
    ) -> PracticeReviewResult:
        try:
            return service.review_practice(run_id, submission)
        except KeyError as exc:
            raise _run_not_found(run_id) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "invalid_practice_submission", "message": str(exc)},
            ) from exc

    @app.post("/api/v1/runs/{run_id}/start-node", response_model=PlatformRunResult)
    def start_node(run_id: str, payload: dict[str, object]) -> PlatformRunResult:
        concept_id = payload.get("concept_id")
        if not isinstance(concept_id, str) or not concept_id.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "invalid_start_node", "message": "concept_id is required"},
            )
        try:
            return service.start_node(run_id, concept_id.strip())
        except KeyError as exc:
            raise _run_not_found(run_id) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "invalid_start_node", "message": str(exc)},
            ) from exc

    return app


def _run_not_found(run_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "run_not_found",
            "message": f"platform run was not found: {run_id}",
        },
    )
