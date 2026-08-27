from pathlib import Path


def test_diagnosis_console_hands_off_final_profile_to_platform() -> None:
    html = (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")

    assert "skillforge.pendingProfile.v1" in html
    assert "/api/learner/" in html and "/profile" in html
    assert "/platform?from=diagnosis" in html
    assert "created_at:Date.now()" in html
