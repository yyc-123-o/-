import json

import pytest

from skillforge_kb.agents.assessment_feedback import (
    AssessmentAnswer,
    AssessmentFeedbackAgent,
    build_intro_cnn_blueprint,
    export_feedback,
)


@pytest.fixture
def blueprint():
    return build_intro_cnn_blueprint(
        ("解释卷积。", "计算输出尺寸。", "阅读 Conv2d 代码。")
    )


def test_low_score_generates_remediation_focus(blueprint) -> None:
    feedback = AssessmentFeedbackAgent().evaluate(
        blueprint,
        (
            AssessmentAnswer("cnn-c01", False),
            AssessmentAnswer("cnn-s01", False),
            AssessmentAnswer("cnn-p01", False),
            AssessmentAnswer("cnn-c02", True),
        ),
        current_depth="intro",
    )

    assert feedback.status == "remediate"
    assert feedback.recommended_depth == "intro"
    assert feedback.error_distribution["concept_confusion"] == 1
    assert feedback.error_distribution["calculation_error"] == 1
    assert feedback.path_mutation_requested is False


def test_high_score_requests_planning_review_instead_of_changing_path(blueprint) -> None:
    answers = tuple(AssessmentAnswer(item.question_id, True) for item in blueprint)

    feedback = AssessmentFeedbackAgent().evaluate(blueprint, answers, current_depth="intro")

    assert feedback.status == "request_planning_review"
    assert feedback.recommended_depth == "intermediate"
    assert feedback.requires_planning_recheck is True
    assert feedback.path_mutation_requested is False


def test_unknown_question_is_rejected(blueprint) -> None:
    with pytest.raises(ValueError, match="unknown question ID"):
        AssessmentFeedbackAgent().evaluate(
            blueprint,
            (AssessmentAnswer("not-in-blueprint", False),),
            current_depth="intro",
        )


def test_feedback_export_is_machine_readable(tmp_path, blueprint) -> None:
    feedback = AssessmentFeedbackAgent().evaluate(
        blueprint,
        (AssessmentAnswer("cnn-c01", True),),
        current_depth="intro",
    )

    path = export_feedback(feedback, tmp_path / "assessment_feedback.json")

    assert (
        json.loads(path.read_text(encoding="utf-8"))["status"]
        == "request_planning_review"
    )
