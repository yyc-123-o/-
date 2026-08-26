from datetime import UTC, datetime
from pathlib import Path

import pytest

from skillforge_kb.evaluation.knowledge_tracing import KnowledgeTracingObservation
from skillforge_kb.agents.resource_agent import ResourceGenerationAgent
from skillforge_kb.platform.models import (
    ExecutionMode,
    PlatformRunRequest,
    PlatformRunResult,
    PlatformRunStatus,
    build_request_digest,
    build_run_id,
)
from skillforge_kb.platform.repository import (
    IdempotencyConflict,
    InMemoryPlatformRunRepository,
    SqlitePlatformRunRepository,
)


def _observation(
    assessment_id: str = "assessment-1",
    probability: float = 0.2,
    model_version: str = "bkt.v1",
):
    return KnowledgeTracingObservation(
        observation_id=assessment_id,
        profile_id="PROFILE-2026-0001-DEMO",
        concept_id="ml.optimization.gradient-descent",
        model_version=model_version,
        predicted_mastery=probability,
        correct=True,
        observed_at=datetime(2026, 8, 26, tzinfo=UTC),
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


def test_repository_lists_profile_observations_across_runs_and_filters_model(profile) -> None:
    repository = InMemoryPlatformRunRepository()
    first = PlatformRunRequest(profile=profile, idempotency_key="aggregate-1")
    second = PlatformRunRequest(profile=profile, idempotency_key="aggregate-2")
    repository.reserve(first)
    repository.reserve(second)
    repository.save_prediction_observation(
        build_run_id(second),
        "b",
        _observation("b", 0.4, "bkt.v1"),
    )
    repository.save_prediction_observation(
        build_run_id(first),
        "a",
        _observation("a", 0.6, "rule.v1"),
    )

    observations = repository.list_prediction_observations_for_profile(profile.profile_id)

    assert tuple(item.observation_id for item in observations) == ("a", "b")
    assert repository.list_prediction_observations_for_profile(
        profile.profile_id,
        model_version="bkt.v1",
    )[0].observation_id == "b"


def test_sqlite_repository_restores_runs_and_observations_after_reopen(
    profile,
    tmp_path: Path,
) -> None:
    database = tmp_path / "platform.sqlite3"
    request = PlatformRunRequest(profile=profile, idempotency_key="persistent-run")
    result = _result(request)
    observation = _observation()

    first = SqlitePlatformRunRepository(database)
    assert first.reserve(request) is None
    first.save(result)
    first.save_prediction_observation(result.run_id, "assessment-1", observation)
    first.close()

    reopened = SqlitePlatformRunRepository(database)
    assert reopened.reserve(request) == result
    assert reopened.get_request(result.run_id) == request
    assert reopened.get_prediction_observation(result.run_id, "assessment-1") == observation
    reopened.close()


def test_sqlite_repository_rejects_idempotency_conflicts_after_reopen(
    profile,
    tmp_path: Path,
) -> None:
    database = tmp_path / "platform.sqlite3"
    request = PlatformRunRequest(profile=profile, idempotency_key="persistent-conflict")
    repository = SqlitePlatformRunRepository(database)
    repository.reserve(request)
    repository.close()

    reopened = SqlitePlatformRunRepository(database)
    with pytest.raises(IdempotencyConflict, match="idempotency key"):
        reopened.reserve(request.model_copy(update={"top_k": request.top_k + 1}))
    reopened.close()


def test_sqlite_repository_restores_private_preview_fields_for_server_replay(
    profile,
    platform_case,
    tmp_path: Path,
) -> None:
    database = tmp_path / "platform.sqlite3"
    request = PlatformRunRequest(
        profile=profile,
        idempotency_key="preview-persistence",
        execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
    )
    resource = ResourceGenerationAgent().generate_preview(
        profile,
        platform_case["handoff"],
        platform_case["retrieval"],
    )
    result = PlatformRunResult(
        run_id=build_run_id(request),
        request_digest=build_request_digest(request),
        profile_id=profile.profile_id,
        status=PlatformRunStatus.COMPLETED,
        planning=platform_case["planning"],
        handoff=platform_case["handoff"],
        retrieval=platform_case["retrieval"],
        resources=resource,
    )

    repository = SqlitePlatformRunRepository(database)
    repository.reserve(request)
    repository.save(result)
    repository.close()

    reopened = SqlitePlatformRunRepository(database)
    restored = reopened.get(result.run_id)
    assert restored is not None
    assert restored.resources is not None
    assert restored.resources.preview_package is not None
    assert restored.resources.preview_package.draft.teacher_guide.items
    reopened.close()
