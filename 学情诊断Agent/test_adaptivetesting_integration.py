"""第三方 adaptivetesting 接入的行为验证。"""

import numpy as np

from core import adaptive_test
from core import irt
from core.profile_builder import build_profile
from generators.mock_generator import generate_all_mock_data
from generators.mock_generator import generate_test_bank
from models.knowledge_graph import KG


def _small_bank():
    bank = generate_test_bank(KG, np.random.default_rng(19))
    selected = []
    seen = set()
    for question in bank:
        kp_id = question["knowledge_point_id"]
        if kp_id not in seen:
            selected.append(question)
            seen.add(kp_id)
        if len(selected) == 3:
            break
    # Include a second item per covered knowledge point for the CAT phase.
    for kp_id in list(seen):
        selected.append(next(q for q in bank if q["knowledge_point_id"] == kp_id and q not in selected))
    return selected


def test_adaptivetesting_updates_eap_and_selects_without_duplicates():
    assert adaptive_test._cat is not None
    bank = _small_bank()
    config = adaptive_test.build_config(
        {
            "max_questions": 6,
            "min_questions": 3,
            "min_kp_coverage": 3,
        }
    )
    started = adaptive_test.start_session("cat-integration", 0.0, bank, config)
    session_id = started["session_id"]
    asked = []
    result = started

    while not result.get("finished"):
        question = result["next_question"]
        assert question["question_id"] not in asked
        asked.append(question["question_id"])
        result = adaptive_test.submit_answer(
            session_id,
            question["question_id"],
            question.get("correct_answer", 0),
            30,
            bank,
        )

    assert result["question_count"] == 3
    assert result["covered_kp"] == 3
    assert result["theta_info"]["method"] == "adaptivetesting-EAP"
    assert np.isfinite(result["current_theta"] if "current_theta" in result else result["final_theta"])
    assert np.isfinite(result["standard_error"])

    selected = adaptive_test._pick_max_fisher(bank, result["final_theta"])
    assert selected is not None
    assert selected["question_id"] in {q["question_id"] for q in bank}


def test_standard_error_threshold_is_a_supported_stop_condition():
    bank = _small_bank()
    config = adaptive_test.build_config(
        {
            "max_questions": 6,
            "min_questions": 2,
            "min_kp_coverage": 2,
            "standard_error_threshold": 2.0,
        }
    )
    result = adaptive_test.start_session("cat-se", 0.0, bank, config)
    while not result.get("finished"):
        question = result["next_question"]
        full = next(q for q in bank if q["question_id"] == question["question_id"])
        result = adaptive_test.submit_answer(
            result["session_id"], question["question_id"], full["correct_answer"], 20, bank
        )

    assert result["question_count"] == 2
    assert "标准误" in result["stop_reason"]


def test_profile_reuses_eap_and_reports_evidence_coverage():
    learners, _ = generate_all_mock_data()
    learner = learners[1]
    profile = build_profile(learner, KG)
    matrix = profile.knowledge_mastery

    responses = [
        (record.discrimination, record.difficulty, record.is_correct)
        for record in learner.test_records
    ]
    theta, standard_error, method = irt.estimate_eap_theta(
        responses, prior_theta=irt.education_prior_theta(learner.education.level)
    )

    assert matrix.estimation_method == method == "adaptivetesting-EAP"
    assert matrix.global_theta == round(theta, 2)
    assert matrix.standard_error == round(standard_error, 3)
    assert matrix.tested_kps == len({record.knowledge_point_id for record in learner.test_records})
    assert matrix.coverage_ratio == round(
        sum(point.mastery is not None for point in matrix.points.values()) / len(KG.points), 3
    )
    assert profile.ability_level.sub_dimensions["coding_ability"].score is None
    assert profile.ability_level.sub_dimensions["coding_ability"].level == "insufficient_evidence"

    for point in matrix.points.values():
        if point.test_count:
            assert point.standard_error is not None
            assert point.evidence_level in {"preliminary", "limited", "stable"}

    for domain, summary in matrix.domain_summary.items():
        points = [point for point in matrix.points.values() if point.domain == domain]
        assert summary.total_kps == len(points)
        assert summary.kps_covered == sum(point.mastery is not None for point in points)
        assert summary.tested_kps == sum(point.test_count > 0 for point in points)


def test_cat_exposes_selection_reason_and_calibration_status():
    bank = _small_bank()
    started = adaptive_test.start_session(
        "cat-metadata", 0.0, bank,
        adaptive_test.build_config({"max_questions": 3, "min_questions": 3, "min_kp_coverage": 3}),
    )
    assert started["selection_reason"] == "优先覆盖尚未测评的知识点"
    assert started["item_calibration_status"] == "provisional"


def test_cat_keeps_posterior_uncertainty_when_optional_library_is_unavailable(monkeypatch):
    bank = _small_bank()
    monkeypatch.setattr(irt, "_cat", None)
    started = adaptive_test.start_session(
        "cat-grid-eap", 0.0, bank,
        adaptive_test.build_config({"max_questions": 3, "min_questions": 3, "min_kp_coverage": 3}),
    )
    result = adaptive_test.submit_answer(
        started["session_id"], started["next_question"]["question_id"], 0, 10, bank
    )

    assert result["estimator_method"] == "grid-EAP"
    assert result["standard_error"] is not None
    assert result["standard_error"] > 0
