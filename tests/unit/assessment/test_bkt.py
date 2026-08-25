import pytest
from pydantic import ValidationError

from skillforge_kb.assessment.bkt import BktParameters, update_bkt_probability


def test_default_parameters_and_first_observations() -> None:
    params = BktParameters()

    assert params.p_l0 == pytest.approx(0.2)
    assert update_bkt_probability(params.p_l0, True, params) == pytest.approx(
        0.5764705882
    )
    assert update_bkt_probability(params.p_l0, False, params) == pytest.approx(
        0.1272727273
    )


def test_parameters_reject_invalid_probability_combinations() -> None:
    with pytest.raises(ValidationError):
        BktParameters(p_l0=1.1)
    with pytest.raises(ValidationError, match="guess and slip"):
        BktParameters(p_guess=0.9, p_slip=0.1)


def test_repeated_correct_answers_increase_and_wrong_answers_decrease() -> None:
    params = BktParameters()
    correct = params.p_l0
    wrong = params.p_l0
    correct_values: list[float] = []
    wrong_values: list[float] = []

    for _ in range(4):
        correct = update_bkt_probability(correct, True, params)
        wrong = update_bkt_probability(wrong, False, params)
        correct_values.append(correct)
        wrong_values.append(wrong)

    assert correct_values == sorted(correct_values)
    assert wrong_values == sorted(wrong_values, reverse=True)
    assert all(0 <= value <= 1 for value in (*correct_values, *wrong_values))
