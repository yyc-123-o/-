from pathlib import Path


FRONTEND_ROOT = Path(__file__).resolve().parent.parent / "frontend" / "web" / "src"


def test_diagnosis_flow_uses_current_api_and_routes_to_profile() -> None:
    api_client = (FRONTEND_ROOT / "api" / "diagnosis.ts").read_text(encoding="utf-8")
    assessment = (FRONTEND_ROOT / "views" / "DiagnosisAssessmentView.vue").read_text(
        encoding="utf-8"
    )
    basic = (FRONTEND_ROOT / "views" / "DiagnosisBasicView.vue").read_text(
        encoding="utf-8"
    )

    assert '"/api/learner/upload"' in api_client
    assert '"/diagnosis/api' not in api_client
    assert "/api/adaptive-test/apply/" in api_client
    assert "await diagnosis.finishAdaptive(); router.push(\"/profile\")" in assessment
    assert 'value: "基本了解"' in basic
    assert '@click="selectLevel(group.domain, item, level.value)"' in basic
