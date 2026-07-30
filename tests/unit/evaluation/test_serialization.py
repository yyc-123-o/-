import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from skillforge_kb.evaluation import (
    PathEvaluationReport,
    PlannerPolicyCalibrationReport,
    evaluate_course_paths,
    generate_synthetic_dataset,
    load_synthetic_dataset,
    search_planner_policies,
    write_path_evaluation_report,
    write_planner_policy_calibration_report,
    write_synthetic_dataset,
)


def test_dataset_write_and_load_round_trip(tmp_path: Path, catalog) -> None:
    dataset = generate_synthetic_dataset(catalog, case_count=8)
    output = tmp_path / "dataset.json"

    write_synthetic_dataset(dataset, output)

    assert output.read_bytes().endswith(b"\n")
    assert load_synthetic_dataset(output) == dataset
    assert not (tmp_path / ".dataset.json.tmp").exists()


def test_dataset_write_atomically_replaces_existing_file(tmp_path: Path, catalog) -> None:
    output = tmp_path / "dataset.json"
    output.write_text("stale", encoding="utf-8")
    dataset = generate_synthetic_dataset(catalog, case_count=8)

    write_synthetic_dataset(dataset, output)

    assert load_synthetic_dataset(output) == dataset


def test_dataset_load_rejects_tampered_digest(tmp_path: Path, catalog) -> None:
    output = tmp_path / "dataset.json"
    write_synthetic_dataset(generate_synthetic_dataset(catalog, case_count=8), output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    payload["seed"] += 1
    output.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValidationError, match="digest"):
        load_synthetic_dataset(output)


def test_report_write_is_valid_and_atomic(tmp_path: Path, catalog) -> None:
    report = evaluate_course_paths(
        catalog,
        generate_synthetic_dataset(catalog, case_count=8),
    )
    output = tmp_path / "report.json"

    write_path_evaluation_report(report, output)

    loaded = PathEvaluationReport.model_validate_json(output.read_text(encoding="utf-8"))
    assert loaded == report
    assert not (tmp_path / ".report.json.tmp").exists()


def test_calibration_report_write_is_valid_and_atomic(tmp_path: Path, catalog) -> None:
    report = search_planner_policies(
        catalog,
        generate_synthetic_dataset(catalog, case_count=8),
    )
    output = tmp_path / "calibration.json"

    write_planner_policy_calibration_report(report, output)

    loaded = PlannerPolicyCalibrationReport.model_validate_json(
        output.read_text(encoding="utf-8")
    )
    assert loaded == report
    assert not (tmp_path / ".calibration.json.tmp").exists()
