from skillforge_kb.platform.practice_review import review_practice_submission
from skillforge_kb.resources.controlled_generation import PracticeExercise


def _exercise() -> PracticeExercise:
    return PracticeExercise(
        language="python",
        task="将标量乘到向量的每个元素上，打印结果并保留断言验证输出长度，同时用注释说明每一步计算。",
        starter_code="s = -2.5\nv = [3, 0, -1]\n# TODO\nresult = []\nprint(result)\n",
        expected_output="[-7.5, -0.0, 2.5]",
        checks=("结果保留三个元素",),
        required_tokens=("s", "v", "result", "print"),
    )


def test_review_rejects_forbidden_import_without_executing_source() -> None:
    review = review_practice_submission(
        concept_id="math.linear-algebra.scalar",
        source="import subprocess\nsubprocess.run(['whoami'])",
        exercise=_exercise(),
    )

    assert review.accepted is False
    assert review.execution_performed is False
    assert "subprocess" in review.issues[0].message


def test_review_reports_missing_learning_tokens() -> None:
    review = review_practice_submission(
        concept_id="math.linear-algebra.scalar",
        source="result = [1, 2, 3]",
        exercise=_exercise(),
    )

    assert review.accepted is False
    assert review.missing_tokens == ("s", "v", "print")
    assert review.next_step


def test_review_accepts_complete_static_submission() -> None:
    review = review_practice_submission(
        concept_id="math.linear-algebra.scalar",
        source="s = -2.5\nv = [3, 0, -1]\nresult = [s * item for item in v]\nprint(result)",
        exercise=_exercise(),
    )

    assert review.accepted is True
    assert review.execution_performed is False
    assert review.next_step
