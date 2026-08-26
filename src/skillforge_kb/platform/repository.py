from threading import RLock

from skillforge_kb.evaluation.knowledge_tracing import KnowledgeTracingObservation

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
        self._assessments: dict[tuple[str, str], tuple[str, PlatformRunResult]] = {}
        self._observations: dict[tuple[str, str], KnowledgeTracingObservation] = {}

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

    def update_request(self, run_id: str, request: PlatformRunRequest) -> None:
        request = PlatformRunRequest.model_validate(request.model_dump())
        digest = build_request_digest(request)
        with self._lock:
            existing = self._requests.get(run_id)
            if existing is None:
                raise KeyError(f"platform run not found: {run_id}")
            if (
                existing.profile.profile_id != request.profile.profile_id
                or existing.idempotency_key != request.idempotency_key
            ):
                raise ValueError("updated request must preserve run identity")
            self._requests[run_id] = request
            for key, (_, reserved_run_id) in self._reservations.items():
                if reserved_run_id == run_id:
                    self._reservations[key] = (digest, run_id)
                    break

    def get_assessment(
        self,
        run_id: str,
        assessment_id: str,
    ) -> tuple[str, PlatformRunResult] | None:
        with self._lock:
            return self._assessments.get((run_id, assessment_id))

    def save_assessment(
        self,
        run_id: str,
        assessment_id: str,
        submission_digest: str,
        result: PlatformRunResult,
    ) -> None:
        result = PlatformRunResult.model_validate(result.model_dump())
        with self._lock:
            if run_id not in self._requests:
                raise KeyError(f"platform run not found: {run_id}")
            key = (run_id, assessment_id)
            existing = self._assessments.get(key)
            if existing is not None and existing[0] != submission_digest:
                raise ValueError("assessment ID was already used with a different payload")
            self._assessments[key] = (submission_digest, result)

    def get_prediction_observation(
        self,
        run_id: str,
        assessment_id: str,
    ) -> KnowledgeTracingObservation | None:
        with self._lock:
            return self._observations.get((run_id, assessment_id))

    def save_prediction_observation(
        self,
        run_id: str,
        assessment_id: str,
        observation: KnowledgeTracingObservation,
    ) -> None:
        validated = KnowledgeTracingObservation.model_validate(observation.model_dump())
        with self._lock:
            request = self._requests.get(run_id)
            if request is None:
                raise KeyError(f"platform run not found: {run_id}")
            if validated.observation_id != assessment_id:
                raise ValueError("observation ID must match assessment ID")
            if validated.profile_id != request.profile.profile_id:
                raise ValueError("observation profile does not match platform run")
            key = (run_id, assessment_id)
            existing = self._observations.get(key)
            if existing is not None and existing != validated:
                raise ValueError("assessment has a different observation")
            self._observations[key] = validated

    def list_prediction_observations(
        self,
        run_id: str,
    ) -> tuple[KnowledgeTracingObservation, ...]:
        with self._lock:
            if run_id not in self._requests:
                raise KeyError(f"platform run not found: {run_id}")
            return tuple(
                observation
                for (stored_run_id, _), observation in self._observations.items()
                if stored_run_id == run_id
            )

    def list_prediction_observations_for_profile(
        self,
        profile_id: str,
        *,
        model_version: str | None = None,
    ) -> tuple[KnowledgeTracingObservation, ...]:
        with self._lock:
            observations: list[tuple[str, str, KnowledgeTracingObservation]] = []
            for run_id, request in self._requests.items():
                if request.profile.profile_id != profile_id:
                    continue
                for (stored_run_id, assessment_id), observation in self._observations.items():
                    if stored_run_id != run_id:
                        continue
                    if model_version is not None and observation.model_version != model_version:
                        continue
                    observations.append((run_id, assessment_id, observation))
            observations.sort(key=lambda item: (item[2].observed_at, item[0], item[1]))
            return tuple(item[2] for item in observations)
