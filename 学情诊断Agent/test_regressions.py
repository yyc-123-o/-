from pathlib import Path

import numpy as np
import yaml

from core import adaptive_test
from core.profile_builder import build_profile
from generators.mock_generator import generate_test_bank
from models.knowledge_graph import KG
from models.schemas import Education, Learner, SelfAssessment


def _blank_learner() -> Learner:
    return Learner(
        id="regression-blank",
        name="待测学生",
        education=Education(level="本科", major="计算机"),
        self_assessment=SelfAssessment(learning_goal="系统学习 AI", weekly_hours=6),
    )


def test_blank_profile_has_no_fabricated_history_or_cnn_evidence() -> None:
    profile = build_profile(_blank_learner(), KG, current_chapter_id="ch06_transformer")

    assert profile.prior_chapters == []
    assert all("CNN" not in item.claim for item in profile.evidence)
    assert all(point.mastery is None for point in profile.knowledge_mastery.points.values())
    assert profile.resource_generation_hints.target_chapter_id == "ch06_transformer"
    assert profile.resource_generation_hints.lecture_notes.must_include
    assert profile.resource_generation_hints.practical_guide.must_include
    assert profile.resource_generation_hints.test_questions.must_cover


def test_profile_agent_mapping_covers_every_legacy_knowledge_point() -> None:
    mapping_path = Path(__file__).parents[1] / "resources" / "ontology" / "profile_agent_kp_map_v1.yaml"
    mapping = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    legacy_ids = {point.id for point in KG.points}
    covered_ids = set(mapping.get("mappings", {})) | set(mapping.get("expansions", {}))

    assert legacy_ids <= covered_ids


def test_adaptive_test_honors_domain_filter_and_uses_answer_history_for_theta() -> None:
    bank = generate_test_bank(KG, np.random.default_rng(4))
    config = adaptive_test.build_config(
        {"domains": ["数学基础"], "max_questions": 2, "min_questions": 1}
    )
    result = adaptive_test.start_session("regression-adaptive", 0.0, bank, config=config)
    assert result["bank_size"] > 0
    assert result["next_question"]["domain"] == "数学基础"

    question = result["next_question"]
    full_question = next(item for item in bank if item["question_id"] == question["question_id"])
    answered = adaptive_test.submit_answer(
        result["session_id"],
        question["question_id"],
        full_question["correct_answer"],
        30,
        bank,
    )
    assert answered["current_theta"] != 0.0
