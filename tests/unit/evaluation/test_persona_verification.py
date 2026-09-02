import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from skillforge_kb.evaluation.persona_pipeline import (
    build_persona_pipeline_context,
    run_persona_feedback_loop,
    run_persona_pipeline,
)
from skillforge_kb.evaluation.persona_verification import verify_persona_snapshot
from skillforge_kb.ontology.catalog import OntologyCatalog

PROJECT_ROOT = Path(__file__).parents[3]
CNN_CONCEPT_ID = "dl.cnn.convolution"


def _demo_profile_payload() -> dict[str, object]:
    path = PROJECT_ROOT / "tests" / "fixtures" / "profile-2026-0001-demo.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _mutable_snapshot(snapshot: Any) -> dict[str, Any]:
    """``model_dump(mode="python")`` keeps tuples as tuples; tests need to
    mutate lists in place, so convert the one collection most tests touch."""

    payload = snapshot.model_dump(mode="python")
    payload["full_path"] = list(payload["full_path"])
    return payload


def test_verify_passes_for_healthy_one_shot_snapshot(catalog: OntologyCatalog) -> None:
    context = build_persona_pipeline_context(PROJECT_ROOT)
    snapshot = run_persona_pipeline(context, _demo_profile_payload())

    report = verify_persona_snapshot(catalog, snapshot.model_dump(mode="python"))

    assert report.passed is True
    assert [check.code for check in report.checks if not check.passed] == []
    codes = {check.code for check in report.checks}
    assert "hard_prerequisite_order" in codes
    assert "candidate_drafts_have_audit_report" in codes


def test_verify_passes_for_healthy_feedback_loop_snapshot(catalog: OntologyCatalog) -> None:
    context = build_persona_pipeline_context(PROJECT_ROOT)
    snapshot = run_persona_feedback_loop(context, _demo_profile_payload(), max_rounds=5)

    report = verify_persona_snapshot(catalog, snapshot.model_dump(mode="python"))

    assert report.passed is True
    feedback_check = next(c for c in report.checks if c.code == "feedback_rounds_consistent")
    assert feedback_check.sample_size == 5


def test_verify_works_on_a_disk_round_trip_of_the_persisted_json(
    catalog: OntologyCatalog, tmp_path: Path
) -> None:
    """The persisted JSON file is intentionally not guaranteed to round-trip
    through ``PersonaPipelineSnapshot.model_validate_json`` (candidate-preview
    redaction) -- verification must still work against the same file via
    plain ``json.loads``, which is the whole point of taking a ``Mapping``."""

    context = build_persona_pipeline_context(PROJECT_ROOT)
    snapshot = run_persona_pipeline(context, _demo_profile_payload())
    output = tmp_path / "snapshot.json"
    output.write_text(json.dumps(snapshot.model_dump(mode="json")), encoding="utf-8")

    reloaded = json.loads(output.read_text(encoding="utf-8"))
    report = verify_persona_snapshot(catalog, reloaded)

    assert report.passed is True


def test_verify_reports_pipeline_failure_and_skips_the_rest(catalog: OntologyCatalog) -> None:
    report = verify_persona_snapshot(
        catalog,
        {
            "profile_id": "p1",
            "path_id": None,
            "pipeline_failure": "planning error",
            "full_path": [],
        },
    )

    assert report.passed is False
    assert len(report.checks) == 1
    assert report.checks[0].code == "no_pipeline_failure"


def test_verify_catches_a_missing_node(catalog: OntologyCatalog) -> None:
    context = build_persona_pipeline_context(PROJECT_ROOT)
    snapshot = run_persona_pipeline(context, _demo_profile_payload())
    payload = _mutable_snapshot(snapshot)
    removed = payload["full_path"].pop(0)

    report = verify_persona_snapshot(catalog, payload)

    assert report.passed is False
    failed_codes = {check.code for check in report.checks if not check.passed}
    assert {"full_path_matches_catalog", "snapshot_digest_matches_content"} <= failed_codes
    match = next(c for c in report.checks if c.code == "full_path_matches_catalog")
    assert removed["concept_id"] in match.failures


def test_verify_catches_a_tampered_digest(catalog: OntologyCatalog) -> None:
    context = build_persona_pipeline_context(PROJECT_ROOT)
    snapshot = run_persona_pipeline(context, _demo_profile_payload())
    payload = _mutable_snapshot(snapshot)
    payload["snapshot_digest"] = "persona_pipeline_0" * 8

    report = verify_persona_snapshot(catalog, payload)

    assert report.passed is False
    check = next(c for c in report.checks if c.code == "snapshot_digest_matches_content")
    assert check.passed is False


def test_verify_catches_a_hard_prerequisite_violation(catalog: OntologyCatalog) -> None:
    context = build_persona_pipeline_context(PROJECT_ROOT)
    snapshot = run_persona_pipeline(context, _demo_profile_payload())
    payload = _mutable_snapshot(snapshot)
    # Swap two far-apart nodes to break at least one hard-prerequisite pair
    # without touching the concept set (so the catalog-membership check still
    # passes and this check is exercised in isolation).
    payload["full_path"][0], payload["full_path"][60] = (
        payload["full_path"][60],
        payload["full_path"][0],
    )

    report = verify_persona_snapshot(catalog, payload)

    assert report.passed is False
    check = next(c for c in report.checks if c.code == "hard_prerequisite_order")
    assert check.passed is False
    assert check.failures


def test_verify_catches_resource_mode_gate_mismatch(catalog: OntologyCatalog) -> None:
    context = build_persona_pipeline_context(PROJECT_ROOT)
    snapshot = run_persona_pipeline(context, _demo_profile_payload())
    payload = _mutable_snapshot(snapshot)
    candidate_node = next(
        node for node in payload["full_path"] if node["resource_mode"] == "candidate_draft"
    )
    candidate_node["resource_mode"] = "formal"

    report = verify_persona_snapshot(catalog, payload)

    assert report.passed is False
    gate_check = next(
        c for c in report.checks if c.code == "resource_mode_matches_generation_gate"
    )
    assert gate_check.passed is False
    assert candidate_node["concept_id"] in gate_check.failures
    evidence_check = next(
        c for c in report.checks if c.code == "formal_nodes_have_published_evidence"
    )
    assert evidence_check.passed is False


def test_verify_catches_a_missing_audit_report(catalog: OntologyCatalog) -> None:
    context = build_persona_pipeline_context(PROJECT_ROOT)
    snapshot = run_persona_pipeline(context, _demo_profile_payload())
    payload = _mutable_snapshot(snapshot)
    candidate_node = next(
        node for node in payload["full_path"] if node["resource_mode"] == "candidate_draft"
    )
    candidate_node["resource_result"]["preview_package"]["audit_report"] = None

    report = verify_persona_snapshot(catalog, payload)

    assert report.passed is False
    check = next(c for c in report.checks if c.code == "candidate_drafts_have_audit_report")
    assert check.passed is False
    assert candidate_node["concept_id"] in check.failures


def test_verification_report_is_frozen(catalog: OntologyCatalog) -> None:
    report = verify_persona_snapshot(
        catalog,
        {"profile_id": "p1", "path_id": None, "pipeline_failure": "x", "full_path": []},
    )

    with pytest.raises(ValidationError):
        report.passed = True  # type: ignore[misc]
