from skillforge_kb.evaluation.persona_metrics import (
    aggregate_hard_metrics,
    compute_persona_hard_metrics,
)


def _resource_node(
    *,
    concept_id: str,
    status: str = "available",
    resource_mode: str = "candidate_draft",
    delivery_depth: str | None = "intro",
    difficulties: tuple[int, ...] | None = (1, 1, 1, 1, 1, 2, 2, 3),
    model_name: str | None = "glm-4-flash",
    claim_support: tuple[str, ...] = ("supported", "supported", "unsupported"),
) -> dict:
    node: dict = {
        "concept_id": concept_id,
        "status": status,
        "resource_mode": resource_mode,
        "delivery_depth": delivery_depth,
    }
    if resource_mode not in {"formal", "candidate_draft"} or model_name is None:
        return node
    preview_package: dict = {}
    if difficulties is not None:
        preview_package["draft"] = {
            "student_quiz": {
                "items": [{"difficulty": value} for value in difficulties],
            }
        }
    preview_package["trace"] = {"model_name": model_name}
    preview_package["audit_report"] = {
        "claim_evidence_ledger": [{"support": support} for support in claim_support]
    }
    node["resource_result"] = {"preview_package": preview_package}
    return node


def _snapshot(nodes: list[dict], profile_id: str = "P-1") -> dict:
    return {"profile_id": profile_id, "full_path": nodes}


def test_coverage_counts_non_skipped_nodes_with_a_produced_resource() -> None:
    nodes = [
        _resource_node(concept_id="a", resource_mode="candidate_draft"),
        _resource_node(concept_id="b", resource_mode="blocked_hard_prerequisite"),
        _resource_node(concept_id="c", status="skipped", resource_mode="not_attempted"),
    ]
    metrics = compute_persona_hard_metrics("p", _snapshot(nodes), None)

    assert metrics.coverage.attempted_nodes == 2  # "c" is skipped, excluded
    assert metrics.coverage.covered_nodes == 1  # only "a" produced a resource
    assert metrics.coverage.coverage_rate == 0.5


def test_coverage_rate_is_zero_not_a_crash_when_nothing_was_attempted() -> None:
    nodes = [_resource_node(concept_id="a", status="skipped")]
    metrics = compute_persona_hard_metrics("p", _snapshot(nodes), None)

    assert metrics.coverage.attempted_nodes == 0
    assert metrics.coverage.coverage_rate == 0.0


def test_adaptation_checks_modal_quiz_difficulty_against_delivery_depth() -> None:
    nodes = [
        _resource_node(
            concept_id="intro-match",
            delivery_depth="intro",
            difficulties=(1,) * 5 + (2,) * 3,
        ),
        _resource_node(
            concept_id="advanced-mismatch",
            delivery_depth="advanced",
            difficulties=(1,) * 5 + (2,) * 3,  # modal is 1, expected 3
        ),
    ]
    metrics = compute_persona_hard_metrics("p", _snapshot(nodes), None)

    assert metrics.adaptation.checked_nodes == 2
    assert metrics.adaptation.matched_nodes == 1
    assert metrics.adaptation.adaptation_accuracy == 0.5


def test_adaptation_skips_nodes_with_no_draft_instead_of_counting_a_mismatch() -> None:
    nodes = [
        _resource_node(concept_id="blocked", resource_mode="blocked_hard_prerequisite"),
        _resource_node(concept_id="no-depth", delivery_depth=None),
    ]
    metrics = compute_persona_hard_metrics("p", _snapshot(nodes), None)

    assert metrics.adaptation.checked_nodes == 0
    assert metrics.adaptation.adaptation_accuracy == 0.0


def test_hallucination_rate_ignores_fallback_generated_nodes() -> None:
    nodes = [
        _resource_node(
            concept_id="real",
            model_name="glm-4-flash",
            claim_support=("supported", "unsupported"),
        ),
        _resource_node(
            concept_id="fallback",
            model_name="fake-resource-writer",
            claim_support=("unsupported", "unsupported", "unsupported"),
        ),
    ]
    metrics = compute_persona_hard_metrics("p", _snapshot(nodes), _snapshot(nodes))

    assert metrics.hallucination is not None
    # only the "real" node counts -- the fallback node's 3 unsupported claims
    # must not leak into the numerator/denominator.
    assert metrics.hallucination.sampled_node_count == 1
    assert metrics.hallucination.total_claims == 2
    assert metrics.hallucination.unsupported_claims == 1
    assert metrics.hallucination.hallucination_rate == 0.5


def test_hallucination_is_none_when_no_sample_snapshot_is_given() -> None:
    metrics = compute_persona_hard_metrics("p", _snapshot([_resource_node(concept_id="a")]), None)

    assert metrics.hallucination is None


def test_aggregate_combines_personas_and_evaluates_the_three_thresholds() -> None:
    good_nodes = [
        _resource_node(
            concept_id=f"c{i}",
            claim_support=("supported",) * 19 + ("unsupported",),  # 5% exactly
        )
        for i in range(1)
    ]
    persona = compute_persona_hard_metrics("only", _snapshot(good_nodes), _snapshot(good_nodes))
    report = aggregate_hard_metrics([persona])

    assert report.aggregate_coverage.coverage_rate == 1.0
    assert report.aggregate_adaptation.adaptation_accuracy == 1.0
    assert report.aggregate_hallucination.hallucination_rate == 0.05
    assert report.thresholds_met == {
        "hallucination_rate_below_5pct": False,  # 5% is not strictly below 5%
        "adaptation_accuracy_at_least_85pct": True,
        "coverage_rate_at_least_90pct": True,
    }
    assert report.report_digest.startswith("persona_hard_metrics_")


def test_aggregate_of_no_personas_reports_zero_not_a_crash() -> None:
    report = aggregate_hard_metrics([])

    assert report.aggregate_coverage.coverage_rate == 0.0
    assert report.aggregate_adaptation.adaptation_accuracy == 0.0
    assert report.aggregate_hallucination.hallucination_rate == 0.0
    assert report.thresholds_met["hallucination_rate_below_5pct"] is True


def test_report_is_frozen() -> None:
    import pytest
    from pydantic import ValidationError

    report = aggregate_hard_metrics([])
    with pytest.raises(ValidationError):
        report.report_digest = "mutated"  # type: ignore[misc]
