from datetime import UTC, datetime
import json
from pathlib import Path
from math import log

import pytest
from pydantic import ValidationError

from skillforge_kb.evaluation.knowledge_tracing import (
    KnowledgeTracingObservation,
    compare_knowledge_tracing_reports,
    evaluate_knowledge_tracing,
    load_knowledge_tracing_report,
    write_knowledge_tracing_report,
)


def _observation(
    observation_id: str,
    probability: float,
    correct: bool,
    model: str = "bkt.v1",
) -> KnowledgeTracingObservation:
    return KnowledgeTracingObservation(
        observation_id=observation_id,
        profile_id="profile-eval",
        concept_id="ml.optimization.gradient-descent",
        model_version=model,
        predicted_mastery=probability,
        correct=correct,
        observed_at=datetime(2026, 8, 26, tzinfo=UTC),
    )


def test_metrics_match_known_predictions() -> None:
    report = evaluate_knowledge_tracing(
        (
            _observation("o1", 0.9, True),
            _observation("o2", 0.2, False),
            _observation("o3", 0.8, True),
            _observation("o4", 0.1, False),
        )
    )

    assert report.metrics.sample_count == 4
    assert report.metrics.brier_score == pytest.approx(0.025)
    assert report.metrics.log_loss == pytest.approx(
        -(2 * log(0.9) + 2 * log(0.8)) / 4
    )
    assert report.metrics.auc == pytest.approx(1.0)


def test_single_class_auc_is_none_and_invalid_input_fails() -> None:
    report = evaluate_knowledge_tracing((_observation("o1", 0.8, True),))

    assert report.metrics.auc is None
    with pytest.raises(ValidationError):
        _observation("bad", 1.1, True)
    with pytest.raises(ValueError, match="at least one"):
        evaluate_knowledge_tracing(())


def test_auc_supports_reverse_predictions_and_ties() -> None:
    reverse = evaluate_knowledge_tracing(
        (
            _observation("r1", 0.9, False),
            _observation("r2", 0.1, True),
        )
    )
    tied = evaluate_knowledge_tracing(
        (
            _observation("t1", 0.5, True),
            _observation("t2", 0.5, False),
            _observation("t3", 0.2, True),
            _observation("t4", 0.1, False),
        )
    )

    assert reverse.metrics.auc == pytest.approx(0.0)
    assert tied.metrics.auc == pytest.approx(0.625)


def test_evaluation_rejects_duplicate_ids_mixed_models_and_naive_time() -> None:
    with pytest.raises(ValueError, match="IDs"):
        evaluate_knowledge_tracing(
            (_observation("same", 0.5, True), _observation("same", 0.4, False))
        )
    with pytest.raises(ValueError, match="one model"):
        evaluate_knowledge_tracing(
            (_observation("m1", 0.5, True), _observation("m2", 0.4, False, "rule.v1"))
        )
    with pytest.raises(ValidationError, match="timezone-aware"):
        KnowledgeTracingObservation(
            observation_id="naive",
            profile_id="profile-eval",
            concept_id="ml.optimization.gradient-descent",
            model_version="bkt.v1",
            predicted_mastery=0.5,
            correct=True,
            observed_at=datetime(2026, 8, 26),
        )


def test_log_loss_is_finite_at_probability_boundaries() -> None:
    report = evaluate_knowledge_tracing(
        (_observation("zero", 0.0, True), _observation("one", 1.0, False))
    )

    assert report.metrics.log_loss < 100


def test_report_round_trip_and_tamper_detection(tmp_path: Path) -> None:
    report = evaluate_knowledge_tracing((_observation("o1", 0.8, True),))
    output = tmp_path / "kt-report.json"

    write_knowledge_tracing_report(report, output)
    assert load_knowledge_tracing_report(output) == report
    assert not (tmp_path / ".kt-report.json.tmp").exists()

    payload = json.loads(output.read_text(encoding="utf-8"))
    payload["metrics"]["brier_score"] = 0.9
    output.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValidationError, match="digest"):
        load_knowledge_tracing_report(output)


def test_comparison_requires_same_observation_set() -> None:
    bkt = evaluate_knowledge_tracing(
        (
            _observation("o1", 0.9, True, "bkt.v1"),
            _observation("o2", 0.2, False, "bkt.v1"),
        )
    )
    rule = evaluate_knowledge_tracing(
        (
            _observation("o1", 0.7, True, "rule.v1"),
            _observation("o2", 0.4, False, "rule.v1"),
        )
    )

    comparison = compare_knowledge_tracing_reports((bkt, rule))

    assert comparison.ranking[0] in {"bkt.v1", "rule.v1"}
    with pytest.raises(ValueError, match="observation IDs"):
        compare_knowledge_tracing_reports(
            (
                bkt,
                evaluate_knowledge_tracing(
                    (_observation("different", 0.5, True, "rule.v1"),)
                ),
            )
        )
