"""Turn a generated assessment attempt into a safe resource-regeneration hint.

This Agent does not promote a learner or mutate a course path. It only turns
observable answers into an auditable recommendation for the resource generator
and, for strong performance, asks the planning Agent to re-evaluate depth.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

FeedbackStatus = Literal["remediate", "continue", "request_planning_review"]


@dataclass(frozen=True)
class AssessmentItem:
    question_id: str
    category: Literal["concept", "calculation", "code_reading"]
    error_category: Literal[
        "concept_confusion",
        "calculation_error",
        "logic_jump",
        "code_shape_error",
        "condition_omission",
    ]
    learning_outcome: str
    difficulty: Literal["easy", "medium", "hard"]


@dataclass(frozen=True)
class AssessmentAnswer:
    question_id: str
    correct: bool


@dataclass(frozen=True)
class AssessmentFeedback:
    status: FeedbackStatus
    score: float
    correct_count: int
    total_count: int
    error_distribution: dict[str, int]
    next_resource_focus: tuple[str, ...]
    recommended_depth: str
    requires_planning_recheck: bool
    path_mutation_requested: Literal[False] = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class AssessmentFeedbackAgent:
    """Evaluate answers against an immutable assessment blueprint."""

    def evaluate(
        self,
        blueprint: tuple[AssessmentItem, ...],
        answers: tuple[AssessmentAnswer, ...],
        *,
        current_depth: str,
    ) -> AssessmentFeedback:
        item_by_id = {item.question_id: item for item in blueprint}
        if len(item_by_id) != len(blueprint):
            raise ValueError("assessment blueprint has duplicate question IDs")
        answer_ids = [answer.question_id for answer in answers]
        if len(answer_ids) != len(set(answer_ids)):
            raise ValueError("assessment attempt has duplicate question IDs")
        unknown = sorted(set(answer_ids) - set(item_by_id))
        if unknown:
            raise ValueError(f"assessment attempt has unknown question ID: {unknown[0]}")
        if not answers:
            raise ValueError("assessment attempt cannot be empty")

        incorrect = [answer for answer in answers if not answer.correct]
        error_distribution = Counter(
            item_by_id[answer.question_id].error_category for answer in incorrect
        )
        score = sum(answer.correct for answer in answers) / len(answers)
        focus = tuple(category for category, _ in error_distribution.most_common())
        if score < 0.60:
            status: FeedbackStatus = "remediate"
            recommended_depth = current_depth
            requires_planning_recheck = False
        elif score < 0.85:
            status = "continue"
            recommended_depth = current_depth
            requires_planning_recheck = False
        else:
            status = "request_planning_review"
            recommended_depth = _next_depth_candidate(current_depth)
            requires_planning_recheck = True

        return AssessmentFeedback(
            status=status,
            score=round(score, 3),
            correct_count=len(answers) - len(incorrect),
            total_count=len(answers),
            error_distribution=dict(error_distribution),
            next_resource_focus=focus or ("consolidation",),
            recommended_depth=recommended_depth,
            requires_planning_recheck=requires_planning_recheck,
        )


def build_intro_cnn_blueprint(learning_outcomes: tuple[str, ...]) -> tuple[AssessmentItem, ...]:
    """Build the fixed eight-item blueprint promised by the intro handoff."""
    outcomes = learning_outcomes or (
        "解释卷积运算的核心含义。",
        "计算卷积输出尺寸。",
        "在 PyTorch 中读取 Conv2d 示例。",
    )
    return (
        AssessmentItem(
            question_id="cnn-c01",
            category="concept",
            error_category="concept_confusion",
            learning_outcome=outcomes[0],
            difficulty="easy",
        ),
        AssessmentItem(
            question_id="cnn-c02",
            category="concept",
            error_category="concept_confusion",
            learning_outcome=outcomes[0],
            difficulty="medium",
        ),
        AssessmentItem(
            question_id="cnn-c03",
            category="concept",
            error_category="logic_jump",
            learning_outcome=outcomes[0],
            difficulty="medium",
        ),
        AssessmentItem(
            question_id="cnn-s01",
            category="calculation",
            error_category="calculation_error",
            learning_outcome=outcomes[min(1, len(outcomes) - 1)],
            difficulty="easy",
        ),
        AssessmentItem(
            question_id="cnn-s02",
            category="calculation",
            error_category="calculation_error",
            learning_outcome=outcomes[min(1, len(outcomes) - 1)],
            difficulty="medium",
        ),
        AssessmentItem(
            question_id="cnn-s03",
            category="calculation",
            error_category="condition_omission",
            learning_outcome=outcomes[min(1, len(outcomes) - 1)],
            difficulty="hard",
        ),
        AssessmentItem(
            question_id="cnn-p01",
            category="code_reading",
            error_category="code_shape_error",
            learning_outcome=outcomes[min(2, len(outcomes) - 1)],
            difficulty="medium",
        ),
        AssessmentItem(
            question_id="cnn-p02",
            category="code_reading",
            error_category="code_shape_error",
            learning_outcome=outcomes[min(2, len(outcomes) - 1)],
            difficulty="hard",
        ),
    )


def blueprint_to_dict(blueprint: tuple[AssessmentItem, ...]) -> list[dict[str, object]]:
    return [asdict(item) for item in blueprint]


def export_feedback(feedback: AssessmentFeedback, output_path: str | Path) -> Path:
    """Write a feedback result that the next resource-generation run can consume."""
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(feedback.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _next_depth_candidate(current_depth: str) -> str:
    order = ("intro", "intermediate", "advanced")
    try:
        return order[min(order.index(current_depth) + 1, len(order) - 1)]
    except ValueError:
        return current_depth
