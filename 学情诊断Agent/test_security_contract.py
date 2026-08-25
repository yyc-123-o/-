"""学生端自适应测试题目的安全契约回归测试。"""

from core import adaptive_test


def _bank() -> list[dict]:
    return [
        {
            "question_id": "q-1",
            "knowledge_point_id": "kp-1",
            "knowledge_point_name": "梯度",
            "difficulty": -1.0,
            "discrimination": 1.0,
            "question_text": "梯度下降沿哪个方向更新？",
            "options": ["负梯度", "正梯度"],
            "correct_answer": 0,
            "explanation": "负梯度方向使目标函数下降最快。",
        },
        {
            "question_id": "q-2",
            "knowledge_point_id": "kp-1",
            "knowledge_point_name": "梯度",
            "difficulty": -0.9,
            "discrimination": 1.0,
            "question_text": "梯度表示什么？",
            "options": ["最速上升方向", "随机方向"],
            "correct_answer": 0,
            "explanation": "梯度是函数最速上升方向。",
        },
    ]


def test_student_question_omits_answer_and_explanation() -> None:
    adaptive_test._sessions.clear()

    result = adaptive_test.start_session("learner-1", 0.0, _bank())

    assert "correct_answer" not in result["next_question"]
    assert "explanation" not in result["next_question"]


def test_server_scores_selected_answer_without_exposing_answer() -> None:
    adaptive_test._sessions.clear()
    bank = _bank()
    started = adaptive_test.start_session("learner-1", 0.0, bank)
    question = started["next_question"]

    result = adaptive_test.submit_answer(
        started["session_id"],
        question["question_id"],
        selected_answer=1,
        time_spent=10,
        test_bank=bank,
    )

    assert result["last_correct"] is False
    assert "correct_answer" not in result["next_question"]
