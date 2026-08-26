import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_app_uses_lifespan_instead_of_deprecated_startup_event() -> None:
    assert app.router.on_startup == []


def test_upload_rejects_non_array_records_without_server_error(client: TestClient) -> None:
    payload = {
        "education": {"level": "\u672c\u79d1"},
        "test_records": {"bad": 1},
        "interaction_records": [],
    }

    response = client.post("/api/learner/upload", json=payload)

    assert response.status_code == 422


def test_upload_rejects_non_array_self_assessment_collections(client: TestClient) -> None:
    payload = {
        "education": {"level": "\u672c\u79d1"},
        "self_assessment": {"courses": {"bad": 1}},
    }

    response = client.post("/api/learner/upload", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    [("courses", [1]), ("projects", [1]), ("domain_assessments", [1])],
)
def test_upload_rejects_non_object_self_assessment_items(
    client: TestClient,
    field: str,
    value: list[object],
) -> None:
    payload = {
        "education": {"level": "\u672c\u79d1"},
        "self_assessment": {field: value},
    }

    response = client.post("/api/learner/upload", json=payload)

    assert response.status_code == 422


def test_profile_rejects_unknown_chapter_like_diagnose(client: TestClient) -> None:
    response = client.get(
        "/api/learner/learner_001/profile?chapter_id=does-not-exist"
    )

    assert response.status_code == 400


@pytest.mark.parametrize(
    "education_patch",
    [{"graduation_year": "bad"}, {"gpa": "bad"}, {"relevant_courses": {}}],
)
def test_upload_converts_nested_model_validation_to_422(
    client: TestClient,
    education_patch: dict[str, object],
) -> None:
    education = {"level": "\u672c\u79d1", **education_patch}

    response = client.post("/api/learner/upload", json={"education": education})

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("record_group", "record"),
    [
        ("test_records", {"knowledge_point_id": "kp_001", "is_correct": True, "time_spent": "60"}),
        ("test_records", {"knowledge_point_id": "kp_001", "is_correct": True, "discrimination": True}),
        ("interaction_records", {"knowledge_point_id": "kp_001", "duration": "60"}),
    ],
)
def test_upload_rejects_invalid_numeric_record_values_as_422(
    client: TestClient,
    record_group: str,
    record: dict[str, object],
) -> None:
    payload = {
        "education": {"level": "本科"},
        "test_records": [record] if record_group == "test_records" else [],
        "interaction_records": [record] if record_group == "interaction_records" else [],
    }

    response = client.post("/api/learner/upload", json=payload)

    assert response.status_code == 422


def test_upload_preserves_historical_record_timestamps(client: TestClient) -> None:
    payload = {
        "id": "timestamp-regression",
        "education": {"level": "本科"},
        "test_records": [
            {
                "knowledge_point_id": "kp_001",
                "is_correct": True,
                "timestamp": "2026-01-02T03:04:05",
            }
        ],
        "interaction_records": [
            {
                "knowledge_point_id": "kp_001",
                "type": "view",
                "timestamp": "2026-01-03T04:05:06",
            }
        ],
    }

    response = client.post("/api/learner/upload", json=payload)

    assert response.status_code == 200
    learner = client.get("/api/learner/timestamp-regression").json()
    assert learner["test_records"][0]["timestamp"].startswith("2026-01-02T03:04:05")
    assert learner["interaction_records"][0]["timestamp"].startswith("2026-01-03T04:05:06")


def test_upload_rejects_existing_learner_id_to_preserve_session_ownership(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/learner/upload",
        json={
            "id": "learner_001",
            "name": "覆盖者",
            "education": {"level": "本科"},
        },
    )

    assert response.status_code == 409
    assert client.get("/api/learner/learner_001").json()["name"] == "张小明"
