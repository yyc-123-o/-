from datetime import UTC, datetime

import pytest

from skillforge_kb.evaluation.knowledge_tracing import KnowledgeTracingObservation

from skillforge_kb.platform.models import (
    PlatformRunRequest,
    PlatformRunResult,
    PlatformRunStatus,
    build_request_digest,
    build_run_id,
)


def _observation(assessment_id: str = "assessment-1", probability: float = 0.2):
    return KnowledgeTracingObservation(
        observation_id=assessment_id,
        profile_id="PROFILE-2026-0001-DEMO",
        concept_id="ml.optimization.gradient-descent",
        model_version="bkt.v1",
        predicted_mastery=probability,
        correct=True,
        observed_at=datetime(2026, 8, 26, tzinfo=UTC),
    )
from skillforge_kb.platform.repository import (
    IdempotencyConflict,
    InMemoryPlatformRunRepository,
)


def _result(request: PlatformRunRequest) -> PlatformRunResult:
    return PlatformRunResult(
        run_id=build_run_id(request),
        request_digest=build_request_digest(request),
        profile_id=request.profile.profile_id,
        status=PlatformRunStatus.PENDING,
    )


def test_repository_replays_identical_request(profile) -> None:
    repository = InMemoryPlatformRunRepository()
    request = PlatformRunRequest(profile=profile, idempotency_key="same-run")
    result = _result(request)

    assert repository.reserve(request) is None
    repository.save(result)

    assert repository.reserve(request) == result
    assert repository.peek(request) == result
    assert repository.get(result.run_id) == result
    assert repository.get_request(result.run_id) == request


def test_repository_rejects_key_reuse_with_different_payload(profile) -> None:
    repository = InMemoryPlatformRunRepository()
    request = PlatformRunRequest(profile=profile, idempotency_key="conflict-run")
    repository.reserve(request)
    changed = request.model_copy(update={"top_k": request.top_k + 1})

    with pytest.raises(IdempotencyConflict, match="idempotency key"):
        repository.reserve(changed)


def test_repository_rejects_result_for_unknown_reservation(profile) -> None:
    repository = InMemoryPlatformRunRepository()
    request = PlatformRunRequest(profile=profile, idempotency_key="not-reserved")

    with pytest.raises(ValueError, match="reserved"):
        repository.save(_result(request))


def test_repository_stores_and_lists_observations(profile) -> None:
    repository = InMemoryPlatformRunRepository()
    request = PlatformRunRequest(profile=profile, idempotency_key="observation-run")
    repository.reserve(request)
    run_id = build_run_id(request)
    observation = _observation()

    repository.save_prediction_observation(run_id, "assessment-1", observation)

    assert repository.get_prediction_observation(run_id, "assessment-1") == observation
    assert repository.list_prediction_observations(run_id) == (observation,)


def test_repository_rejects_observation_conflicts(profile) -> None:
    repository = InMemoryPlatformRunRepository()
    request = PlatformRunRequest(profile=profile, idempotency_key="observation-conflict")
    repository.reserve(request)
    run_id = build_run_id(request)
    repository.save_prediction_observation(run_id, "assessment-1", _observation())

    with pytest.raises(ValueError, match="different observation"):
        repository.save_prediction_observation(
            run_id,
            "assessment-1",
            _observation(probability=0.8),
        )
