from fastapi.testclient import TestClient

from skillforge_kb.api.app import create_app


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


def test_missing_run_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/runs/run_{'0' * 64}")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "run_not_found"


def test_invalid_request_returns_422(client: TestClient) -> None:
    response = client.post("/api/v1/runs", json={"top_k": 0})

    assert response.status_code == 422


def test_openapi_contains_platform_contracts(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "PlatformRunRequest" in schema["components"]["schemas"]
    assert "PlatformRunResult" in schema["components"]["schemas"]


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
