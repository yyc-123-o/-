from pydantic import BaseModel, ConfigDict, Field, model_validator


class BktParameters(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    p_l0: float = Field(default=0.2, ge=0, le=1)
    p_transition: float = Field(default=0.1, ge=0, le=1)
    p_guess: float = Field(default=0.2, ge=0, le=1)
    p_slip: float = Field(default=0.1, ge=0, le=1)
    model_version: str = Field(default="bkt.v1", min_length=1)
    parameter_version: str = Field(default="bkt-default.v1", min_length=1)

    @model_validator(mode="after")
    def validate_observation_parameters(self) -> "BktParameters":
        if self.p_guess + self.p_slip >= 1:
            raise ValueError("guess and slip probabilities must sum to less than 1")
        return self


def update_bkt_probability(
    prior_mastery: float,
    correct: bool,
    parameters: BktParameters,
) -> float:
    if not 0 <= prior_mastery <= 1:
        raise ValueError("prior mastery must be between 0 and 1")
    params = BktParameters.model_validate(parameters.model_dump())
    p = _clamp(prior_mastery)
    if correct:
        numerator = p * (1 - params.p_slip)
        denominator = numerator + (1 - p) * params.p_guess
    else:
        numerator = p * params.p_slip
        denominator = numerator + (1 - p) * (1 - params.p_guess)
    if denominator == 0:
        raise ValueError("BKT observation denominator must be positive")
    posterior = _clamp(numerator / denominator)
    return _clamp(posterior + (1 - posterior) * params.p_transition)


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
