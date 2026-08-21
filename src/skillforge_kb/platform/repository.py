from threading import RLock

from .models import (
    PlatformRunRequest,
    PlatformRunResult,
    build_request_digest,
    build_run_id,
)


class IdempotencyConflict(ValueError):
    pass


class InMemoryPlatformRunRepository:
    def __init__(self) -> None:
        self._lock = RLock()
        self._reservations: dict[tuple[str, str], tuple[str, str]] = {}
        self._results: dict[str, PlatformRunResult] = {}
        self._requests: dict[str, PlatformRunRequest] = {}

    def reserve(self, request: PlatformRunRequest) -> PlatformRunResult | None:
        request = PlatformRunRequest.model_validate(request.model_dump())
        key = (request.profile.profile_id, request.idempotency_key)
        digest = build_request_digest(request)
        run_id = build_run_id(request)
        with self._lock:
            existing = self._reservations.get(key)
            if existing is None:
                self._reservations[key] = (digest, run_id)
                self._requests[run_id] = request
                return None
            existing_digest, existing_run_id = existing
            if existing_digest != digest:
                raise IdempotencyConflict(
                    "idempotency key was already used with a different request"
                )
            return self._results.get(existing_run_id)

    def peek(self, request: PlatformRunRequest) -> PlatformRunResult | None:
        request = PlatformRunRequest.model_validate(request.model_dump())
        key = (request.profile.profile_id, request.idempotency_key)
        digest = build_request_digest(request)
        with self._lock:
            existing = self._reservations.get(key)
            if existing is None:
                return None
            existing_digest, run_id = existing
            if existing_digest != digest:
                raise IdempotencyConflict(
                    "idempotency key was already used with a different request"
                )
            return self._results.get(run_id)

    def save(self, result: PlatformRunResult) -> None:
        result = PlatformRunResult.model_validate(result.model_dump())
        with self._lock:
            reserved = any(
                digest == result.request_digest and run_id == result.run_id
                for digest, run_id in self._reservations.values()
            )
            if not reserved:
                raise ValueError("platform result does not match a reserved request")
            self._results[result.run_id] = result

    def get(self, run_id: str) -> PlatformRunResult | None:
        with self._lock:
            return self._results.get(run_id)

    def get_request(self, run_id: str) -> PlatformRunRequest | None:
        with self._lock:
            return self._requests.get(run_id)
