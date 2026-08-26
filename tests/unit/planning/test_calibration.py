import pytest
from pydantic import ValidationError

from skillforge_kb.planning.adaptation import (
    NodeWeightFeatures,
    NodeWeightPolicy,
    SupportIntensity,
)
from skillforge_kb.planning.calibration import (
    CalibrationDataKind,
    NodeWeightCalibrationDataset,
    NodeWeightCalibrationExample,
    NodeWeightCalibrationReport,
    NodeWeightFactor,
    NodeWeightPolicyEvaluation,
    NodeWeightSearchSpace,
    NodeWeightSensitivityPoint,
    build_calibration_dataset_digest,
    evaluate_node_weight_ablations,
    evaluate_node_weight_policy,
    generate_node_weight_policies,
    search_node_weight_policies,
    summarize_node_weight_sensitivity,
)


@pytest.fixture
def dataset() -> NodeWeightCalibrationDataset:
    return NodeWeightCalibrationDataset(
        dataset_id="support-fixtures",
        data_version="support-fixtures.v1",
        data_kind=CalibrationDataKind.SYNTHETIC,
        examples=(
            NodeWeightCalibrationExample(
                case_id="compact",
                features=NodeWeightFeatures(
                    mastery_gap=0.1,
                    error_risk=0.0,
                    ability_gap=0.1,
                ),
                expected_support_intensity=SupportIntensity.COMPACT,
                target_support_need_score=0.075,
            ),
            NodeWeightCalibrationExample(
                case_id="standard",
                features=NodeWeightFeatures(
                    mastery_gap=0.5,
                    error_risk=0.2,
                    ability_gap=0.3,
                ),
                expected_support_intensity=SupportIntensity.STANDARD,
                target_support_need_score=0.385,
            ),
            NodeWeightCalibrationExample(
                case_id="scaffolded",
                features=NodeWeightFeatures(
                    mastery_gap=0.8,
                    error_risk=0.4,
                    ability_gap=0.5,
                ),
                expected_support_intensity=SupportIntensity.SCAFFOLDED,
                target_support_need_score=0.64,
            ),
            NodeWeightCalibrationExample(
                case_id="blocked",
                features=NodeWeightFeatures(
                    mastery_gap=0.0,
                    error_risk=0.0,
                    ability_gap=0.0,
                    blocked=True,
                ),
                expected_support_intensity=SupportIntensity.REMEDIATION,
                target_support_need_score=0.0,
            ),
        ),
    )


@pytest.fixture
def search_space() -> NodeWeightSearchSpace:
    return NodeWeightSearchSpace(
        policy_version_prefix="node-weight-policy.candidate.v1",
        mastery_gap_weights=(0.5, 0.55),
        error_risk_weights=(0.25, 0.3),
        ability_gap_weights=(0.2,),
        compact_thresholds=(0.2, 0.25),
        scaffolded_thresholds=(0.55, 0.6),
    )


def test_dataset_requires_unique_case_ids(dataset) -> None:
    duplicate = dataset.model_copy(update={"examples": (dataset.examples[0],) * 2})

    with pytest.raises(ValidationError, match="case IDs"):
        NodeWeightCalibrationDataset.model_validate(duplicate.model_dump())


def test_examples_require_consistent_blocked_labels() -> None:
    with pytest.raises(ValidationError, match="blocked examples"):
        NodeWeightCalibrationExample(
            case_id="invalid-blocked",
            features=NodeWeightFeatures(
                mastery_gap=0.0,
                error_risk=0.0,
                ability_gap=0.0,
                blocked=True,
            ),
            expected_support_intensity=SupportIntensity.STANDARD,
        )

    with pytest.raises(ValidationError, match="non-blocked examples"):
        NodeWeightCalibrationExample(
            case_id="invalid-remediation",
            features=NodeWeightFeatures(
                mastery_gap=0.5,
                error_risk=0.0,
                ability_gap=0.0,
            ),
            expected_support_intensity=SupportIntensity.REMEDIATION,
        )


def test_dataset_digest_is_stable_and_content_sensitive(dataset) -> None:
    same = NodeWeightCalibrationDataset.model_validate(dataset.model_dump())
    changed = dataset.model_copy(update={"data_version": "support-fixtures.v2"})

    assert build_calibration_dataset_digest(dataset) == build_calibration_dataset_digest(same)
    assert build_calibration_dataset_digest(dataset) != build_calibration_dataset_digest(changed)


def test_search_axes_must_be_strictly_increasing(search_space) -> None:
    invalid = search_space.model_copy(update={"mastery_gap_weights": (0.55, 0.5)})

    with pytest.raises(ValidationError, match="strictly increasing"):
        NodeWeightSearchSpace.model_validate(invalid.model_dump())


def test_candidate_generation_is_deterministic_and_legal(search_space) -> None:
    first = generate_node_weight_policies(search_space)
    second = generate_node_weight_policies(search_space)

    assert first == second
    assert first
    assert len({item.version for item in first}) == len(first)
    assert all(
        item.mastery_gap_weight + item.error_risk_weight + item.ability_gap_weight
        == pytest.approx(1.0)
        for item in first
    )
    assert all(item.compact_threshold < item.scaffolded_threshold for item in first)


def test_candidate_generation_rejects_a_grid_without_valid_weights() -> None:
    search_space = NodeWeightSearchSpace(
        mastery_gap_weights=(0.1,),
        error_risk_weights=(0.1,),
        ability_gap_weights=(0.1,),
        compact_thresholds=(0.25,),
        scaffolded_thresholds=(0.6,),
    )

    with pytest.raises(ValueError, match="no valid policy"):
        generate_node_weight_policies(search_space)


def test_candidate_generation_filters_positive_weight_overshoot() -> None:
    search_space = NodeWeightSearchSpace(
        mastery_gap_weights=(0.5, 0.5000000005),
        error_risk_weights=(0.3,),
        ability_gap_weights=(0.2,),
        compact_thresholds=(0.25,),
        scaffolded_thresholds=(0.6,),
    )

    policies = generate_node_weight_policies(search_space)

    assert len(policies) == 1
    assert policies[0].mastery_gap_weight == 0.5


def test_policy_evaluation_reports_label_fit_and_score_error(dataset) -> None:
    evaluation = evaluate_node_weight_policy(dataset, NodeWeightPolicy())

    assert evaluation.case_count == 4
    assert evaluation.exact_match_count == 4
    assert evaluation.exact_match_rate == 1.0
    assert evaluation.target_case_count == 4
    assert evaluation.mean_absolute_error == pytest.approx(0.0)
    assert tuple(item.case_id for item in evaluation.case_results) == (
        "compact",
        "standard",
        "scaffolded",
        "blocked",
    )
    assert all(item.intensity_matches for item in evaluation.case_results)


def test_policy_evaluation_validates_derived_metrics(dataset) -> None:
    evaluation = evaluate_node_weight_policy(dataset, NodeWeightPolicy())
    invalid = evaluation.model_copy(update={"exact_match_count": 3})

    with pytest.raises(ValidationError, match="exact match count"):
        type(evaluation).model_validate(invalid.model_dump())


def test_policy_evaluation_rejects_duplicate_case_ids(dataset) -> None:
    evaluation = evaluate_node_weight_policy(dataset, NodeWeightPolicy())
    duplicated = evaluation.model_copy(
        update={
            "case_results": (
                *evaluation.case_results[:-1],
                evaluation.case_results[0],
            )
        }
    )

    with pytest.raises(ValidationError, match="case IDs must be unique"):
        NodeWeightPolicyEvaluation.model_validate(duplicated.model_dump())


def test_search_is_deterministic_and_excludes_the_baseline(dataset, search_space) -> None:
    baseline = NodeWeightPolicy()
    first = search_node_weight_policies(dataset, search_space, baseline)
    second = search_node_weight_policies(dataset, search_space, baseline)

    assert first == second
    assert first.baseline.policy == baseline
    assert all(
        _tunable_values(item.policy) != _tunable_values(baseline)
        for item in first.ranked_candidates
    )
    assert first.best_fitting_candidate == first.ranked_candidates[0]
    assert NodeWeightCalibrationReport.model_validate_json(first.model_dump_json()) == first


def test_report_rejects_candidate_case_order_mismatch(dataset, search_space) -> None:
    report = search_node_weight_policies(dataset, search_space, NodeWeightPolicy())
    first = report.ranked_candidates[0]
    reordered = NodeWeightPolicyEvaluation.model_validate(
        first.model_copy(update={"case_results": tuple(reversed(first.case_results))}).model_dump()
    )
    invalid = report.model_copy(
        update={
            "ranked_candidates": (reordered, *report.ranked_candidates[1:]),
            "best_fitting_candidate": reordered,
        }
    )

    with pytest.raises(ValidationError, match="same ordered cases"):
        NodeWeightCalibrationReport.model_validate(invalid.model_dump())


def test_report_rejects_candidate_target_coverage_mismatch(dataset, search_space) -> None:
    report = search_node_weight_policies(dataset, search_space, NodeWeightPolicy())
    first = report.ranked_candidates[0]
    case_results = (
        first.case_results[0].model_copy(update={"absolute_error": None}),
        *first.case_results[1:],
    )
    errors = tuple(item.absolute_error for item in case_results if item.absolute_error is not None)
    changed = NodeWeightPolicyEvaluation.model_validate(
        first.model_copy(
            update={
                "target_case_count": len(errors),
                "mean_absolute_error": sum(errors) / len(errors),
                "case_results": case_results,
            }
        ).model_dump()
    )
    invalid = report.model_copy(
        update={
            "ranked_candidates": (changed, *report.ranked_candidates[1:]),
            "best_fitting_candidate": changed,
        }
    )

    with pytest.raises(ValidationError, match="target coverage"):
        NodeWeightCalibrationReport.model_validate(invalid.model_dump())


def test_report_rejects_duplicate_candidate_tunables(dataset, search_space) -> None:
    report = search_node_weight_policies(dataset, search_space, NodeWeightPolicy())
    duplicated = report.model_copy(
        update={
            "ranked_candidates": (
                report.ranked_candidates[0],
                report.ranked_candidates[0],
                *report.ranked_candidates[2:],
            )
        }
    )

    with pytest.raises(ValidationError, match="candidate tunables must be unique"):
        NodeWeightCalibrationReport.model_validate(duplicated.model_dump())


def test_report_rejects_baseline_in_ranked_candidates(dataset, search_space) -> None:
    report = search_node_weight_policies(dataset, search_space, NodeWeightPolicy())
    invalid = report.model_copy(
        update={
            "ranked_candidates": (report.baseline, *report.ranked_candidates),
            "best_fitting_candidate": report.baseline,
        }
    )

    with pytest.raises(ValidationError, match="must exclude baseline"):
        NodeWeightCalibrationReport.model_validate(invalid.model_dump())


def test_report_rejects_reversed_candidate_ranking(dataset, search_space) -> None:
    report = search_node_weight_policies(dataset, search_space, NodeWeightPolicy())
    reversed_candidates = tuple(reversed(report.ranked_candidates))
    invalid = report.model_copy(
        update={
            "ranked_candidates": reversed_candidates,
            "best_fitting_candidate": reversed_candidates[0],
        }
    )

    with pytest.raises(ValidationError, match="candidate ranking"):
        NodeWeightCalibrationReport.model_validate(invalid.model_dump())


def test_search_prefers_equal_fit_closest_to_the_baseline(dataset) -> None:
    baseline = NodeWeightPolicy()
    unscored = dataset.model_copy(
        update={
            "examples": tuple(
                example.model_copy(update={"target_support_need_score": None})
                for example in dataset.examples
            )
        }
    )
    search_space = NodeWeightSearchSpace(
        mastery_gap_weights=(0.5, 0.55),
        error_risk_weights=(0.25, 0.3),
        ability_gap_weights=(0.2,),
        compact_thresholds=(0.2, 0.25),
        scaffolded_thresholds=(0.6,),
    )

    report = search_node_weight_policies(unscored, search_space, baseline)

    assert _tunable_values(report.best_fitting_candidate.policy) == (
        0.55,
        0.25,
        0.2,
        0.2,
        0.6,
    )


def test_search_prefers_lower_score_error_before_policy_distance(dataset) -> None:
    targets = {
        "compact": 0.07,
        "standard": 0.37,
        "scaffolded": 0.62,
        "blocked": 0.0,
    }
    targeted = dataset.model_copy(
        update={
            "examples": tuple(
                example.model_copy(
                    update={"target_support_need_score": targets[example.case_id]}
                )
                for example in dataset.examples
            )
        }
    )
    search_space = NodeWeightSearchSpace(
        mastery_gap_weights=(0.5, 0.55),
        error_risk_weights=(0.25, 0.3),
        ability_gap_weights=(0.2,),
        compact_thresholds=(0.2, 0.25),
        scaffolded_thresholds=(0.6,),
    )

    report = search_node_weight_policies(targeted, search_space, NodeWeightPolicy())

    assert _tunable_values(report.best_fitting_candidate.policy) == (
        0.5,
        0.3,
        0.2,
        0.25,
        0.6,
    )


def test_search_prefers_intensity_match_rate_before_other_metrics(dataset) -> None:
    unscored = dataset.model_copy(
        update={
            "examples": tuple(
                example.model_copy(update={"target_support_need_score": None})
                for example in dataset.examples
            )
        }
    )
    search_space = NodeWeightSearchSpace(
        mastery_gap_weights=(0.55,),
        error_risk_weights=(0.25,),
        ability_gap_weights=(0.2,),
        compact_thresholds=(0.1, 0.25),
        scaffolded_thresholds=(0.6, 0.65),
    )

    report = search_node_weight_policies(unscored, search_space, NodeWeightPolicy())

    assert report.best_fitting_candidate.exact_match_rate == 1.0
    assert _tunable_values(report.best_fitting_candidate.policy) == (
        0.55,
        0.25,
        0.2,
        0.1,
        0.6,
    )


def test_search_uses_policy_digest_as_the_final_tie_break(dataset) -> None:
    unscored = dataset.model_copy(
        update={
            "examples": tuple(
                example.model_copy(
                    update={
                        "features": (
                            NodeWeightFeatures(
                                mastery_gap=1.0,
                                error_risk=1.0,
                                ability_gap=1.0,
                            )
                            if example.case_id == "scaffolded"
                            else example.features
                        ),
                        "target_support_need_score": None,
                    }
                )
                for example in dataset.examples
            )
        }
    )
    search_space = NodeWeightSearchSpace(
        mastery_gap_weights=(0.55,),
        error_risk_weights=(0.25,),
        ability_gap_weights=(0.2,),
        compact_thresholds=(0.125, 0.25),
        scaffolded_thresholds=(0.6, 0.725),
    )

    report = search_node_weight_policies(unscored, search_space, NodeWeightPolicy())
    tied_values = {
        (0.55, 0.25, 0.2, 0.125, 0.6),
        (0.55, 0.25, 0.2, 0.25, 0.725),
    }
    tied = tuple(
        item
        for item in report.ranked_candidates
        if _tunable_values(item.policy) in tied_values
    )

    assert len(tied) == 2
    assert report.best_fitting_candidate == min(tied, key=lambda item: item.policy_digest)


def test_search_rejects_a_grid_without_an_alternative(dataset) -> None:
    baseline = NodeWeightPolicy()
    search_space = NodeWeightSearchSpace()

    with pytest.raises(ValueError, match="no alternative policy"):
        search_node_weight_policies(dataset, search_space, baseline)


def test_default_policy_ablation_removes_each_factor_and_renormalizes(dataset) -> None:
    results = evaluate_node_weight_ablations(dataset, NodeWeightPolicy())

    assert tuple(item.removed_factor for item in results) == tuple(NodeWeightFactor)
    for item in results:
        policy = item.evaluation.policy
        assert getattr(policy, item.removed_factor.value) == 0.0
        assert sum(_weight_values(policy)) == pytest.approx(1.0)
        assert item.evaluation.case_count == len(dataset.examples)


def test_ablation_rejects_a_policy_with_no_remaining_weight(dataset) -> None:
    policy = NodeWeightPolicy(
        mastery_gap_weight=1.0,
        error_risk_weight=0.0,
        ability_gap_weight=0.0,
    )

    with pytest.raises(ValueError, match="no positive remaining weight"):
        evaluate_node_weight_ablations(dataset, policy)


def test_sensitivity_summarizes_every_factor_value_deterministically(
    dataset,
    search_space,
) -> None:
    report = search_node_weight_policies(dataset, search_space, NodeWeightPolicy())

    first = summarize_node_weight_sensitivity(report)
    second = summarize_node_weight_sensitivity(report)

    assert first == second
    assert all(isinstance(item, NodeWeightSensitivityPoint) for item in first)
    expected_keys = tuple(
        (factor, value)
        for factor in NodeWeightFactor
        for value in sorted(
            {
                getattr(evaluation.policy, factor.value)
                for evaluation in report.ranked_candidates
            }
        )
    )
    assert tuple((item.factor, item.value) for item in first) == expected_keys
    for item in first:
        matching = tuple(
            evaluation
            for evaluation in report.ranked_candidates
            if getattr(evaluation.policy, item.factor.value) == item.value
        )
        assert item.candidate_count == len(matching)
        assert item.mean_exact_match_rate == pytest.approx(
            sum(evaluation.exact_match_rate for evaluation in matching) / len(matching)
        )
        assert item.mean_absolute_error == pytest.approx(
            sum(
                evaluation.mean_absolute_error
                for evaluation in matching
                if evaluation.mean_absolute_error is not None
            )
            / len(matching)
        )


def test_sensitivity_preserves_missing_score_error(dataset, search_space) -> None:
    unscored = dataset.model_copy(
        update={
            "examples": tuple(
                example.model_copy(update={"target_support_need_score": None})
                for example in dataset.examples
            )
        }
    )
    report = search_node_weight_policies(unscored, search_space, NodeWeightPolicy())

    points = summarize_node_weight_sensitivity(report)

    assert all(item.mean_absolute_error is None for item in points)


def test_calibration_api_is_available_from_planning_package() -> None:
    from skillforge_kb.planning import (
        NodeWeightCalibrationDataset as PublicDataset,
    )
    from skillforge_kb.planning import (
        evaluate_node_weight_ablations as public_ablation,
    )
    from skillforge_kb.planning import (
        score_node_support as public_score,
    )
    from skillforge_kb.planning import (
        search_node_weight_policies as public_search,
    )
    from skillforge_kb.planning import (
        summarize_node_weight_sensitivity as public_sensitivity,
    )

    assert PublicDataset is NodeWeightCalibrationDataset
    assert public_ablation is evaluate_node_weight_ablations
    assert public_score.__name__ == "score_node_support"
    assert public_search is search_node_weight_policies
    assert public_sensitivity is summarize_node_weight_sensitivity


def _tunable_values(policy: NodeWeightPolicy) -> tuple[float, ...]:
    return (
        policy.mastery_gap_weight,
        policy.error_risk_weight,
        policy.ability_gap_weight,
        policy.compact_threshold,
        policy.scaffolded_threshold,
    )


def _weight_values(policy: NodeWeightPolicy) -> tuple[float, float, float]:
    return (
        policy.mastery_gap_weight,
        policy.error_risk_weight,
        policy.ability_gap_weight,
    )
