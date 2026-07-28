import json
from pathlib import Path


def test_validation_report_is_structural_only() -> None:
    path = Path(__file__).parents[3] / "docs" / "reports" / "course-graph-v1-validation.json"
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["chapter_count"] == 11
    assert report["concept_count"] == 140
    assert report["concept_level_count"] == 420
    assert report["hard_prerequisite_cycles"] == 0
    assert "learner_id" not in json.dumps(report)
