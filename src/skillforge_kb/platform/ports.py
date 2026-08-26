from datetime import datetime
from typing import Protocol

from skillforge_kb.agents.planning_agent_models import (
    CoursePlanningAgentResult,
    PlanningAgentEvent,
)
from skillforge_kb.agents.resource_agent import ResourceAgentResult
from skillforge_kb.agents.retrieval_agent_models import (
    DomainRetrievalRequest,
    DomainRetrievalResult,
)
from skillforge_kb.evaluation.knowledge_tracing import KnowledgeTracingObservation
from skillforge_kb.ontology.models import LearnerProfileSnapshot
from skillforge_kb.resources.evidence_bundle import EvidenceBundle
from skillforge_kb.resources.handoff import ResourceHandoffContract

from .models import PlatformRunRequest, PlatformRunResult


class PlanningAgentPort(Protocol):
    def invoke(
        self,
        event: PlanningAgentEvent,
        thread_id: str,
    ) -> CoursePlanningAgentResult: ...


class RetrievalAgentPort(Protocol):
    def retrieve(
        self,
        request: DomainRetrievalRequest,
        handoff: ResourceHandoffContract,
    ) -> DomainRetrievalResult: ...


class ResourceAgentPort(Protocol):
    def generate_strict(
        self,
        handoff: ResourceHandoffContract,
        bundle: EvidenceBundle,
    ) -> ResourceAgentResult: ...

    def generate_preview(
        self,
        profile: LearnerProfileSnapshot,
        handoff: ResourceHandoffContract,
        retrieval: DomainRetrievalResult,
    ) -> ResourceAgentResult: ...


class HandoffFactoryPort(Protocol):
    def build(
        self,
        planning: CoursePlanningAgentResult,
        profile: LearnerProfileSnapshot,
    ) -> ResourceHandoffContract: ...


class PlatformRunRepository(Protocol):
    def reserve(self, request: PlatformRunRequest) -> PlatformRunResult | None: ...

    def peek(self, request: PlatformRunRequest) -> PlatformRunResult | None: ...

    def save(self, result: PlatformRunResult) -> None: ...

    def get(self, run_id: str) -> PlatformRunResult | None: ...

    def get_request(self, run_id: str) -> PlatformRunRequest | None: ...

    def update_request(self, run_id: str, request: PlatformRunRequest) -> None: ...

    def get_assessment(
        self,
        run_id: str,
        assessment_id: str,
    ) -> tuple[str, PlatformRunResult] | None: ...

    def save_assessment(
        self,
        run_id: str,
        assessment_id: str,
        submission_digest: str,
        result: PlatformRunResult,
    ) -> None: ...

    def get_prediction_observation(
        self,
        run_id: str,
        assessment_id: str,
    ) -> KnowledgeTracingObservation | None: ...

    def save_prediction_observation(
        self,
        run_id: str,
        assessment_id: str,
        observation: KnowledgeTracingObservation,
    ) -> None: ...

    def list_prediction_observations(
        self,
        run_id: str,
    ) -> tuple[KnowledgeTracingObservation, ...]: ...

    def list_prediction_observations_for_profile(
        self,
        profile_id: str,
        *,
        model_version: str | None = None,
    ) -> tuple[KnowledgeTracingObservation, ...]: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
