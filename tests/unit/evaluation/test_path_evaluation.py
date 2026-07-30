import pytest
from pydantic import ValidationError

from skillforge_kb.evaluation import (
    PathEvaluationReport,
    ScenarioCohort,
    build_synthetic_dataset_digest,
    evaluate_course_path_cases,
    evaluate_course_paths,
    generate_synthetic_dataset,
)
from skillforge_kb.ontology.models import DepthLevel
from skillforge_kb.planning import PlannerPolicy


def test_default_planner_preserves_graph_invariants(catalog) -> None:
    dataset = generate_synthetic_dataset(catalog)
    report = evaluate_course_paths(catalog, dataset)

    assert report.metrics.hard_prerequisite_violation_rate == 0.0
    assert report.metrics.required_concept_coverage_rate == 1.0
    assert report.metrics.path_order_stability_rate == 1.0
    assert report.metrics.skip_accuracy == 1.0
    assert report.metrics.delivery_depth_accuracy == 1.0
    assert len(report.case_results) == 60


def test_low_confidence_cases_are_conservative(catalog) -> None:
    report = evaluate_course_paths(catalog, generate_synthetic_dataset(catalog))

    assert report.metrics.low_confidence_case_count > 0
    assert report.metrics.low_confidence_conservative_rate == 1.0
    assert all(
        item.low_confidence_conservative is True
        for item in report.case_results
        if item.cohort is ScenarioCohort.LOW_CONFIDENCE
    )


def test_evaluator_rejects_policy_mismatch(catalog) -> None:
    dataset = generate_synthetic_dataset(catalog)
    changed = PlannerPolicy(version="planner-policy.changed")

    with pytest.raises(ValueError, match="policy"):
        evaluate_course_paths(catalog, dataset, changed)


def test_candidate_case_evaluation_accepts_a_different_policy(catalog) -> None:
    dataset = generate_synthetic_dataset(catalog, case_count=8)
    candidate = PlannerPolicy(
        version="planner-policy.candidate.v1",
        intermediate_threshold=0.70,
    )

    results = evaluate_course_path_cases(catalog, dataset, candidate)

    assert len(results) == 8
    assert any(item.depth_mismatch_ids for item in results)


def test_strict_report_still_rejects_a_different_policy(catalog) -> None:
    dataset = generate_synthetic_dataset(catalog, case_count=8)

    with pytest.raises(ValueError, match="policy"):
        evaluate_course_paths(
            catalog,
            dataset,
            PlannerPolicy(version="planner-policy.candidate.v1"),
        )


def test_evaluator_reports_oracle_depth_mismatches(catalog) -> None:
    dataset = generate_synthetic_dataset(catalog, case_count=8)
    first_case = dataset.cases[0]
    first_node = first_case.expected_nodes[0]
    assert first_node.delivery_depth is DepthLevel.INTRO
    changed_node = first_node.model_copy(
        update={"delivery_depth": DepthLevel.INTERMEDIATE}
    )
    changed_case = first_case.model_copy(
        update={"expected_nodes": (changed_node, *first_case.expected_nodes[1:])}
    )
    payload = dataset.model_dump(mode="json", exclude={"dataset_digest"})
    payload["cases"] = [changed_case.model_dump(mode="json"), *payload["cases"][1:]]
    payload["dataset_digest"] = build_synthetic_dataset_digest(payload)
    changed_dataset = type(dataset).model_validate(payload)

    report = evaluate_course_paths(catalog, changed_dataset)

    assert report.metrics.delivery_depth_accuracy < 1.0
    assert report.case_results[0].depth_mismatch_ids == (first_node.concept_id,)


def test_report_round_trip_preserves_digest(catalog) -> None:
    report = evaluate_course_paths(
        catalog,
        generate_synthetic_dataset(catalog, case_count=8),
    )

    assert PathEvaluationReport.model_validate_json(report.model_dump_json()) == report


def test_report_rejects_aggregate_mutation(catalog) -> None:
    report = evaluate_course_paths(
        catalog,
        generate_synthetic_dataset(catalog, case_count=8),
    )
    payload = report.model_dump()
    payload["metrics"]["skip_accuracy"] = 0.5

    with pytest.raises(ValidationError, match="skip accuracy"):
        PathEvaluationReport.model_validate(payload)


def test_report_digest_rejects_case_mutation(catalog) -> None:
    report = evaluate_course_paths(
        catalog,
        generate_synthetic_dataset(catalog, case_count=8),
    )
    payload = report.model_dump()
    payload["case_results"][0]["path_id"] = report.case_results[1].path_id

    with pytest.raises(ValidationError, match="report digest"):
        PathEvaluationReport.model_validate(payload)
