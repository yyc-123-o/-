import json
from pathlib import Path

from typer.testing import CliRunner

from skillforge_kb.cli import app

RESOURCE_ROOT = Path(__file__).parents[3] / "resources" / "ontology"


def test_graph_validate_reports_catalog_scale() -> None:
    result = CliRunner().invoke(
        app,
        [
            "graph-validate",
            "--course-file",
            str(RESOURCE_ROOT / "ai_course_v1.yaml"),
            "--relations-file",
            str(RESOURCE_ROOT / "ai_relations_v1.yaml"),
        ],
    )

    assert result.exit_code == 0
    assert "11 chapters" in result.stdout
    assert "140 concepts" in result.stdout


def test_graph_validate_writes_report(tmp_path: Path) -> None:
    output_path = tmp_path / "validation.json"

    result = CliRunner().invoke(
        app,
        [
            "graph-validate",
            "--course-file",
            str(RESOURCE_ROOT / "ai_course_v1.yaml"),
            "--relations-file",
            str(RESOURCE_ROOT / "ai_relations_v1.yaml"),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["concept_count"] == 140
    assert report["section_count"] == 27


def test_graph_coverage_writes_read_only_candidate_report(tmp_path: Path) -> None:
    input_path = tmp_path / "pilot.jsonl"
    output_path = tmp_path / "reports" / "coverage.json"
    input_path.write_text(
        json.dumps({"concept_ids": ["ml.optimization.gradient-descent"]}) + "\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "graph-coverage",
            "--course-file",
            str(RESOURCE_ROOT / "ai_course_v1.yaml"),
            "--relations-file",
            str(RESOURCE_ROOT / "ai_relations_v1.yaml"),
            "--pilot-jsonl",
            str(input_path),
            "--output-file",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["candidate_counts"]["ml.optimization.gradient-descent"] == 1
    assert report["published_concept_ids"] == []
