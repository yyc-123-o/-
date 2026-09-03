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
    profile_adapter = object()
    application = object()

    monkeypatch.setattr(
        "skillforge_kb.cli.build_default_platform_service",
        lambda root: calls.update(project_root=root) or service,
    )
    monkeypatch.setattr(
        "skillforge_kb.cli.build_default_profile_agent_adapter",
        lambda root: calls.update(adapter_project_root=root) or profile_adapter,
    )
    monkeypatch.setattr(
        "skillforge_kb.cli.create_app",
        lambda value, profile_adapter: calls.update(
            service=value,
            profile_adapter=profile_adapter,
        ) or application,
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
        "adapter_project_root": tmp_path,
        "service": service,
        "profile_adapter": profile_adapter,
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


def test_persona_pipeline_run_cli(tmp_path: Path) -> None:
    output_path = tmp_path / "snapshot.json"

    result = runner.invoke(
        app,
        [
            "persona-pipeline-run",
            "--profile-file",
            "tests/fixtures/profile-2026-0001-demo.json",
            "--output-file",
            str(output_path),
            "--project-root",
            ".",
        ],
    )

    assert result.exit_code == 0
    assert "140 path nodes" in result.output

    # A full ``PersonaPipelineSnapshot.model_validate_json`` round trip is not
    # guaranteed here: candidate-preview resource results deliberately strip
    # teacher-only content (``teacher_guide``/``correct_choice``) in JSON mode
    # (see ``ResourceAgentResult.serialize_public``), and with this repo's
    # empty tracked evidence manifest most nodes take that branch. Validate
    # the persisted file generically instead.
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["pipeline_failure"] is None
    assert len(payload["full_path"]) == 140
    assert payload["personalized_path_concept_ids"]


def test_persona_pipeline_run_cli_feedback_loop(tmp_path: Path) -> None:
    output_path = tmp_path / "feedback-snapshot.json"

    result = runner.invoke(
        app,
        [
            "persona-pipeline-run",
            "--profile-file",
            "tests/fixtures/profile-2026-0001-demo.json",
            "--output-file",
            str(output_path),
            "--project-root",
            ".",
            "--feedback-loop",
            "--max-rounds",
            "2",
        ],
    )

    assert result.exit_code == 0
    assert "2 feedback rounds" in result.output

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["pipeline_failure"] is None
    assert len(payload["feedback_rounds"]) == 2
    completed = [node for node in payload["full_path"] if node["status"] == "completed"]
    assert len(completed) == 2


def test_persona_pipeline_verify_cli(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "snapshot.json"
    report_path = tmp_path / "report.json"

    generated = runner.invoke(
        app,
        [
            "persona-pipeline-run",
            "--profile-file",
            "tests/fixtures/profile-2026-0001-demo.json",
            "--output-file",
            str(snapshot_path),
            "--project-root",
            ".",
        ],
    )
    assert generated.exit_code == 0

    verified = runner.invoke(
        app,
        [
            "persona-pipeline-verify",
            "--snapshot-file",
            str(snapshot_path),
            "--project-root",
            ".",
            "--output-file",
            str(report_path),
        ],
    )

    assert verified.exit_code == 0
    assert "All 10 checks passed." in verified.output
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert all(check["passed"] for check in report["checks"])


def test_persona_pipeline_verify_cli_fails_on_a_tampered_snapshot(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "snapshot.json"
    generated = runner.invoke(
        app,
        [
            "persona-pipeline-run",
            "--profile-file",
            "tests/fixtures/profile-2026-0001-demo.json",
            "--output-file",
            str(snapshot_path),
            "--project-root",
            ".",
        ],
    )
    assert generated.exit_code == 0
    tampered = json.loads(snapshot_path.read_text(encoding="utf-8"))
    tampered["snapshot_digest"] = "bogus"
    snapshot_path.write_text(json.dumps(tampered), encoding="utf-8")

    verified = runner.invoke(
        app,
        [
            "persona-pipeline-verify",
            "--snapshot-file",
            str(snapshot_path),
            "--project-root",
            ".",
        ],
    )

    assert verified.exit_code == 1
    assert "snapshot_digest_matches_content" in verified.output


def test_persona_hard_metrics_cli_aggregates_two_personas(tmp_path: Path) -> None:
    snapshot_a = tmp_path / "a.json"
    snapshot_b = tmp_path / "b.json"
    for path in (snapshot_a, snapshot_b):
        generated = runner.invoke(
            app,
            [
                "persona-pipeline-run",
                "--profile-file",
                "tests/fixtures/profile-2026-0001-demo.json",
                "--output-file",
                str(path),
                "--project-root",
                ".",
                "--feedback-loop",
                "--max-rounds",
                "2",
            ],
        )
        assert generated.exit_code == 0

    report_path = tmp_path / "hard-metrics.json"
    result = runner.invoke(
        app,
        [
            "persona-hard-metrics",
            "--persona-label",
            "a",
            "--coverage-snapshot",
            str(snapshot_a),
            "--persona-label",
            "b",
            "--coverage-snapshot",
            str(snapshot_b),
            "--output-file",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    assert "coverage_rate=" in result.output
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert len(report["personas"]) == 2
    assert {p["persona_label"] for p in report["personas"]} == {"a", "b"}
    # A --max-rounds 2 run stops early, so "attempted" also counts every
    # not-yet-reached node -- this only checks the CLI wiring end to end
    # (arg parsing, snapshot loading, aggregation), not the coverage number
    # itself (covered by tests/unit/evaluation/test_persona_metrics.py).
    assert report["aggregate_coverage"]["attempted_nodes"] > 0


def test_persona_hard_metrics_cli_rejects_a_snapshot_that_is_not_a_json_object(
    tmp_path: Path,
) -> None:
    bad_snapshot = tmp_path / "not-an-object.json"
    bad_snapshot.write_text(json.dumps(["oops", "this-is-a-list"]), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "persona-hard-metrics",
            "--persona-label",
            "a",
            "--coverage-snapshot",
            str(bad_snapshot),
        ],
    )

    assert result.exit_code != 0
    assert "Traceback" not in result.output
    # A raw AttributeError from `.get()` on a list is the exact bug this
    # guards against; asserting the clean Click/Typer error framing is
    # present (rather than the wrapped message text, which can line-wrap
    # differently depending on the terminal width Rich detects) is enough
    # to prove it now fails cleanly instead of crashing.
    assert "Invalid value" in result.output


def test_persona_hard_metrics_cli_rejects_mismatched_label_and_snapshot_counts(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "a.json"
    snapshot.write_text(json.dumps({"profile_id": "p", "full_path": []}), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "persona-hard-metrics",
            "--persona-label",
            "a",
            "--persona-label",
            "b",
            "--coverage-snapshot",
            str(snapshot),
        ],
    )

    assert result.exit_code != 0
    assert "must match --persona-label count" in result.output
