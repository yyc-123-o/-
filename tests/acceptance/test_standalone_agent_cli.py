import json
from pathlib import Path

from typer.testing import CliRunner

from skillforge_kb.cli import app

runner = CliRunner()


def test_agent_run_writes_identical_output_file(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    result = runner.invoke(
        app,
        [
            "agent-run",
            "--event-file",
            "examples/agents/initialize_event.json",
            "--thread-id",
            "acceptance-demo",
            "--output-file",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "ready"
    assert output.read_text(encoding="utf-8") == result.stdout


def test_agent_run_rejects_output_overwriting_asset(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "agent-run",
            "--event-file",
            "examples/agents/initialize_event.json",
            "--thread-id",
            "invalid-output",
            "--output-file",
            "examples/agents/initialize_event.json",
        ],
    )

    assert result.exit_code != 0
    assert "must not overwrite" in result.output


def test_agent_run_rejects_invalid_event_without_traceback(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"profile_meta": {"profile_id": "legacy"}}), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "agent-run",
            "--event-file",
            str(invalid),
            "--thread-id",
            "invalid-event",
        ],
    )

    assert result.exit_code != 0
    assert "invalid planning event" in result.output
    assert "Traceback" not in result.output


def test_agent_run_validates_assets_before_creating_state_db(tmp_path: Path) -> None:
    invalid_course = tmp_path / "invalid-course.yaml"
    invalid_course.write_text("not: a-course-graph\n", encoding="utf-8")
    state_db = tmp_path / "state.sqlite3"

    result = runner.invoke(
        app,
        [
            "agent-run",
            "--event-file",
            "examples/agents/initialize_event.json",
            "--thread-id",
            "invalid-assets",
            "--course-file",
            str(invalid_course),
            "--state-db",
            str(state_db),
        ],
    )

    assert result.exit_code == 2
    assert not state_db.exists()


def test_agent_run_prints_failed_result_and_exits_three(tmp_path: Path) -> None:
    payload = json.loads(
        Path("examples/agents/initialize_event.json").read_text(encoding="utf-8")
    )
    payload["profile"]["graph_version"] = "ai-course-v2"
    event_file = tmp_path / "mismatched-graph.json"
    event_file.write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "agent-run",
            "--event-file",
            str(event_file),
            "--thread-id",
            "failed-result",
        ],
    )

    assert result.exit_code == 3
    output = json.loads(result.stdout)
    assert output["status"] == "failed"
    assert output["failure"]["code"] == "planning_error"
