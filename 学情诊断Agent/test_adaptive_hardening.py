import pytest
from fastapi.testclient import TestClient

from core import adaptive_test
from main import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_adaptive_answer_rejects_negative_time_without_mutating_session(client: TestClient) -> None:
    started = client.post("/api/adaptive-test/start/learner_001").json()
    question = started["next_question"]

    response = client.post(
        "/api/adaptive-test/answer",
        json={
            "session_id": started["session_id"],
            "question_id": question["question_id"],
            "selected_answer": 0,
            "time_spent": -1,
        },
    )

    assert response.status_code == 422
    session = client.get(f"/api/adaptive-test/session/{started['session_id']}").json()
    assert session["question_count"] == 0


def test_adaptive_start_rejects_malformed_stage_without_server_error(client: TestClient) -> None:
    response = client.post(
        "/api/adaptive-test/start/learner_001",
        json={"difficulty_stages": ["bad"]},
    )

    assert response.status_code == 422


def test_submit_answer_rejects_negative_time_at_core_boundary() -> None:
    adaptive_test._sessions.clear()
    bank = [
        {
            "question_id": "q-1",
            "knowledge_point_id": "kp-1",
            "difficulty": 0.0,
            "discrimination": 1.0,
            "options": ["a", "b"],
            "correct_answer": 0,
        }
    ]
    started = adaptive_test.start_session("learner", 0.0, bank)

    result = adaptive_test.submit_answer(
        started["session_id"],
        "q-1",
        0,
        -1,
        bank,
    )

    assert result["error"] == "time_spent 必须是非负整数"


def test_get_session_preserves_zero_final_theta() -> None:
    adaptive_test._sessions.clear()
    session = adaptive_test.AdaptiveSession(
        session_id="sess-zero",
        learner_id="learner",
        started_at="2026-08-26T00:00:00",
        finished=True,
        final_theta=0.0,
        stop_reason="completed",
    )
    adaptive_test._sessions[session.session_id] = session

    result = adaptive_test.get_session(session.session_id)

    assert result is not None
    assert result["final_theta"] == 0.0


def test_build_config_rejects_non_mapping_input() -> None:
    with pytest.raises(ValueError, match="对象"):
        adaptive_test.build_config([])


@pytest.mark.parametrize(
    "payload",
    [
        {"domains": "数学基础"},
        {"knowledge_point_ids": "kp_001"},
        {"convergence_threshold": float("nan")},
        {"difficulty_stages": [{"low": float("inf"), "high": 1.0}]},
    ],
)
def test_build_config_rejects_invalid_filter_and_nonfinite_values(payload: dict) -> None:
    with pytest.raises(ValueError):
        adaptive_test.build_config(payload)


def test_adaptive_answer_rejects_missing_session_fields_as_422(client: TestClient) -> None:
    response = client.post("/api/adaptive-test/answer", json={"selected_answer": 0})

    assert response.status_code == 422
