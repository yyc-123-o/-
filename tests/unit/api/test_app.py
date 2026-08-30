from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from skillforge_kb.api.app import create_app
from skillforge_kb.evaluation import (
    KnowledgeTracingObservation,
    evaluate_knowledge_tracing,
)
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.profile_agent_adapter import LearnerProfileAgentAdapter


def _request(profile_payload: dict[str, object], *, top_k: int = 5) -> dict[str, object]:
    return {
        "profile": profile_payload,
        "idempotency_key": "api-demo-1",
        "execution_mode": "strict",
        "top_k": top_k,
    }


def test_health_lists_enabled_execution_modes(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "execution_modes": ["strict", "candidate_preview"],
    }


def test_app_closes_service_when_test_client_exits() -> None:
    class ClosingService:
        closed = False

        def close(self) -> None:
            self.closed = True

    service = ClosingService()
    with TestClient(create_app(service)):  # type: ignore[arg-type]
        pass

    assert service.closed is True


def test_create_run_returns_201_and_structured_result(
    client: TestClient,
    profile_payload: dict[str, object],
) -> None:
    response = client.post("/api/v1/runs", json=_request(profile_payload))

    assert response.status_code == 201
    assert response.json()["status"] == "blocked"


def test_identical_replay_returns_200(
    client: TestClient,
    profile_payload: dict[str, object],
) -> None:
    payload = _request(profile_payload)

    assert client.post("/api/v1/runs", json=payload).status_code == 201
    assert client.post("/api/v1/runs", json=payload).status_code == 200


def test_idempotency_conflict_returns_409(
    client: TestClient,
    profile_payload: dict[str, object],
) -> None:
    assert client.post("/api/v1/runs", json=_request(profile_payload)).status_code == 201

    response = client.post("/api/v1/runs", json=_request(profile_payload, top_k=6))

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "idempotency_conflict"


def test_get_run_and_events(
    client: TestClient,
    profile_payload: dict[str, object],
) -> None:
    created = client.post("/api/v1/runs", json=_request(profile_payload)).json()
    run_id = created["run_id"]

    assert client.get(f"/api/v1/runs/{run_id}").json() == created
    assert client.get(f"/api/v1/runs/{run_id}/events").json() == []


def test_complete_node_requires_learning_progress_service(
    client: TestClient,
    profile_payload: dict[str, object],
) -> None:
    created = client.post("/api/v1/runs", json=_request(profile_payload)).json()
    response = client.post(
        f"/api/v1/runs/{created['run_id']}/complete-node",
        json={"concept_id": "math.linear-algebra.scalar"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "invalid_learning_transition"


def test_start_node_requires_learning_progress_service(
    client: TestClient,
    profile_payload: dict[str, object],
) -> None:
    created = client.post("/api/v1/runs", json=_request(profile_payload)).json()
    response = client.post(
        f"/api/v1/runs/{created['run_id']}/start-node",
        json={"concept_id": "math.linear-algebra.scalar"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "invalid_start_node"


def test_assessment_requires_learning_progress_service(
    client: TestClient,
    profile_payload: dict[str, object],
) -> None:
    created = client.post("/api/v1/runs", json=_request(profile_payload)).json()
    response = client.post(
        f"/api/v1/runs/{created['run_id']}/assessment",
        json={
            "assessment_id": "assessment-api-test",
            "concept_id": "math.linear-algebra.scalar",
            "score": 0.5,
            "response_time_ms": 1000,
            "hint_count": 0,
            "attempt_count": 1,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "invalid_assessment"


def test_refresh_resources_requires_learning_progress_service(
    client: TestClient,
    profile_payload: dict[str, object],
) -> None:
    created = client.post("/api/v1/runs", json=_request(profile_payload)).json()
    response = client.post(f"/api/v1/runs/{created['run_id']}/refresh-resources")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "invalid_resource_refresh"


def test_missing_run_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/runs/run_{'0' * 64}")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "run_not_found"


def test_invalid_request_returns_422(client: TestClient) -> None:
    response = client.post("/api/v1/runs", json={"top_k": 0})

    assert response.status_code == 422


def test_practice_review_returns_safe_feedback(client: TestClient, profile_payload) -> None:
    created = client.post("/api/v1/runs", json=_request(profile_payload)).json()

    response = client.post(
        f"/api/v1/runs/{created['run_id']}/practice-review",
        json={
            "concept_id": "math.linear-algebra.scalar",
            "source": "result = [1]\nprint(result)",
        },
    )

    assert response.status_code == 200
    assert response.json()["execution_performed"] is False


def test_student_resource_response_does_not_expose_teacher_answers(client: TestClient) -> None:
    response = client.get("/api/v1/runs/run_" + "0" * 64)
    assert response.status_code == 404


def test_openapi_contains_platform_contracts(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "PlatformRunRequest" in schema["components"]["schemas"]
    assert "PlatformRunResult" in schema["components"]["schemas"]


def test_knowledge_tracing_evaluation_returns_reports(
    client: TestClient,
    service,
    profile,
) -> None:
    service.evaluation_reports = (
        evaluate_knowledge_tracing(
            (
                KnowledgeTracingObservation(
                    observation_id="api-observation-1",
                    profile_id=profile.profile_id,
                    concept_id="ml.optimization.gradient-descent",
                    model_version="bkt.v1",
                    predicted_mastery=0.2,
                    correct=True,
                    observed_at=datetime(2026, 8, 26, tzinfo=UTC),
                ),
            )
        ),
    )

    response = client.get(
        f"/api/v1/profiles/{profile.profile_id}/knowledge-tracing/evaluation"
    )

    assert response.status_code == 200
    assert response.json()[0]["model_version"] == "bkt.v1"


def test_knowledge_tracing_evaluation_without_observations_returns_404(
    client: TestClient,
    profile,
) -> None:
    response = client.get(
        f"/api/v1/profiles/{profile.profile_id}/knowledge-tracing/evaluation"
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "knowledge_tracing_not_found"


def test_unexpected_runtime_failure_returns_503(profile_payload: dict[str, object]) -> None:
    class BrokenService:
        def peek(self, request):
            return None

        def run(self, request):
            raise RuntimeError("runtime unavailable")

        def get(self, run_id: str):
            return None

    with TestClient(create_app(BrokenService())) as broken_client:  # type: ignore[arg-type]
        response = broken_client.post("/api/v1/runs", json=_request(profile_payload))

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "platform_unavailable"


def test_profile_agent_output_can_be_adapted(client, service) -> None:
    root = Path(__file__).parents[3]
    catalog = OntologyCatalog.load(
        root / "resources" / "ontology" / "ai_course_v1.yaml",
        root / "resources" / "ontology" / "ai_relations_v1.yaml",
    )
    adapter = LearnerProfileAgentAdapter(
        catalog,
        mappings={"kp_012": "dl.cnn.convolution"},
    )
    raw = {
        "profile_id": "PROFILE-LEARNER_TEST_001",
        "profile_version": "2.1",
        "generated_at": "2026-08-19T10:00:00Z",
        "learner_id": "learner_test_001",
        "knowledge_mastery": {
            "points": {
                "kp_012": {
                    "mastery": 0.3,
                    "status": "weak",
                    "confidence": 0.9,
                }
            }
        },
        "learning_scope": {"primary_kp_id": "kp_012"},
    }

    app = create_app(service, profile_adapter=adapter)
    with TestClient(app) as adapted_client:
        response = adapted_client.post("/api/v1/profiles/adapt", json=raw)

    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot"]["profile_id"] == "PROFILE-LEARNER_TEST_001"
    assert payload["snapshot"]["knowledge_mastery"][0]["concept_id"] == "dl.cnn.convolution"
    assert payload["suggested_target_concept_id"] == "dl.cnn.convolution"
