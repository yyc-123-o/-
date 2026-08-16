import json
from pathlib import Path

from typer.testing import CliRunner

from skillforge_kb.cli import app
from skillforge_kb.evaluation import (
    PathEvaluationReport,
    PlannerPolicyCalibrationReport,
    SyntheticPlanningDataset,
)
from skillforge_kb.ingestion.normalize import sha256_text

runner = CliRunner()


def test_agent_run_prints_json() -> None:
    result = runner.invoke(
        app,
        [
            "agent-run",
            "--event-file",
            "examples/agents/initialize_event.json",
            "--thread-id",
            "cli-demo",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready"
    assert payload["current_node"] is not None


def test_platform_serve_builds_service_and_starts_uvicorn(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {}
    service = object()
    application = object()

    monkeypatch.setattr(
        "skillforge_kb.cli.build_default_platform_service",
        lambda root: calls.update(project_root=root) or service,
    )
    monkeypatch.setattr(
        "skillforge_kb.cli.create_app",
        lambda value: calls.update(service=value) or application,
    )
    monkeypatch.setattr(
        "skillforge_kb.cli.uvicorn.run",
        lambda app, **kwargs: calls.update(app=app, **kwargs),
    )

    result = runner.invoke(
        app,
        [
            "platform-serve",
            "--project-root",
            str(tmp_path),
            "--host",
            "127.0.0.1",
            "--port",
            "8123",
        ],
    )

    assert result.exit_code == 0
    assert calls == {
        "project_root": tmp_path,
        "service": service,
        "app": application,
        "host": "127.0.0.1",
        "port": 8123,
    }


def test_agent_run_persists_duplicate_event(tmp_path: Path) -> None:
    state_db = tmp_path / "agent.sqlite3"
    args = [
        "agent-run",
        "--event-file",
        "examples/agents/initialize_event.json",
        "--thread-id",
        "sqlite-demo",
        "--state-db",
        str(state_db),
    ]

    first = runner.invoke(app, args)
    second = runner.invoke(app, args)

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert json.loads(second.stdout)["event_duplicate"] is True


def test_fusion_dry_run_cli_writes_summary(tmp_path: Path) -> None:
    knowledge = tmp_path / "knowledge"
    processed = tmp_path / "processed"
    output = tmp_path / "output"
    knowledge.mkdir()
    processed.mkdir()
    source = knowledge / "source.pdf"
    source.write_bytes(b"source")
    text = "梯度下降沿损失函数下降方向更新模型参数。"
    pilot_row = {
        "chunk_id": "pilot-1",
        "source_id": "source-1",
        "source_title": "Optimization Notes",
        "source_path": "knowledge/source.pdf",
        "source_url": "https://example.edu/optimization",
        "language": "zh",
        "text": text,
        "content_hash": sha256_text(text),
        "locator": "page 1",
        "concept_ids": ["ml.optimization.gradient_descent"],
        "content_kind": "definition",
        "difficulty": 2,
        "license": "MIT",
        "review_status": "candidate",
    }
    pilot = knowledge / "pilot.jsonl"
    pilot.write_text(json.dumps(pilot_row, ensure_ascii=False) + "\n", encoding="utf-8")
    legacy = processed / "index_chunks.jsonl"
    legacy.write_text("", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "fusion-dry-run",
            "--knowledge-root",
            str(knowledge),
            "--legacy-root",
            str(processed),
            "--pilot-jsonl",
            str(pilot),
            "--legacy-jsonl",
            str(legacy),
            "--workspace-root",
            str(tmp_path),
            "--output-dir",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert "Processed 1 rows" in result.stdout
    summary = json.loads((output / "fusion_summary.json").read_text(encoding="utf-8"))
    assert summary["input_rows"] == 1


def test_planning_commands_generate_and_evaluate(tmp_path: Path) -> None:
    dataset_path = tmp_path / "synthetic.json"
    report_path = tmp_path / "report.json"

    generated = runner.invoke(
        app,
        [
            "planning-generate-synthetic",
            "--output-file",
            str(dataset_path),
            "--case-count",
            "8",
        ],
    )
    evaluated = runner.invoke(
        app,
        [
            "planning-evaluate",
            "--dataset-file",
            str(dataset_path),
            "--output-file",
            str(report_path),
        ],
    )

    assert generated.exit_code == 0
    assert evaluated.exit_code == 0
    dataset = SyntheticPlanningDataset.model_validate_json(
        dataset_path.read_text(encoding="utf-8")
    )
    report = PathEvaluationReport.model_validate_json(
        report_path.read_text(encoding="utf-8")
    )
    assert len(dataset.cases) == 8
    assert report.metrics.hard_prerequisite_violation_rate == 0.0


def test_planning_generation_defaults_to_sixty_cases(tmp_path: Path) -> None:
    output = tmp_path / "synthetic.json"

    result = runner.invoke(
        app,
        ["planning-generate-synthetic", "--output-file", str(output)],
    )

    assert result.exit_code == 0
    dataset = SyntheticPlanningDataset.model_validate_json(
        output.read_text(encoding="utf-8")
    )
    assert len(dataset.cases) == 60


def test_planning_evaluation_rejects_output_overwriting_dataset(tmp_path: Path) -> None:
    dataset_path = tmp_path / "synthetic.json"
    generated = runner.invoke(
        app,
        [
            "planning-generate-synthetic",
            "--output-file",
            str(dataset_path),
            "--case-count",
            "8",
        ],
    )
    assert generated.exit_code == 0

    result = runner.invoke(
        app,
        [
            "planning-evaluate",
            "--dataset-file",
            str(dataset_path),
            "--output-file",
            str(dataset_path),
        ],
    )

    assert result.exit_code != 0
    assert "must not overwrite" in result.output


def test_planning_evaluation_reports_invalid_dataset_without_traceback(
    tmp_path: Path,
) -> None:
    dataset_path = tmp_path / "invalid.json"
    report_path = tmp_path / "report.json"
    dataset_path.write_text("{}", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "planning-evaluate",
            "--dataset-file",
            str(dataset_path),
            "--output-file",
            str(report_path),
        ],
    )

    assert result.exit_code != 0
    assert "invalid synthetic dataset" in result.output
    assert "Traceback" not in result.output


def test_planning_policy_calibration_writes_ranked_report(tmp_path: Path) -> None:
    dataset_path = tmp_path / "synthetic.json"
    report_path = tmp_path / "calibration.json"
    generated = runner.invoke(
        app,
        [
            "planning-generate-synthetic",
            "--output-file",
            str(dataset_path),
            "--case-count",
            "8",
        ],
    )
    assert generated.exit_code == 0

    result = runner.invoke(
        app,
        [
            "planning-calibrate-policy",
            "--dataset-file",
            str(dataset_path),
            "--output-file",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    report = PlannerPolicyCalibrationReport.model_validate_json(
        report_path.read_text(encoding="utf-8")
    )
    assert report.ranked_candidates
    assert report.data_kind == "synthetic"
    assert all(not item.invariant_failure_case_ids for item in report.ranked_candidates)


def test_planning_policy_calibration_rejects_output_overwriting_dataset(
    tmp_path: Path,
) -> None:
    dataset_path = tmp_path / "synthetic.json"
    generated = runner.invoke(
        app,
        [
            "planning-generate-synthetic",
            "--output-file",
            str(dataset_path),
            "--case-count",
            "8",
        ],
    )
    assert generated.exit_code == 0

    result = runner.invoke(
        app,
        [
            "planning-calibrate-policy",
            "--dataset-file",
            str(dataset_path),
            "--output-file",
            str(dataset_path),
        ],
    )

    assert result.exit_code != 0
    assert "must not overwrite" in result.output
