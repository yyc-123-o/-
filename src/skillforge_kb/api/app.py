from typing import Protocol

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.responses import JSONResponse

from skillforge_kb.platform.models import (
    PlatformRunRequest,
    PlatformRunResult,
    PlatformStepRecord,
)
from skillforge_kb.platform.repository import IdempotencyConflict


class PlatformApplicationService(Protocol):
    def run(self, request: PlatformRunRequest) -> PlatformRunResult: ...

    def peek(self, request: PlatformRunRequest) -> PlatformRunResult | None: ...

    def get(self, run_id: str) -> PlatformRunResult | None: ...


def create_app(service: PlatformApplicationService) -> FastAPI:
    app = FastAPI(title="SkillForge Platform API", version="1.0.0")
    app.state.platform_service = service

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

    return app


def _run_not_found(run_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "run_not_found",
            "message": f"platform run was not found: {run_id}",
        },
    )
