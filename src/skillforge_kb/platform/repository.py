import json
import sqlite3
from pathlib import Path
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


def _internal_json(value: object) -> str:
    """Persist complete server state without invoking public response serializers."""
    model_dump = getattr(value, "model_dump", None)
    payload = model_dump(mode="python") if callable(model_dump) else value
    return json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))


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


class SqlitePlatformRunRepository:
    """Durable platform repository with the same contract as the in-memory store."""

    def __init__(self, database: str | Path) -> None:
        path = Path(database).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS reservations (
                profile_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                digest TEXT NOT NULL,
                run_id TEXT NOT NULL,
                PRIMARY KEY (profile_id, idempotency_key)
            );
            CREATE TABLE IF NOT EXISTS requests (
                run_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS results (
                run_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS assessments (
                run_id TEXT NOT NULL,
                assessment_id TEXT NOT NULL,
                digest TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (run_id, assessment_id)
            );
            CREATE TABLE IF NOT EXISTS observations (
                run_id TEXT NOT NULL,
                assessment_id TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                model_version TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (run_id, assessment_id)
            );
            """
        )
        self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _request(self, run_id: str) -> PlatformRunRequest | None:
        row = self._connection.execute(
            "SELECT payload FROM requests WHERE run_id = ?", (run_id,)
        ).fetchone()
        return PlatformRunRequest.model_validate_json(row["payload"]) if row else None

    def _result(self, run_id: str) -> PlatformRunResult | None:
        row = self._connection.execute(
            "SELECT payload FROM results WHERE run_id = ?", (run_id,)
        ).fetchone()
        return PlatformRunResult.model_validate_json(row["payload"]) if row else None

    def reserve(self, request: PlatformRunRequest) -> PlatformRunResult | None:
        request = PlatformRunRequest.model_validate(request.model_dump())
        key = (request.profile.profile_id, request.idempotency_key)
        digest = build_request_digest(request)
        run_id = build_run_id(request)
        payload = _internal_json(request)
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT digest, run_id FROM reservations WHERE profile_id = ? AND idempotency_key = ?",
                key,
            ).fetchone()
            if row is None:
                self._connection.execute(
                    "INSERT INTO reservations(profile_id, idempotency_key, digest, run_id) VALUES (?, ?, ?, ?)",
                    (*key, digest, run_id),
                )
                self._connection.execute(
                    "INSERT INTO requests(run_id, payload) VALUES (?, ?)",
                    (run_id, payload),
                )
                return None
            if row["digest"] != digest:
                raise IdempotencyConflict(
                    "idempotency key was already used with a different request"
                )
            return self._result(row["run_id"])

    def peek(self, request: PlatformRunRequest) -> PlatformRunResult | None:
        request = PlatformRunRequest.model_validate(request.model_dump())
        digest = build_request_digest(request)
        with self._lock:
            row = self._connection.execute(
                "SELECT digest, run_id FROM reservations WHERE profile_id = ? AND idempotency_key = ?",
                (request.profile.profile_id, request.idempotency_key),
            ).fetchone()
            if row is None:
                return None
            if row["digest"] != digest:
                raise IdempotencyConflict(
                    "idempotency key was already used with a different request"
                )
            return self._result(row["run_id"])

    def save(self, result: PlatformRunResult) -> None:
        result = PlatformRunResult.model_validate(result.model_dump())
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT 1 FROM reservations WHERE run_id = ? AND digest = ?",
                (result.run_id, result.request_digest),
            ).fetchone()
            if row is None:
                raise ValueError("platform result does not match a reserved request")
            self._connection.execute(
                "INSERT INTO results(run_id, payload) VALUES (?, ?) ON CONFLICT(run_id) DO UPDATE SET payload=excluded.payload",
                (result.run_id, _internal_json(result)),
            )

    def get(self, run_id: str) -> PlatformRunResult | None:
        with self._lock:
            return self._result(run_id)

    def get_request(self, run_id: str) -> PlatformRunRequest | None:
        with self._lock:
            return self._request(run_id)

    def update_request(self, run_id: str, request: PlatformRunRequest) -> None:
        request = PlatformRunRequest.model_validate(request.model_dump())
        digest = build_request_digest(request)
        with self._lock, self._connection:
            existing = self._request(run_id)
            if existing is None:
                raise KeyError(f"platform run not found: {run_id}")
            if (
                existing.profile.profile_id != request.profile.profile_id
                or existing.idempotency_key != request.idempotency_key
            ):
                raise ValueError("updated request must preserve run identity")
            self._connection.execute(
                "UPDATE requests SET payload = ? WHERE run_id = ?",
                (_internal_json(request), run_id),
            )
            self._connection.execute(
                "UPDATE reservations SET digest = ? WHERE run_id = ?",
                (digest, run_id),
            )

    def get_assessment(self, run_id: str, assessment_id: str) -> tuple[str, PlatformRunResult] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT digest, payload FROM assessments WHERE run_id = ? AND assessment_id = ?",
                (run_id, assessment_id),
            ).fetchone()
            return (row["digest"], PlatformRunResult.model_validate_json(row["payload"])) if row else None

    def save_assessment(self, run_id: str, assessment_id: str, submission_digest: str, result: PlatformRunResult) -> None:
        result = PlatformRunResult.model_validate(result.model_dump())
        with self._lock, self._connection:
            if self._request(run_id) is None:
                raise KeyError(f"platform run not found: {run_id}")
            row = self._connection.execute(
                "SELECT digest FROM assessments WHERE run_id = ? AND assessment_id = ?",
                (run_id, assessment_id),
            ).fetchone()
            if row is not None and row["digest"] != submission_digest:
                raise ValueError("assessment ID was already used with a different payload")
            self._connection.execute(
                "INSERT INTO assessments(run_id, assessment_id, digest, payload) VALUES (?, ?, ?, ?) ON CONFLICT(run_id, assessment_id) DO UPDATE SET digest=excluded.digest, payload=excluded.payload",
                (run_id, assessment_id, submission_digest, _internal_json(result)),
            )

    def get_prediction_observation(self, run_id: str, assessment_id: str) -> KnowledgeTracingObservation | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload FROM observations WHERE run_id = ? AND assessment_id = ?",
                (run_id, assessment_id),
            ).fetchone()
            return KnowledgeTracingObservation.model_validate_json(row["payload"]) if row else None

    def save_prediction_observation(self, run_id: str, assessment_id: str, observation: KnowledgeTracingObservation) -> None:
        validated = KnowledgeTracingObservation.model_validate(observation.model_dump())
        with self._lock, self._connection:
            request = self._request(run_id)
            if request is None:
                raise KeyError(f"platform run not found: {run_id}")
            if validated.observation_id != assessment_id:
                raise ValueError("observation ID must match assessment ID")
            if validated.profile_id != request.profile.profile_id:
                raise ValueError("observation profile does not match platform run")
            existing = self.get_prediction_observation(run_id, assessment_id)
            if existing is not None and existing != validated:
                raise ValueError("assessment has a different observation")
            self._connection.execute(
                "INSERT INTO observations(run_id, assessment_id, profile_id, model_version, observed_at, payload) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(run_id, assessment_id) DO UPDATE SET payload=excluded.payload",
                (run_id, assessment_id, validated.profile_id, validated.model_version, validated.observed_at.isoformat(), validated.model_dump_json()),
            )

    def list_prediction_observations(self, run_id: str) -> tuple[KnowledgeTracingObservation, ...]:
        with self._lock:
            if self._request(run_id) is None:
                raise KeyError(f"platform run not found: {run_id}")
            rows = self._connection.execute(
                "SELECT payload FROM observations WHERE run_id = ? ORDER BY observed_at, assessment_id",
                (run_id,),
            ).fetchall()
            return tuple(KnowledgeTracingObservation.model_validate_json(row["payload"]) for row in rows)

    def list_prediction_observations_for_profile(self, profile_id: str, *, model_version: str | None = None) -> tuple[KnowledgeTracingObservation, ...]:
        with self._lock:
            query = "SELECT payload FROM observations WHERE profile_id = ?"
            params: list[str] = [profile_id]
            if model_version is not None:
                query += " AND model_version = ?"
                params.append(model_version)
            query += " ORDER BY observed_at, run_id, assessment_id"
            rows = self._connection.execute(query, params).fetchall()
            return tuple(KnowledgeTracingObservation.model_validate_json(row["payload"]) for row in rows)
