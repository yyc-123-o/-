import pytest

from skillforge_kb.platform.models import (
    PlatformRunRequest,
    PlatformRunResult,
    PlatformRunStatus,
    build_request_digest,
    build_run_id,
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
