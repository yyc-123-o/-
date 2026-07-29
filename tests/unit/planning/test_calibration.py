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
    NodeWeightSearchSpace,
    build_calibration_dataset_digest,
    evaluate_node_weight_policy,
    generate_node_weight_policies,
    search_node_weight_policies,
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


def test_search_prefers_equal_fit_closest_to_the_baseline(dataset) -> None:
    baseline = NodeWeightPolicy()
    search_space = NodeWeightSearchSpace(
        mastery_gap_weights=(0.5, 0.55),
        error_risk_weights=(0.25, 0.3),
        ability_gap_weights=(0.2,),
        compact_thresholds=(0.2, 0.25),
        scaffolded_thresholds=(0.6,),
    )

    report = search_node_weight_policies(dataset, search_space, baseline)

    assert _tunable_values(report.best_fitting_candidate.policy) == (
        0.55,
        0.25,
        0.2,
        0.2,
        0.6,
    )


def test_search_rejects_a_grid_without_an_alternative(dataset) -> None:
    baseline = NodeWeightPolicy()
    search_space = NodeWeightSearchSpace()

    with pytest.raises(ValueError, match="no alternative policy"):
        search_node_weight_policies(dataset, search_space, baseline)


def _tunable_values(policy: NodeWeightPolicy) -> tuple[float, ...]:
    return (
        policy.mastery_gap_weight,
        policy.error_risk_weight,
        policy.ability_gap_weight,
        policy.compact_threshold,
        policy.scaffolded_threshold,
    )
