import pytest

from skillforge_kb.platform.models import LearningProgress


def test_learning_progress_requires_all_learning_gates() -> None:
    incomplete = LearningProgress(concept_id="dl.cnn.convolution", lecture_completed=True)
    assert incomplete.can_complete is False
    complete = incomplete.model_copy(
        update={"practice_completed": True, "assessment_passed": True}
    )
    assert complete.can_complete is True
    assert complete.model_dump(mode="json")["can_complete"] is True


def test_learning_progress_rejects_inconsistent_assessment_state() -> None:
    with pytest.raises(ValueError, match="assessment"):
        LearningProgress(
            concept_id="dl.cnn.convolution",
            lecture_completed=True,
            practice_completed=True,
            assessment_passed=True,
            assessment_attempts=0,
        )


def test_resources_start_with_lecture_gate_recorded() -> None:
    progress = LearningProgress(concept_id="dl.cnn.convolution", lecture_completed=True)
    assert progress.practice_completed is False


def test_lecture_progress_requires_eighty_percent_to_complete() -> None:
    progress = LearningProgress(
        concept_id="dl.cnn.convolution",
        lecture_progress=0.79,
    )
    assert progress.lecture_completed is False
    completed = LearningProgress(
        concept_id="dl.cnn.convolution",
        lecture_progress=0.80,
    )
    assert completed.lecture_completed is True


def test_assessment_passing_score_is_server_controlled() -> None:
    from pydantic import ValidationError

    from skillforge_kb.platform.models import AssessmentSubmission

    with pytest.raises(ValidationError, match="passing score"):
        AssessmentSubmission(
            assessment_id="a-1",
            concept_id="dl.cnn.convolution",
            score=0.0,
            passing_score=0.0,
            response_time_ms=1,
            hint_count=0,
            attempt_count=1,
        )


def test_lecture_progress_cannot_jump_more_than_twenty_five_percent() -> None:
    progress = LearningProgress(
        concept_id="dl.cnn.convolution",
        lecture_progress=0.0,
    )
    assert progress.max_next_lecture_progress == 0.25
