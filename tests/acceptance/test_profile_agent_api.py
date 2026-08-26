import json
from pathlib import Path

from fastapi.testclient import TestClient

from skillforge_kb.api.app import create_app
from skillforge_kb.platform.runtime import (
    build_default_platform_service,
    build_default_profile_agent_adapter,
)


def _platform_app(root: Path, monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SKILLFORGE_PLATFORM_STATE_DB", str(tmp_path / "platform.sqlite3"))
    return create_app(
        build_default_platform_service(root),
        profile_adapter=build_default_profile_agent_adapter(root),
    )


def _raw_profile() -> dict[str, object]:
    return {
        "profile_id": "PROFILE-LEARNER_TEST_001",
        "profile_version": "2.1",
        "generated_at": "2026-08-19T10:00:00Z",
        "learner_id": "learner_test_001",
        "knowledge_mastery": {
            "points": {
                "kp_012": {
                    "name": "卷积神经网络CNN",
                    "mastery": 0.30,
                    "status": "weak",
                    "confidence": 0.9,
                }
            }
        },
        "learning_scope": {"scope_type": "chapter", "primary_kp_id": "kp_012"},
        "ability_level": {
            "sub_dimensions": {
                "coding_ability": {"score": 0.7, "confidence": 0.8},
            }
        },
        "learning_preferences": {
            "format": {"content_order": [], "framework": "PyTorch"},
            "pace": {"weekly_hours": 10},
        },
    }


def test_default_platform_adapts_cnn_profile_agent_output(monkeypatch, tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    app = _platform_app(root, monkeypatch, tmp_path)

    with TestClient(app) as client:
        response = client.post("/api/v1/profiles/adapt", json=_raw_profile())

    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot"]["graph_version"] == "ai-course-v1"
    assert payload["snapshot"]["knowledge_mastery"][0]["concept_id"] == (
        "dl.cnn.convolution"
    )
    assert payload["suggested_target_concept_id"] == "dl.cnn.convolution"
    assert any(
        "inferred" in warning["reason"] for warning in payload["warnings"]
    )


def test_default_platform_rejects_profile_graph_mismatch(monkeypatch, tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    app = _platform_app(root, monkeypatch, tmp_path)
    raw = _raw_profile()
    raw["graph_version"] = "ai-course-v2"

    with TestClient(app) as client:
        response = client.post("/api/v1/profiles/adapt", json=raw)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_profile_agent_output"


def test_adapted_profile_enters_platform_and_respects_evidence_gate(monkeypatch, tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    app = _platform_app(root, monkeypatch, tmp_path)

    with TestClient(app) as client:
        adaptation = client.post("/api/v1/profiles/adapt", json=_raw_profile())
        run = client.post(
            "/api/v1/runs",
            json={
                "profile": adaptation.json()["snapshot"],
                "idempotency_key": "profile-agent-acceptance",
                "execution_mode": "strict",
                "top_k": 5,
            },
        )

    assert adaptation.status_code == 200
    assert run.status_code == 201
    payload = run.json()
    assert payload["profile_id"] == "PROFILE-LEARNER_TEST_001"
    assert payload["status"] == "blocked"
    assert payload["planning"]["path"]["graph_version"] == "ai-course-v1"
    assert payload["handoff"]["concept_id"] == payload["retrieval"]["request"][
        "concept_id"
    ]
    assert payload["evidence_gap"]["missing_content_kinds"] == [
        "definition",
        "code",
        "exercise",
    ]


def test_target_concept_is_forwarded_to_planner(monkeypatch, tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    profile = json.loads(
        (root / "tests" / "fixtures" / "profile-2026-0001-demo.json").read_text(
            encoding="utf-8"
        )
    )
    profile["profile_id"] = "PROFILE-TARGET-TEST"
    monkeypatch.setenv("SKILLFORGE_PLATFORM_STATE_DB", str(tmp_path / "platform.sqlite3"))
    app = create_app(build_default_platform_service(root))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            json={
                "profile": profile,
                "target_concept_id": "dl.cnn.convolution",
                "idempotency_key": "target-concept-acceptance",
                "execution_mode": "candidate_preview",
                "top_k": 5,
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["planning"]["path"]["target_concept_id"] == "dl.cnn.convolution"
    assert payload["handoff"]["concept_id"] == "dl.cnn.convolution"
    assert len(payload["planning"]["path"]["nodes"]) == 140
    assert any(
        node["concept_id"] == "nlp.rnn"
        for node in payload["planning"]["path"]["nodes"]
    )
