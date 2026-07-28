import json
from pathlib import Path

from typer.testing import CliRunner

from skillforge_kb import cli
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
    input_root = tmp_path / "input"
    input_root.mkdir()
    input_path = input_root / "pilot.jsonl"
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


def test_graph_coverage_rejects_an_output_inside_the_input_directory(tmp_path: Path) -> None:
    input_path = tmp_path / "pilot.jsonl"
    output_path = tmp_path / "reports" / "coverage.json"
    input_path.write_text("{}\n", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "graph-coverage",
            "--pilot-jsonl",
            str(input_path),
            "--output-file",
            str(output_path),
        ],
    )

    assert result.exit_code != 0
    assert "outside the pilot JSONL directory" in result.output


def test_graph_validate_reports_invalid_catalog_without_a_traceback(tmp_path: Path) -> None:
    invalid_course = tmp_path / "invalid-course.yaml"
    invalid_course.write_text("not: [valid", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "graph-validate",
            "--course-file",
            str(invalid_course),
        ],
    )

    assert result.exit_code != 0
    assert "invalid course graph" in result.output
    assert "Traceback" not in result.output


def test_graph_publish_rejects_an_invalid_catalog_before_opening_driver(
    tmp_path: Path,
    monkeypatch,
) -> None:
    invalid_course = tmp_path / "invalid-course.yaml"
    invalid_course.write_text("not: [valid", encoding="utf-8")
    opened = False

    def fail_if_called(*args, **kwargs):
        nonlocal opened
        opened = True
        raise AssertionError("Neo4j driver must not open for an invalid catalog")

    monkeypatch.setattr(cli.GraphDatabase, "driver", fail_if_called)

    result = CliRunner().invoke(
        app,
        [
            "graph-publish",
            "--course-file",
            str(invalid_course),
        ],
    )

    assert result.exit_code != 0
    assert not opened


def test_graph_publish_closes_driver_after_a_successful_publish(monkeypatch) -> None:
    class FakeDriver:
        closed = False

        def close(self) -> None:
            self.closed = True

    class FakeConceptGraph:
        def __init__(self, driver: FakeDriver) -> None:
            self._driver = driver

        def publish(self, catalog) -> None:
            return None

    driver = FakeDriver()
    monkeypatch.setattr(cli.GraphDatabase, "driver", lambda *args, **kwargs: driver)
    monkeypatch.setattr(cli, "Neo4jConceptGraph", FakeConceptGraph)

    result = CliRunner().invoke(app, ["graph-publish"])

    assert result.exit_code == 0
    assert driver.closed
