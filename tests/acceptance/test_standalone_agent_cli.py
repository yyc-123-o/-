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
