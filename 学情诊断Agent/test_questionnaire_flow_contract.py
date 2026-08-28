from pathlib import Path


def test_diagnosis_console_hands_off_final_profile_to_platform() -> None:
    root = (
        Path(__file__).resolve().parent.parent / "frontend" / "diagnosis" / "index.html"
    ).read_text(encoding="utf-8")
    script = (
        Path(__file__).resolve().parent.parent
        / "frontend"
        / "diagnosis"
        / "assets"
        / "scripts"
        / "app.js"
    ).read_text(encoding="utf-8")
    html = root + script

    assert "skillforge.pendingProfile.v1" in html
    assert "/api/learner/" in html and "/profile" in html
    assert "/platform?from=diagnosis" in html
    assert "created_at:Date.now()" in html
