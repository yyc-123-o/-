import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


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
