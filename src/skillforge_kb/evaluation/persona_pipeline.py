"""Additive multi-Agent evaluation pipelines for one learner profile.

This module composes the already-published Agent building blocks -- it never
changes planning, retrieval, resource, or platform behavior -- in two shapes:

``run_persona_pipeline`` -- one straight pass:

    diagnosis profile (raw v2.1 or canonical)
        -> LearnerProfileAgentAdapter          (学情诊断 Agent bridge)
        -> CoursePlanningAgent                 (课程规划 Agent, full path in one shot)
        -> per personalized node, in path order:
             DomainRetrievalAgent.retrieve      (领域检索 Agent)
             ResourceGenerationAgent.generate_* (资源生成 Agent, formal or candidate preview)

``run_persona_feedback_loop`` -- the same Agents, but closing the loop one
node at a time so the path/depth visibly react to simulated answers:

    diagnosis profile -> LearnerProfileAgentAdapter -> CoursePlanningAgent (INITIALIZE)
        -> repeat for the current node until the course completes:
             DomainRetrievalAgent.retrieve + ResourceGenerationAgent.generate_*
             -> simulate one answer
             -> assessment.apply_assessment_event    (same rule-based ledger the platform uses)
             -> CoursePlanningAgent (PROFILE_REFRESHED, same thread)
             -> CoursePlanningAgent (CONCEPTS_COMPLETED, same thread, advance to the next node)

Both are intentionally separate from ``platform/graph.py`` (the live,
stateful, checkpointed service) so offline evaluation runs never touch
production platform state (``SKILLFORGE_PLATFORM_STATE_DB``).

The result of either is a single deterministic snapshot per learner profile
that later evaluation modules (path accuracy, knowledge-base coverage,
resource quality) can consume without re-running the pipeline.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from skillforge_kb.agents.planning_agent import CoursePlanningAgent
from skillforge_kb.agents.planning_agent_models import (
    CoursePlanningAgentResult,
    PlanningAgentEvent,
    PlanningAgentStatus,
    PlanningEventKind,
)
from skillforge_kb.agents.resource_agent import (
    ResourceAgentResult,
    ResourceGenerationAgent,
)
from skillforge_kb.agents.retrieval_agent import DomainRetrievalAgent
from skillforge_kb.agents.retrieval_agent_models import (
    DomainRetrievalRequest,
    DomainRetrievalResult,
)
from skillforge_kb.assessment import (
    AssessmentEvent,
    AssessmentLedger,
    AssessmentUpdateResult,
    apply_assessment_event,
)
from skillforge_kb.config import Settings
from skillforge_kb.domain.enums import ContentKind
from skillforge_kb.evidence.manifest import EvidenceIndex, load_evidence_index
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.concept_attributes import load_concept_attributes
from skillforge_kb.ontology.models import DepthLevel, LearnerProfileSnapshot
from skillforge_kb.ontology.profile_agent_adapter import LearnerProfileAgentAdapter
from skillforge_kb.ontology.resource_blueprints import (
    ResourceBlueprintCatalog,
    load_resource_blueprints,
)
from skillforge_kb.ontology.validation import validate_catalog
from skillforge_kb.planning.models import PathDecision, PathNode, PathStatus, ReasonCode
from skillforge_kb.platform.models import ASSESSMENT_PASSING_SCORE
from skillforge_kb.platform.runtime import (
    DefaultPlatformPaths,
    validate_default_platform_paths,
)
from skillforge_kb.resources.briefs import ResourceBriefBuilder
from skillforge_kb.resources.controlled_generation import OpenAICompatibleLLMAdapter
from skillforge_kb.resources.evidence_bundle import build_evidence_bundle
from skillforge_kb.resources.handoff import ResourceHandoffContract
from skillforge_kb.resources.models import GenerationGateStatus
from skillforge_kb.retrieval.bm25 import Bm25KnowledgeRetriever
from skillforge_kb.retrieval.corpus import KnowledgeCorpus
from skillforge_kb.retrieval.tool import KnowledgeRetrievalTool

DEFAULT_FEEDBACK_RESPONSE_TIME_MS = 45_000

PERSONA_PIPELINE_SCHEMA_VERSION = "persona-pipeline-snapshot.v1"

ResourceMode = Literal[
    "formal",
    "candidate_draft",
    "blocked_hard_prerequisite",
    "not_attempted",
]


@dataclass(frozen=True)
class PersonaPipelineContext:
    """One composed, read-only pipeline: catalog + the four Agent building blocks.

    Built once per process and reused across profiles. Never opens the live
    platform SQLite state database, so running persona/cohort evaluations has
    no side effect on ``platform-serve``.
    """

    catalog: OntologyCatalog
    evidence_index: EvidenceIndex
    blueprints: ResourceBlueprintCatalog
    profile_adapter: LearnerProfileAgentAdapter
    retrieval_agent: DomainRetrievalAgent
    resource_agent: ResourceGenerationAgent
    planning_agent: CoursePlanningAgent


class NodeEvidenceSummary(BaseModel):
    """Knowledge-base matching signal for one path node (§5 of the workplan)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    formal_evidence_count: int = Field(ge=0)
    candidate_evidence_count: int = Field(ge=0)
    definition_available: bool
    code_available: bool
    exercise_available: bool
    highest_retrieval_score: float = Field(ge=0)
    review_status: Literal["published", "unreviewed"]
    license_status: Literal["allowed", "unknown"]


class NodeGenerationGate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: bool
    status: GenerationGateStatus
    blocking_codes: tuple[str, ...]
    next_action: str | None = None


class PersonaPathNodeRecord(BaseModel):
    """One full-path node plus (for personalized nodes) its retrieval/resource run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    concept_id: str
    title: str | None = None
    chapter_id: str
    section_id: str
    sequence: int = Field(ge=1)
    status: PathStatus
    delivery_depth: DepthLevel | None
    reason_codes: tuple[ReasonCode, ...] = ()
    generation_gate: NodeGenerationGate | None = None
    retrieval_result: DomainRetrievalResult | None = None
    retrieval_error: str | None = None
    evidence_summary: NodeEvidenceSummary | None = None
    resource_mode: ResourceMode = "not_attempted"
    resource_result: ResourceAgentResult | None = None
    resource_error: str | None = None


class FeedbackRoundRecord(BaseModel):
    """One simulated 学习反馈 round in :func:`run_persona_feedback_loop`.

    Produced by the same ``rule-based-assessment.v1`` ledger
    (``skillforge_kb.assessment.apply_assessment_event``) the live platform
    uses for real answer submissions -- this is a simulated answer, not a
    different update mechanism.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    round_index: int = Field(ge=0)
    concept_id: str
    simulated_correct: bool
    mastery_before: float | None = None
    mastery_after: float | None = None
    classified_error_kind: str | None = None
    reason_codes: tuple[str, ...] = ()


class PersonaPipelineSnapshot(BaseModel):
    """Complete linear-pipeline run for one learner profile.

    Field names deliberately mirror the workplan
    (``full_path``/``personalized_path_concept_ids``/``skip_reasons``/``node_depths``)
    so later cohort- and persona-level reporting can consume this directly.

    Caveat: any embedded ``candidate_draft`` ``resource_result`` carries a
    ``ResourceAgentResult`` whose JSON-mode dump deliberately strips
    teacher-only content (``teacher_guide``, quiz ``correct_choice``) -- see
    ``ResourceAgentResult.serialize_public``. That means
    ``model_dump(mode="json")`` / ``model_dump_json()`` output (including the
    file written by ``dump_persona_pipeline_snapshot``) is not guaranteed to
    round-trip back through ``model_validate_json`` whenever the snapshot
    contains a candidate preview -- which, with an empty evidence manifest, is
    most personalized nodes today. In-process callers that need full fidelity
    should use ``model_dump(mode="python")`` / ``model_validate`` instead; the
    persisted JSON file itself stays intentionally redacted, matching the same
    privacy contract the live platform API already applies to this type.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["persona-pipeline-snapshot.v1"] = (
        "persona-pipeline-snapshot.v1"
    )
    generated_at: datetime
    profile_id: str
    learner_ref: str
    source_profile_version: str
    adapter_warnings: tuple[str, ...] = ()
    target_concept_id: str | None = None
    path_id: str | None = None
    graph_version: str | None = None
    policy_version: str | None = None
    full_path: tuple[PersonaPathNodeRecord, ...] = ()
    personalized_path_concept_ids: tuple[str, ...] = ()
    skipped_concept_ids: tuple[str, ...] = ()
    skip_reasons: dict[str, tuple[ReasonCode, ...]] = Field(default_factory=dict)
    node_depths: dict[str, str | None] = Field(default_factory=dict)
    feedback_rounds: tuple[FeedbackRoundRecord, ...] = ()
    pipeline_failure: str | None = None
    snapshot_digest: str


def build_persona_pipeline_context(project_root: Path) -> PersonaPipelineContext:
    """Compose catalog + Agents the same way ``platform-serve`` does.

    Reuses ``platform.runtime``'s path resolution so the two stay in lockstep,
    but never opens the live platform SQLite state database.
    """

    root = project_root.expanduser().resolve()
    paths = DefaultPlatformPaths.from_project_root(root)
    validate_default_platform_paths(paths)
    catalog = OntologyCatalog.load(paths.course_file, paths.relations_file)
    validate_catalog(catalog)
    attributes = load_concept_attributes(catalog, paths.attributes_file)
    blueprints = load_resource_blueprints(catalog, paths.blueprints_file)
    evidence_index = load_evidence_index(catalog, paths.evidence_file)
    corpus = KnowledgeCorpus.load_many((paths.knowledge_file,))
    retrieval_agent = DomainRetrievalAgent(
        corpus,
        KnowledgeRetrievalTool(Bm25KnowledgeRetriever(corpus)),
        evidence_index,
        catalog=catalog,
    )
    settings = Settings()
    llm_adapter = (
        OpenAICompatibleLLMAdapter(
            base_url=cast(str, settings.llm_base_url),
            api_key=cast(SecretStr, settings.llm_api_key),
            model_name=cast(str, settings.llm_model),
            timeout_seconds=settings.llm_timeout_seconds,
        )
        if settings.llm_configured
        else None
    )
    profile_adapter = LearnerProfileAgentAdapter.load_mappings(
        catalog,
        paths.profile_agent_map_file,
    )
    # Built once and reused across every ``run_persona_pipeline`` call in this
    # process (e.g. a cohort of personas/real profiles). Its in-memory
    # checkpointer is keyed by ``thread_id``, which ``run_persona_pipeline``
    # derives from ``profile.profile_id``, so distinct profiles never share
    # planning state even though they share this one compiled graph.
    planning_agent = CoursePlanningAgent.create(catalog, attributes)

    return PersonaPipelineContext(
        catalog=catalog,
        evidence_index=evidence_index,
        blueprints=blueprints,
        profile_adapter=profile_adapter,
        retrieval_agent=retrieval_agent,
        resource_agent=ResourceGenerationAgent(llm_adapter=llm_adapter),
        planning_agent=planning_agent,
    )


def _adapt_profile(
    context: PersonaPipelineContext,
    raw_profile: Mapping[str, object],
) -> tuple[LearnerProfileSnapshot, str, str | None, tuple[str, ...]]:
    """Diagnosis-Agent bridge step. Accepts a raw v2.1 payload or a canonical snapshot."""

    profile_version = raw_profile.get("profile_version")
    if profile_version == "2.1":
        adapted = context.profile_adapter.adapt(raw_profile)
        warnings = tuple(f"{item.legacy_id}: {item.reason}" for item in adapted.warnings)
        return (
            adapted.snapshot,
            adapted.source_profile_version,
            adapted.suggested_target_concept_id,
            warnings,
        )
    snapshot = LearnerProfileSnapshot.model_validate(raw_profile)
    return snapshot, str(profile_version or snapshot.schema_version), None, ()


def _build_retrieval_scope(catalog: OntologyCatalog, handoff: ResourceHandoffContract) -> str:
    """Bilingual BM25 query scope for one node (mirrors platform/graph.py)."""

    try:
        concept = catalog.get_concept(handoff.concept_id)
        section = catalog.section_for(handoff.concept_id)
    except (KeyError, ValueError):
        return (
            f"{handoff.concept_id} {handoff.chapter_id} "
            f"{handoff.section_id} {handoff.delivery_depth.value}"
        )
    parts = [
        concept.names.zh,
        concept.names.en,
        *concept.aliases,
        concept.summary,
        section.title.zh,
        handoff.concept_id,
        handoff.delivery_depth.value,
    ]
    return " ".join(part for part in parts if part)


def _evidence_summary(retrieval: DomainRetrievalResult) -> NodeEvidenceSummary:
    formal_kinds = {item.content_kind for item in retrieval.evidence}
    scores = [item.score for item in (*retrieval.evidence, *retrieval.candidate_evidence)]
    return NodeEvidenceSummary(
        formal_evidence_count=retrieval.evidence_summary.formal_count,
        candidate_evidence_count=retrieval.evidence_summary.candidate_count,
        definition_available=ContentKind.DEFINITION in formal_kinds,
        code_available=ContentKind.CODE in formal_kinds,
        exercise_available=ContentKind.EXERCISE in formal_kinds,
        highest_retrieval_score=max(scores) if scores else 0.0,
        review_status="published" if retrieval.evidence_summary.formal_count else "unreviewed",
        license_status="allowed" if retrieval.evidence_summary.formal_count else "unknown",
    )


def _bare_node_record(node: PathNode) -> PersonaPathNodeRecord:
    """A path node no retrieval/resource step was attempted for -- either it is
    skipped/mastered, or (in the feedback loop) the simulated run had not
    reached it yet when the loop stopped."""

    return PersonaPathNodeRecord(
        concept_id=node.concept_id,
        title=node.title,
        chapter_id=node.chapter_id,
        section_id=node.section_id,
        sequence=node.sequence,
        status=node.status,
        delivery_depth=node.delivery_depth,
        reason_codes=node.reason_codes,
    )


def _process_personalized_node(
    context: PersonaPipelineContext,
    decision: PathDecision,
    profile: LearnerProfileSnapshot,
    node: PathNode,
    brief_builder: ResourceBriefBuilder,
    top_k: int,
) -> PersonaPathNodeRecord:
    """Retrieval + resource-generation Agent decision for one unfinished node.

    Shared by the single-pass :func:`run_persona_pipeline` and the multi-round
    :func:`run_persona_feedback_loop` so the two never drift.
    """

    handoff = brief_builder.build_handoff(decision, profile, node.concept_id)
    gate = NodeGenerationGate(
        allowed=handoff.generation_gate.allowed,
        status=handoff.generation_gate.status,
        blocking_codes=handoff.generation_gate.blocking_codes,
        next_action=handoff.generation_gate.next_action,
    )

    scope = _build_retrieval_scope(context.catalog, handoff)
    retrieval_request = DomainRetrievalRequest(
        original_query=f"{handoff.concept_id} {handoff.delivery_depth.value}",
        rewritten_queries=(
            f"{scope} 定义 概念 解释 是什么",
            f"{scope} 代码 实现 示例 参数",
            f"{scope} 练习 习题 评估 例题",
        ),
        profile_id=handoff.profile_id,
        concept_id=handoff.concept_id,
        depth=handoff.delivery_depth,
        top_k=top_k,
    )
    retrieval: DomainRetrievalResult | None = None
    retrieval_error: str | None = None
    evidence_summary: NodeEvidenceSummary | None = None
    try:
        retrieval = context.retrieval_agent.retrieve(retrieval_request, handoff)
        evidence_summary = _evidence_summary(retrieval)
    except Exception as exc:  # noqa: BLE001 - keep the linear run alive per node
        # Mirrors the resource-generation isolation below: one concept's
        # retrieval defect (e.g. a corpus/index quirk for that node) must
        # not abort the whole persona run. Record it so it shows up in
        # knowledge-base-coverage reporting instead of silently vanishing.
        retrieval_error = f"{type(exc).__name__}: {exc}"

    resource_mode: ResourceMode = "not_attempted"
    resource_result: ResourceAgentResult | None = None
    resource_error: str | None = None
    if retrieval is not None:
        blockers = set(handoff.generation_gate.blocking_codes)
        try:
            if gate.allowed:
                bundle = build_evidence_bundle(handoff, context.evidence_index)
                resource_result = context.resource_agent.generate_strict(handoff, bundle)
                resource_mode = "formal"
            elif blockers == {"blocked_missing_published_evidence"}:
                resource_result = context.resource_agent.generate_preview(
                    profile, handoff, retrieval
                )
                resource_mode = "candidate_draft"
            elif "blocked_hard_prerequisite" in blockers:
                resource_mode = "blocked_hard_prerequisite"
        except Exception as exc:  # noqa: BLE001 - keep the linear run alive per node
            # The strict/preview generators are existing, separately-owned Agent
            # code; a per-concept generation defect must not abort the whole
            # persona run. Record it so it shows up in resource-quality reporting
            # instead of silently disappearing.
            resource_result = None
            resource_error = f"{type(exc).__name__}: {exc}"

    return PersonaPathNodeRecord(
        concept_id=node.concept_id,
        title=node.title,
        chapter_id=node.chapter_id,
        section_id=node.section_id,
        sequence=node.sequence,
        status=node.status,
        delivery_depth=node.delivery_depth,
        reason_codes=node.reason_codes,
        generation_gate=gate,
        retrieval_result=retrieval,
        retrieval_error=retrieval_error,
        evidence_summary=evidence_summary,
        resource_mode=resource_mode,
        resource_result=resource_result,
        resource_error=resource_error,
    )


def build_persona_snapshot_digest(
    profile_id: str,
    path_id: str,
    node_concept_ids: Iterable[str],
    personalized_ids: Iterable[str],
) -> str:
    """Public so :mod:`persona_verification` can recompute and cross-check it
    from a plain (already-parsed) snapshot dict, not just a live run."""

    payload = {
        "profile_id": profile_id,
        "path_id": path_id,
        "nodes": list(node_concept_ids),
        "personalized": list(personalized_ids),
    }
    digest = sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    return f"persona_pipeline_{digest}"


def _empty_snapshot(
    *,
    generated_at: datetime,
    snapshot: LearnerProfileSnapshot,
    source_version: str,
    target_concept_id: str | None,
    warnings: tuple[str, ...],
    failure: str,
    feedback_rounds: tuple[FeedbackRoundRecord, ...] = (),
) -> PersonaPipelineSnapshot:
    empty_digest = sha256(f"{snapshot.profile_id}:{failure}".encode()).hexdigest()
    return PersonaPipelineSnapshot(
        generated_at=generated_at,
        profile_id=snapshot.profile_id,
        learner_ref=snapshot.learner_ref,
        source_profile_version=source_version,
        adapter_warnings=warnings,
        target_concept_id=target_concept_id,
        feedback_rounds=feedback_rounds,
        pipeline_failure=failure,
        snapshot_digest=f"persona_pipeline_{empty_digest}",
    )


def run_persona_pipeline(
    context: PersonaPipelineContext,
    raw_profile: Mapping[str, object],
    *,
    top_k: int = 5,
) -> PersonaPipelineSnapshot:
    """Run the linear diagnosis -> planning -> retrieval -> resource pipeline once.

    This is a single pass: it plans once, and previews retrieval/resource
    generation for every personalized node as it stands right now. It never
    simulates completing a node or advances the path. For a multi-round run
    that actually completes nodes one at a time and lets mastery updates
    reshape the remaining path, see :func:`run_persona_feedback_loop`.
    """

    generated_at = datetime.now(UTC)
    snapshot, source_version, target_concept_id, warnings = _adapt_profile(
        context, raw_profile
    )

    event_id = f"event_{sha256(f'{snapshot.profile_id}:persona-pipeline'.encode()).hexdigest()}"
    event = PlanningAgentEvent(
        event_id=event_id,
        kind=PlanningEventKind.INITIALIZE,
        profile=snapshot,
        target_concept_id=target_concept_id,
    )
    result = context.planning_agent.invoke(
        event, thread_id=f"persona-pipeline-{snapshot.profile_id}"
    )

    if result.status is PlanningAgentStatus.FAILED or result.path is None:
        failure = result.failure.message if result.failure else "planning did not return a path"
        return _empty_snapshot(
            generated_at=generated_at,
            snapshot=snapshot,
            source_version=source_version,
            target_concept_id=target_concept_id,
            warnings=warnings,
            failure=failure,
        )

    decision = result.path
    brief_builder = ResourceBriefBuilder(
        catalog=context.catalog,
        blueprints=context.blueprints,
        adaptations=result.adaptations,
        evidence_index=context.evidence_index,
    )

    node_records: list[PersonaPathNodeRecord] = []
    personalized_ids: list[str] = []
    skipped_ids: list[str] = []
    skip_reasons: dict[str, tuple[ReasonCode, ...]] = {}
    node_depths: dict[str, str | None] = {}

    for node in decision.nodes:
        node_depths[node.concept_id] = node.delivery_depth.value if node.delivery_depth else None
        if node.status is PathStatus.SKIPPED:
            skipped_ids.append(node.concept_id)
            skip_reasons[node.concept_id] = node.reason_codes
            node_records.append(_bare_node_record(node))
            continue
        if node.status is PathStatus.COMPLETED:
            node_records.append(_bare_node_record(node))
            continue

        personalized_ids.append(node.concept_id)
        node_records.append(
            _process_personalized_node(context, decision, snapshot, node, brief_builder, top_k)
        )

    return PersonaPipelineSnapshot(
        generated_at=generated_at,
        profile_id=snapshot.profile_id,
        learner_ref=snapshot.learner_ref,
        source_profile_version=source_version,
        adapter_warnings=warnings,
        target_concept_id=target_concept_id,
        path_id=decision.path_id,
        graph_version=decision.graph_version,
        policy_version=decision.policy_version,
        full_path=tuple(node_records),
        personalized_path_concept_ids=tuple(personalized_ids),
        skipped_concept_ids=tuple(skipped_ids),
        skip_reasons=skip_reasons,
        node_depths=node_depths,
        snapshot_digest=build_persona_snapshot_digest(
            snapshot.profile_id,
            decision.path_id,
            (record.concept_id for record in node_records),
            personalized_ids,
        ),
    )


def _default_correctness(node: PathNode, profile: LearnerProfileSnapshot) -> bool:
    """Simulated answer correctness for :func:`run_persona_feedback_loop`.

    Grounded in the profile's own diagnosed mastery for this concept (against
    the same passing threshold the live platform uses,
    ``platform.models.ASSESSMENT_PASSING_SCORE``) rather than an arbitrary
    coin flip, so replaying the same profile always simulates the same
    answers. A concept the profile never assessed defaults to "not yet
    correct" -- a first encounter, not an assumed pass.
    """

    mastery = next(
        (
            item.mastery_score
            for item in profile.knowledge_mastery
            if item.concept_id == node.concept_id
        ),
        None,
    )
    return mastery is not None and mastery >= ASSESSMENT_PASSING_SCORE


class FeedbackLoopState(TypedDict, total=False):
    """State for the explicit feedback-loop orchestration graph below.

    Every field here is a direct transplant of a local variable from the
    previous imperative ``while`` loop (git history has the original) -- node
    bodies read/write these the same way the loop's statements did, so the
    graph is a restructuring of the same logic, not a reimplementation.
    """

    # Fixed inputs, set once before the graph runs.
    context: PersonaPipelineContext
    thread_id: str
    top_k: int
    correctness: Callable[[PathNode, LearnerProfileSnapshot], bool]
    generated_at: datetime
    source_version: str
    target_concept_id: str | None
    warnings: tuple[str, ...]
    safety_cap: int
    max_rounds: int | None
    initial_profile: LearnerProfileSnapshot

    # Evolving across rounds.
    result: CoursePlanningAgentResult
    profile: LearnerProfileSnapshot
    ledger: AssessmentLedger
    processed: dict[str, PersonaPathNodeRecord]
    rounds: list[FeedbackRoundRecord]
    round_index: int

    # Scratch for the node currently being processed.
    current_node: PathNode
    update: AssessmentUpdateResult | None

    # Routing and outcome.
    route: str
    failure: str | None
    final_snapshot: PersonaPipelineSnapshot


def _fl_initialize(state: FeedbackLoopState) -> FeedbackLoopState:
    context = state["context"]
    initial_profile = state["initial_profile"]
    init_event_id = (
        f"event_{sha256(f'{initial_profile.profile_id}:persona-pipeline-feedback:init'.encode()).hexdigest()}"
    )
    result: CoursePlanningAgentResult = context.planning_agent.invoke(
        PlanningAgentEvent(
            event_id=init_event_id,
            kind=PlanningEventKind.INITIALIZE,
            profile=initial_profile,
            target_concept_id=state["target_concept_id"],
        ),
        thread_id=state["thread_id"],
    )
    if result.status is PlanningAgentStatus.FAILED or result.path is None:
        failure = result.failure.message if result.failure else "planning did not return a path"
        return {"result": result, "failure": failure}
    return {
        "result": result,
        "profile": initial_profile,
        "ledger": AssessmentLedger(profile=initial_profile),
        "processed": {},
        "rounds": [],
        "round_index": 0,
    }


def _fl_check_progress(state: FeedbackLoopState) -> FeedbackLoopState:
    """The top of the original ``while`` loop: decide whether to process
    another node or stop, on every round including the first."""

    if state.get("failure") is not None:
        return {"route": "assemble"}
    result = state["result"]
    if result.status in {PlanningAgentStatus.COMPLETED, PlanningAgentStatus.FAILED}:
        return {"route": "assemble"}
    if state["round_index"] >= state["safety_cap"]:
        return {
            "failure": (
                f"feedback loop exceeded safety cap of {state['safety_cap']} "
                "rounds without completing"
            ),
            "route": "assemble",
        }
    if result.path is None or result.current_node is None:
        return {
            "failure": "planning did not return a current node to advance",
            "route": "assemble",
        }
    return {"route": "generate"}


def _fl_generate_for_current_node(state: FeedbackLoopState) -> FeedbackLoopState:
    context = state["context"]
    result = state["result"]
    decision = result.path
    current_node = result.current_node
    assert decision is not None and current_node is not None  # guaranteed by check_progress
    brief_builder = ResourceBriefBuilder(
        catalog=context.catalog,
        blueprints=context.blueprints,
        adaptations=result.adaptations,
        evidence_index=context.evidence_index,
    )
    processed = dict(state["processed"])
    processed[current_node.concept_id] = _process_personalized_node(
        context, decision, state["profile"], current_node, brief_builder, state["top_k"]
    )
    return {"processed": processed, "current_node": current_node}


def _fl_simulate_and_update_mastery(state: FeedbackLoopState) -> FeedbackLoopState:
    context = state["context"]
    profile = state["profile"]
    current_node = state["current_node"]
    round_index = state["round_index"]

    is_correct = state["correctness"](current_node, profile)
    assessment_event = AssessmentEvent(
        event_id=(
            f"assessment_{sha256(f'{profile.profile_id}:{current_node.concept_id}:round{round_index}'.encode()).hexdigest()}"
        ),
        profile_id=profile.profile_id,
        graph_version=profile.graph_version,
        concept_ids=(current_node.concept_id,),
        correct=is_correct,
        response_time_ms=DEFAULT_FEEDBACK_RESPONSE_TIME_MS,
        hint_count=0,
        attempt_count=1,
        timestamp=state["generated_at"],
    )
    update = apply_assessment_event(context.catalog, state["ledger"], assessment_event)
    if not update.applied:
        return {"update": update, "route": "advance"}

    mastery_before = next(
        (
            score
            for concept_id, score in update.mastery_before
            if concept_id == current_node.concept_id
        ),
        None,
    )
    mastery_after = next(
        (
            score
            for concept_id, score in update.mastery_after
            if concept_id == current_node.concept_id
        ),
        None,
    )
    rounds = [
        *state["rounds"],
        FeedbackRoundRecord(
            round_index=round_index,
            concept_id=current_node.concept_id,
            simulated_correct=is_correct,
            mastery_before=mastery_before,
            mastery_after=mastery_after,
            classified_error_kind=(
                update.classified_error_kind.value
                if update.classified_error_kind is not None
                else None
            ),
            reason_codes=update.reason_codes,
        ),
    ]
    return {
        "update": update,
        "ledger": update.ledger,
        "profile": update.ledger.profile,
        "rounds": rounds,
        "route": "refresh",
    }


def _fl_replan_profile_refreshed(state: FeedbackLoopState) -> FeedbackLoopState:
    context = state["context"]
    update = state["update"]
    current_node = state["current_node"]
    assert update is not None  # only reached via the "refresh" route
    refresh_event_id = f"event_{sha256(update.event_digest.encode()).hexdigest()}"
    result = context.planning_agent.invoke(
        PlanningAgentEvent(
            event_id=refresh_event_id,
            kind=PlanningEventKind.PROFILE_REFRESHED,
            profile=state["profile"],
            start_concept_id=current_node.concept_id,
        ),
        thread_id=state["thread_id"],
    )
    if result.status is PlanningAgentStatus.FAILED:
        failure = result.failure.message if result.failure else "profile refresh failed"
        return {"result": result, "failure": failure, "route": "assemble"}
    return {"result": result, "route": "advance"}


def _fl_advance_concepts_completed(state: FeedbackLoopState) -> FeedbackLoopState:
    context = state["context"]
    current_node = state["current_node"]
    profile = state["profile"]
    round_index = state["round_index"]
    complete_event_id = (
        f"event_{sha256(f'{profile.profile_id}:{current_node.concept_id}:complete:round{round_index}'.encode()).hexdigest()}"
    )
    result = context.planning_agent.invoke(
        PlanningAgentEvent(
            event_id=complete_event_id,
            kind=PlanningEventKind.CONCEPTS_COMPLETED,
            completed_concept_ids=(current_node.concept_id,),
        ),
        thread_id=state["thread_id"],
    )
    if result.status is PlanningAgentStatus.FAILED:
        failure = result.failure.message if result.failure else "advancing the path failed"
        return {"result": result, "failure": failure, "route": "assemble"}

    next_round_index = round_index + 1
    max_rounds = state.get("max_rounds")
    if max_rounds is not None and next_round_index >= max_rounds:
        # Mirrors the original loop's ``break``: stop without re-checking
        # check_progress, so a max_rounds stop never gets misread as "still
        # going" by the safety-cap/current-node checks there.
        return {"result": result, "round_index": next_round_index, "route": "assemble"}
    return {"result": result, "round_index": next_round_index, "route": "loop"}


def _fl_assemble_snapshot(state: FeedbackLoopState) -> FeedbackLoopState:
    rounds = tuple(state.get("rounds", ()))
    failure = state.get("failure")
    if failure is not None:
        snapshot = _empty_snapshot(
            generated_at=state["generated_at"],
            snapshot=state["initial_profile"],
            source_version=state["source_version"],
            target_concept_id=state["target_concept_id"],
            warnings=state["warnings"],
            failure=failure,
            feedback_rounds=rounds,
        )
        return {"final_snapshot": snapshot}

    result = state["result"]
    if result.path is None:
        snapshot = _empty_snapshot(
            generated_at=state["generated_at"],
            snapshot=state["initial_profile"],
            source_version=state["source_version"],
            target_concept_id=state["target_concept_id"],
            warnings=state["warnings"],
            failure="planning did not return a final path",
            feedback_rounds=rounds,
        )
        return {"final_snapshot": snapshot}

    final_decision = result.path
    processed = state["processed"]
    profile = state["profile"]
    node_records: list[PersonaPathNodeRecord] = []
    personalized_ids: list[str] = []
    skipped_ids: list[str] = []
    skip_reasons: dict[str, tuple[ReasonCode, ...]] = {}
    node_depths: dict[str, str | None] = {}

    for node in final_decision.nodes:
        node_depths[node.concept_id] = node.delivery_depth.value if node.delivery_depth else None
        processed_record = processed.get(node.concept_id)
        if processed_record is not None:
            node_records.append(
                processed_record.model_copy(
                    update={"status": node.status, "reason_codes": node.reason_codes}
                )
            )
            if node.status is not PathStatus.SKIPPED:
                personalized_ids.append(node.concept_id)
            continue
        if node.status is PathStatus.SKIPPED:
            skipped_ids.append(node.concept_id)
            skip_reasons[node.concept_id] = node.reason_codes
        elif node.status is not PathStatus.COMPLETED:
            # Not yet reached because the loop stopped early (max_rounds or
            # the safety cap) -- reported plainly, see the module docstring.
            personalized_ids.append(node.concept_id)
        node_records.append(_bare_node_record(node))

    snapshot = PersonaPipelineSnapshot(
        generated_at=state["generated_at"],
        profile_id=profile.profile_id,
        learner_ref=profile.learner_ref,
        source_profile_version=state["source_version"],
        adapter_warnings=state["warnings"],
        target_concept_id=state["target_concept_id"],
        path_id=final_decision.path_id,
        graph_version=final_decision.graph_version,
        policy_version=final_decision.policy_version,
        full_path=tuple(node_records),
        personalized_path_concept_ids=tuple(personalized_ids),
        skipped_concept_ids=tuple(skipped_ids),
        skip_reasons=skip_reasons,
        node_depths=node_depths,
        feedback_rounds=rounds,
        snapshot_digest=build_persona_snapshot_digest(
            profile.profile_id,
            final_decision.path_id,
            (record.concept_id for record in node_records),
            personalized_ids,
        ),
    )
    return {"final_snapshot": snapshot}


def _fl_route(state: FeedbackLoopState) -> str:
    return state["route"]


def _build_feedback_loop_graph() -> CompiledStateGraph[
    FeedbackLoopState, None, FeedbackLoopState, FeedbackLoopState
]:
    """The explicit orchestration graph for :func:`run_persona_feedback_loop`.

    Mirrors the "closing the loop" half of this session's architecture
    diagram exactly: generate for the current node, simulate an answer,
    update mastery, PROFILE_REFRESHED, CONCEPTS_COMPLETED, loop back to
    check_progress -- until the course completes, a round fails, or
    max_rounds/the safety cap is hit. No checkpointer: the whole loop runs to
    completion inside one ``invoke`` call, so there is nothing to resume
    across separate calls (unlike ``context.planning_agent``'s own graph,
    which this one calls into and which does have its own checkpointer).
    """

    builder: StateGraph[FeedbackLoopState, None, FeedbackLoopState, FeedbackLoopState] = (
        StateGraph(FeedbackLoopState)
    )
    builder.add_node("initialize", _fl_initialize)
    builder.add_node("check_progress", _fl_check_progress)
    builder.add_node("generate_for_current_node", _fl_generate_for_current_node)
    builder.add_node("simulate_and_update_mastery", _fl_simulate_and_update_mastery)
    builder.add_node("replan_profile_refreshed", _fl_replan_profile_refreshed)
    builder.add_node("advance_concepts_completed", _fl_advance_concepts_completed)
    builder.add_node("assemble_snapshot", _fl_assemble_snapshot)

    builder.add_edge(START, "initialize")
    builder.add_edge("initialize", "check_progress")
    builder.add_conditional_edges(
        "check_progress",
        _fl_route,
        {"generate": "generate_for_current_node", "assemble": "assemble_snapshot"},
    )
    builder.add_edge("generate_for_current_node", "simulate_and_update_mastery")
    builder.add_conditional_edges(
        "simulate_and_update_mastery",
        _fl_route,
        {"refresh": "replan_profile_refreshed", "advance": "advance_concepts_completed"},
    )
    builder.add_conditional_edges(
        "replan_profile_refreshed",
        _fl_route,
        {"advance": "advance_concepts_completed", "assemble": "assemble_snapshot"},
    )
    builder.add_conditional_edges(
        "advance_concepts_completed",
        _fl_route,
        # "loop" is the cycle: back to the same top-of-round gate every node
        # not yet processed passes through, including the very first.
        {"loop": "check_progress", "assemble": "assemble_snapshot"},
    )
    builder.add_edge("assemble_snapshot", END)
    return builder.compile()


_FEEDBACK_LOOP_GRAPH = _build_feedback_loop_graph()


def run_persona_feedback_loop(
    context: PersonaPipelineContext,
    raw_profile: Mapping[str, object],
    *,
    top_k: int = 5,
    max_rounds: int | None = None,
    correctness_fn: Callable[[PathNode, LearnerProfileSnapshot], bool] | None = None,
) -> PersonaPipelineSnapshot:
    """Advance the path one node at a time, closing the feedback loop.

    For the current node: generate retrieval/resource output (same Agent
    decision as :func:`run_persona_pipeline`), simulate one answer, update
    mastery through the same rule-based ``AssessmentLedger`` the live
    platform uses (``skillforge_kb.assessment.apply_assessment_event``), then
    replan on the *same* LangGraph thread with the two-event sequence
    production uses for a real answer submission
    (``PlatformService.submit_assessment``): a ``PROFILE_REFRESHED`` event
    first (recomputes depth/adaptations for the still-current node with the
    new mastery, without advancing), then a ``CONCEPTS_COMPLETED`` event
    (marks the node done and promotes the next node to ``AVAILABLE``). This
    repeats until the course completes, ``max_rounds`` is reached, or nothing
    is left to advance.

    The orchestration itself is an explicit ``langgraph.graph.StateGraph``
    (see :func:`_build_feedback_loop_graph`), the same shape as
    ``platform/graph.py`` and ``agents/planning_agent.py`` use, rather than a
    plain imperative loop -- structurally visible, not behaviorally
    different: every node body is a direct transplant of what used to be one
    section of the loop's body.

    ``correctness_fn`` lets a caller script a specific persona's answers
    (e.g. "always correct" for an idealized fast learner); the default
    (:func:`_default_correctness`) derives correctness from the profile's own
    diagnosed mastery, so the simulation is grounded in real diagnostic
    signal instead of an arbitrary coin flip.

    Nodes the loop never reaches (because it stopped early) are reported
    plainly, with no retrieval/resource attempt -- pre-generating for a node
    out of order would use mastery that has not evolved to that point yet,
    which would misrepresent what the loop actually demonstrated.
    """

    generated_at = datetime.now(UTC)
    snapshot, source_version, target_concept_id, warnings = _adapt_profile(
        context, raw_profile
    )
    # Unlike run_persona_pipeline (one INITIALIZE call, safely idempotent via
    # the planning graph's own duplicate-event replay), this function issues
    # a sequence of events across many rounds and tracks the evolving profile
    # in graph state. A thread_id keyed only on profile_id would let a second
    # call for the same profile on this same context replay the *first*
    # call's already-advanced graph state while this call still thinks it is
    # starting fresh -- profile/adaptation digests then disagree and every
    # node raises. Each real invocation gets its own thread instead.
    thread_id = (
        f"persona-pipeline-feedback-{snapshot.profile_id}-"
        f"{generated_at.strftime('%Y%m%dT%H%M%S%f')}"
    )
    safety_cap = len(context.catalog.concepts()) + 5
    initial_state: FeedbackLoopState = {
        "context": context,
        "thread_id": thread_id,
        "top_k": top_k,
        "correctness": correctness_fn or _default_correctness,
        "generated_at": generated_at,
        "source_version": source_version,
        "target_concept_id": target_concept_id,
        "warnings": warnings,
        "safety_cap": safety_cap,
        "max_rounds": max_rounds,
        "initial_profile": snapshot,
    }
    # Each round visits at most 5 nodes (check_progress, generate, simulate,
    # refresh, advance); a generous multiple of the safety cap keeps a full
    # ~140-concept course from ever tripping LangGraph's own recursion guard.
    recursion_limit = safety_cap * 6 + 20
    final_state = cast(
        FeedbackLoopState,
        _FEEDBACK_LOOP_GRAPH.invoke(
            initial_state,
            config={"recursion_limit": recursion_limit},
        ),
    )
    final_snapshot = final_state.get("final_snapshot")
    assert final_snapshot is not None  # assemble_snapshot always sets this
    return final_snapshot


def dump_persona_pipeline_snapshot(snapshot: PersonaPipelineSnapshot, output_path: Path) -> None:
    _write_json(snapshot.model_dump(mode="json"), output_path)


def _write_json(payload: object, output_path: Path) -> None:
    """Atomic write: mirrors ``evaluation/synthetic.py``'s ``_write_json``.

    A killed or interrupted run must never leave a half-written snapshot at
    ``output_path``.
    """

    resolved = output_path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = resolved.with_name(f".{resolved.name}.tmp")
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    try:
        temporary_path.write_text(serialized + "\n", encoding="utf-8")
        temporary_path.replace(resolved)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise
