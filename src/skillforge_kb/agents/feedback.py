from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skillforge_kb.assessment.update import (
    AssessmentEvent,
    AssessmentLedger,
    AssessmentPolicy,
    apply_assessment_event,
)
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import LearnerProfileSnapshot

from .planning_agent_models import PlanningAgentEvent, PlanningEventKind


class PlanningFeedbackResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["planning-feedback-result.v1"] = (
        "planning-feedback-result.v1"
    )
    ledger: AssessmentLedger
    applied: bool
    affected_concept_ids: tuple[str, ...] = ()
    assessment_event_digest: str = Field(min_length=1)
    planning_event: PlanningAgentEvent | None = None

    @property
    def profile(self) -> LearnerProfileSnapshot:
        return self.ledger.profile

    @model_validator(mode="after")
    def validate_event_transition(self) -> "PlanningFeedbackResult":
        if self.applied and self.planning_event is None:
            raise ValueError("applied feedback requires a planning event")
        if not self.applied and self.planning_event is not None:
            raise ValueError("duplicate feedback cannot emit a planning event")
        if self.planning_event is not None:
            if self.planning_event.kind is not PlanningEventKind.PROFILE_REFRESHED:
                raise ValueError("feedback must emit a profile refresh event")
            if self.planning_event.profile != self.ledger.profile:
                raise ValueError("planning event profile does not match ledger")
        return self


class PlanningFeedbackCoordinator:
    """Connect assessment updates to the planner without owning estimation logic."""

    def __init__(
        self,
        catalog: OntologyCatalog,
        assessment_policy: AssessmentPolicy | None = None,
    ) -> None:
        self._catalog = catalog
        self._assessment_policy = assessment_policy

    def apply(
        self,
        ledger: AssessmentLedger,
        event: AssessmentEvent,
    ) -> PlanningFeedbackResult:
        update = apply_assessment_event(
            self._catalog,
            ledger,
            event,
            self._assessment_policy,
        )
        planning_event = None
        if update.applied:
            planning_event = PlanningAgentEvent(
                event_id=_planning_event_id(update.event_digest),
                kind=PlanningEventKind.PROFILE_REFRESHED,
                profile=update.ledger.profile,
            )
        return PlanningFeedbackResult(
            ledger=update.ledger,
            applied=update.applied,
            affected_concept_ids=update.affected_concept_ids,
            assessment_event_digest=update.event_digest,
            planning_event=planning_event,
        )


def _planning_event_id(assessment_event_digest: str) -> str:
    return f"event_{sha256(assessment_event_digest.encode('utf-8')).hexdigest()}"
