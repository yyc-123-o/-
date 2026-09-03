import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from threading import RLock
from typing import TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from skillforge_kb.agents.planning_agent_models import (
    CoursePlanningAgentResult,
    PlanningAgentEvent,
    PlanningAgentStatus,
    PlanningEventKind,
    PlanningPathMode,
)
from skillforge_kb.agents.resource_agent import ResourceAgentResult
from skillforge_kb.agents.retrieval_agent_models import (
    DomainRetrievalRequest,
    DomainRetrievalResult,
    EvidenceGap,
)
from skillforge_kb.assessment import (
    AssessmentEvent,
    AssessmentLedger,
    BktParameters,
    apply_assessment_event,
    apply_bkt_event,
)
from skillforge_kb.evaluation.knowledge_tracing import (
    KnowledgeTracingEvaluationReport,
    KnowledgeTracingObservation,
    evaluate_knowledge_tracing_by_model,
)
from skillforge_kb.evidence.manifest import EvidenceIndex
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.planning.models import PathStatus
from skillforge_kb.resources.controlled_generation import PracticeExercise
from skillforge_kb.resources.evidence_bundle import build_evidence_bundle
from skillforge_kb.resources.handoff import ResourceHandoffContract
from skillforge_kb.resources.models import ResourceBrief
from skillforge_kb.retrieval.models import KnowledgeRetrievalResult

from .models import (
    ASSESSMENT_PASSING_SCORE,
    AssessmentModel,
    AssessmentSubmission,
    ExecutionMode,
    LearningProgress,
    LectureProgressSubmission,
    PlatformFailure,
    PlatformRunRequest,
    PlatformRunResult,
    PlatformRunStatus,
    PlatformStage,
    PlatformStepRecord,
    PlatformStepStatus,
    PracticeReviewSubmission,
    LearningCoachQuestion,
    LearningCoachReply,
    build_payload_digest,
    build_request_digest,
    build_run_id,
)
from .ports import (
    Clock,
    HandoffFactoryPort,
    PlanningAgentPort,
    PlatformRunRepository,
    ResourceAgentPort,
    RetrievalAgentPort,
)
from .practice_review import PracticeReviewResult, review_practice_submission


class PlatformGraphState(TypedDict, total=False):
    request: PlatformRunRequest
    run_id: str
    planning_event: PlanningAgentEvent
    route: str
    status: PlatformRunStatus
    planning: CoursePlanningAgentResult
    handoff: ResourceHandoffContract
    retrieval: DomainRetrievalResult
    resources: ResourceAgentResult
    evidence_gap: EvidenceGap
    failure: PlatformFailure
    steps: tuple[PlatformStepRecord, ...]
    learning_progress: LearningProgress | None


PlatformGraph = CompiledStateGraph[
    PlatformGraphState,
    None,
    PlatformGraphState,
    PlatformGraphState,
]


@dataclass(frozen=True)
class PlatformGraphDependencies:
    planning_agent: PlanningAgentPort
    retrieval_agent: RetrievalAgentPort
    resource_agent: ResourceAgentPort
    handoff_factory: HandoffFactoryPort
    evidence_index: EvidenceIndex
    clock: Clock
    catalog: OntologyCatalog | None = None
    practice_llm: object | None = None


class PlatformService:
    _ASSESSMENT_PASSING_SCORE = ASSESSMENT_PASSING_SCORE
    def __init__(
        self,
        dependencies: PlatformGraphDependencies,
        repository: PlatformRunRepository,
        *,
        close_callbacks: tuple[Callable[[], None], ...] = (),
    ) -> None:
        self._dependencies = dependencies
        self._graph = build_platform_graph(dependencies)
        self._repository = repository
        self._close_callbacks = close_callbacks
        self._lock = RLock()
        self._closed = False

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        close = getattr(self._repository, "close", None)
        if callable(close):
            close()
        for callback in self._close_callbacks:
            callback()

    def ask_learning_coach(
        self,
        run_id: str,
        question: LearningCoachQuestion | dict[str, object],
    ) -> LearningCoachReply:
        """Answer a learner question with the configured Qwen adapter."""
        with self._lock:
            existing = self._repository.get(run_id)
            if existing is None:
                raise KeyError(f"platform run not found: {run_id}")
            question = LearningCoachQuestion.model_validate(question)
            planning = existing.planning
            if (
                existing.status is not PlatformRunStatus.COMPLETED
                or planning is None
                or planning.current_node is None
            ):
                raise ValueError("AI 学习顾问仅在当前学习节点准备好后可用")
            if planning.current_node.concept_id != question.concept_id:
                raise ValueError("问题知识点与当前学习节点不一致")
            adapter = self._dependencies.practice_llm
            if adapter is None or not callable(getattr(adapter, "complete", None)):
                return LearningCoachReply(answer="当前 AI 学习顾问尚未配置模型服务，请先完成千问 API 配置。")
            node = planning.current_node
            draft = (
                existing.resources.preview_package.draft
                if existing.resources and existing.resources.preview_package
                else None
            )
            lecture = getattr(getattr(draft, "lecture", None), "sections", ()) if draft else ()
            context = "\n".join(str(item) for item in lecture)[:6_000]
            prompt = (
                "你是学习平台中的苏格拉底式 AI 学习顾问。只围绕当前知识点回答，先给一个简短提示，"
                "再提出一个引导问题，不直接替学生完成作业。使用中文，控制在 180 字以内。"
                "只返回 JSON 对象：{\"answer\": \"你的回答\"}。"
                f"\n当前知识点：{node.title or node.concept_id}"
                f"\n讲义上下文：{context}\n学生问题：{question.question}"
            )
            try:
                raw_answer = str(adapter.complete(prompt)).strip()
                answer = str(json.loads(raw_answer)["answer"]).strip()
            except Exception as exc:
                raise ValueError("AI 学习顾问暂时不可用，请稍后重试") from exc
            if not answer:
                raise ValueError("AI 学习顾问未返回有效回答")
            return LearningCoachReply(answer=answer[:4_000])

    def run(self, request: PlatformRunRequest) -> PlatformRunResult:
        request = PlatformRunRequest.model_validate(request.model_dump())
        with self._lock:
            existing = self._repository.reserve(request)
            if existing is not None:
                if self._resource_needs_refresh(existing):
                    refreshed = self._execute(request, existing.run_id)
                    self._repository.save(refreshed)
                    return refreshed
                return existing
            result = self._execute(
                request,
                build_run_id(request),
            )
            self._repository.save(result)
            return result

    @staticmethod
    def _resource_needs_refresh(result: PlatformRunResult) -> bool:
        """Regenerate previews created before the richer lesson contract."""
        if result.status is PlatformRunStatus.FAILED:
            return True
        resources = result.resources
        preview = resources.preview_package if resources is not None else None
        draft = preview.draft if preview is not None else None
        practical = draft.practical_guide if draft is not None else None
        if practical is not None and practical.project_exercise is None:
            return True
        lecture = draft.lecture if draft is not None else None
        if lecture is not None:
            # Earlier cached records had prose-only lesson blocks. New lessons
            # must contain the two runnable teaching snippets.
            if sum(bool(block.code) for block in lecture.blocks) < 2:
                return True
            stale_markers = (
                "textcnn", "dcgan", "生成对抗", "bi-lstm", "注意力机制",
            )
            lecture_text = " ".join(
                (
                    lecture.title,
                    *lecture.sections,
                    *(block.body for block in lecture.blocks),
                    *(claim.text for claim in lecture.claims),
                )
            ).casefold()
            if any(marker in lecture_text for marker in stale_markers):
                return True
        return False

    def complete_current_node(
        self,
        run_id: str,
        concept_id: str,
    ) -> PlatformRunResult:
        with self._lock:
            existing = self._repository.get(run_id)
            request = self._repository.get_request(run_id)
            if existing is None or request is None:
                raise KeyError(f"platform run not found: {run_id}")
            planning = existing.planning
            if (
                existing.status is not PlatformRunStatus.COMPLETED
                or existing.resources is None
                or planning is None
                or planning.current_node is None
            ):
                raise ValueError("current node cannot be completed before resources are ready")
            if planning.current_node.concept_id != concept_id:
                raise ValueError("completion concept does not match the current learning node")
            progress = existing.learning_progress
            if progress is not None and not progress.can_complete:
                raise ValueError(
                    "learning completion gate is not satisfied: "
                    "lecture, practice, and passing assessment are required"
                )
            event = PlanningAgentEvent(
                event_id=f"event_{sha256(f'{run_id}:{concept_id}:completed'.encode()).hexdigest()}",
                kind=PlanningEventKind.CONCEPTS_COMPLETED,
                completed_concept_ids=(concept_id,),
            )
            result = self._execute(
                request,
                run_id,
                planning_event=event,
                previous_steps=existing.steps,
                previous_progress=existing.learning_progress,
            )
            self._repository.save(result)
            return result

    def refresh_current_resources(self, run_id: str) -> PlatformRunResult:
        """Regenerate the current node's resource package without changing learning progress."""
        with self._lock:
            existing = self._repository.get(run_id)
            request = self._repository.get_request(run_id)
            if existing is None or request is None:
                raise KeyError(f"platform run not found: {run_id}")
            planning = existing.planning
            if (
                existing.status is not PlatformRunStatus.COMPLETED
                or planning is None
                or planning.current_node is None
            ):
                raise ValueError("current resources are not ready to refresh")
            event = PlanningAgentEvent(
                event_id=f"event_{sha256(f'{run_id}:{planning.current_node.concept_id}:resource-refresh'.encode()).hexdigest()}",
                kind=PlanningEventKind.PROFILE_REFRESHED,
                profile=request.profile,
                start_concept_id=planning.current_node.concept_id,
                path_mode=request.path_mode,
            )
            refreshed = self._execute(
                request,
                run_id,
                planning_event=event,
                previous_steps=existing.steps,
            )
            self._repository.save(refreshed)
            return refreshed

    def submit_assessment(
        self,
        run_id: str,
        submission: AssessmentSubmission | dict[str, object],
    ) -> PlatformRunResult:
        with self._lock:
            existing = self._repository.get(run_id)
            request = self._repository.get_request(run_id)
            if existing is None or request is None:
                raise KeyError(f"platform run not found: {run_id}")
            if self._dependencies.catalog is None:
                raise ValueError("assessment updates are not configured")
            submission = AssessmentSubmission.model_validate(submission)
            submission = self._grade_candidate_quiz(existing, submission)
            is_passing = (
                submission.score is not None
                and submission.score >= self._ASSESSMENT_PASSING_SCORE
            )
            submission_digest = build_payload_digest(
                submission.model_dump(mode="json")
            )
            recorded = self._repository.get_assessment(
                run_id,
                submission.assessment_id,
            )
            if recorded is not None:
                recorded_digest, recorded_result = recorded
                if recorded_digest != submission_digest:
                    raise ValueError(
                        "assessment ID was already used with a different payload"
                    )
                return recorded_result
            planning = existing.planning
            if (
                existing.status is not PlatformRunStatus.COMPLETED
                or existing.resources is None
                or planning is None
                or planning.current_node is None
            ):
                raise ValueError("assessment is only available for a ready learning node")
            if planning.current_node.concept_id != submission.concept_id:
                raise ValueError("assessment concept does not match the current learning node")
            prior_progress = existing.learning_progress
            if (
                prior_progress is not None
                and prior_progress.concept_id != submission.concept_id
            ):
                prior_progress = None
            existing_mastery = next(
                (
                    item.mastery_score
                    for item in request.profile.knowledge_mastery
                    if item.concept_id == submission.concept_id
                ),
                None,
            )
            prior_mastery = existing_mastery
            model_version = "rule.v1"
            if request.assessment_model is AssessmentModel.BKT:
                prior_mastery = (
                    BktParameters().p_l0
                    if prior_mastery is None
                    else prior_mastery
                )
                model_version = BktParameters().model_version
            elif prior_mastery is None:
                prior_mastery = 0.50
            observed_at = datetime.now(UTC)
            event = AssessmentEvent(
                event_id=submission.assessment_id,
                profile_id=request.profile.profile_id,
                graph_version=request.profile.graph_version,
                concept_ids=(submission.concept_id,),
                correct=is_passing,
                response_time_ms=submission.response_time_ms,
                hint_count=submission.hint_count,
                attempt_count=submission.attempt_count,
                timestamp=observed_at,
                error_kind=(
                    None
                    if is_passing
                    else submission.error_kind
                ),
                evidence_refs=submission.evidence_refs,
            )
            observation = KnowledgeTracingObservation(
                observation_id=submission.assessment_id,
                profile_id=request.profile.profile_id,
                concept_id=submission.concept_id,
                model_version=model_version,
                predicted_mastery=prior_mastery,
                correct=is_passing,
                observed_at=observed_at,
            )
            ledger = AssessmentLedger(profile=request.profile)
            if request.assessment_model is AssessmentModel.BKT:
                update = apply_bkt_event(
                    self._dependencies.catalog,
                    ledger,
                    event,
                )
            else:
                update = apply_assessment_event(
                    self._dependencies.catalog,
                    ledger,
                    event,
                )
            updated_request = request.model_copy(
                update={"profile": update.ledger.profile}
            )
            self._repository.update_request(run_id, updated_request)
            progress = LearningProgress(
                concept_id=submission.concept_id,
                lecture_progress=(
                    prior_progress.lecture_progress if prior_progress is not None else 0.0
                ),
                practice_completed=(
                    prior_progress.practice_completed if prior_progress is not None else False
                ),
                assessment_passed=is_passing,
                assessment_attempts=(
                    (prior_progress.assessment_attempts if prior_progress is not None else 0)
                    + 1
                ),
                failed_attempts=(
                    (prior_progress.failed_attempts if prior_progress is not None else 0)
                    + (0 if is_passing else 1)
                ),
                remediation_required=not is_passing,
            )
            refreshed_event = PlanningAgentEvent(
                event_id=f"event_{sha256(f'{run_id}:{submission.assessment_id}:refresh'.encode()).hexdigest()}",
                kind=PlanningEventKind.PROFILE_REFRESHED,
                profile=update.ledger.profile,
                start_concept_id=submission.concept_id,
                path_mode=updated_request.path_mode,
            )
            refreshed = self._execute(
                updated_request,
                run_id,
                planning_event=refreshed_event,
                previous_steps=existing.steps,
                previous_progress=progress,
            )
            refreshed = refreshed.model_copy(
                update={
                    "adaptation_trace": _build_adaptation_trace(
                        existing.planning,
                        refreshed.planning,
                        submission.concept_id,
                        is_passing,
                    )
                }
            )
            if not progress.can_complete:
                self._repository.save(refreshed)
                self._repository.save_assessment(
                    run_id,
                    submission.assessment_id,
                    submission_digest,
                    refreshed,
                )
                self._repository.save_prediction_observation(
                    run_id,
                    submission.assessment_id,
                    observation,
                )
                return refreshed
            completed_event = PlanningAgentEvent(
                event_id=f"event_{sha256(f'{run_id}:{submission.assessment_id}:complete'.encode()).hexdigest()}",
                kind=PlanningEventKind.CONCEPTS_COMPLETED,
                completed_concept_ids=(submission.concept_id,),
            )
            result = self._execute(
                updated_request,
                run_id,
                planning_event=completed_event,
                previous_steps=refreshed.steps,
                previous_progress=refreshed.learning_progress,
            )
            result = result.model_copy(
                update={
                    "adaptation_trace": refreshed.adaptation_trace,
                }
            )
            self._repository.save(result)
            self._repository.save_assessment(
                run_id,
                submission.assessment_id,
                submission_digest,
                result,
            )
            self._repository.save_prediction_observation(
                run_id,
                submission.assessment_id,
                observation,
            )
            return result

    @staticmethod
    def _grade_candidate_quiz(
        existing: PlatformRunResult,
        submission: AssessmentSubmission,
    ) -> AssessmentSubmission:
        """Use server-only preview answer keys when the learner selected options."""
        if not submission.responses:
            if submission.score is None:
                raise ValueError("assessment score is required without selected responses")
            return submission
        preview = existing.resources.preview_package if existing.resources else None
        draft = preview.draft if preview is not None else None
        if draft is None:
            raise ValueError("selected responses are unavailable for this assessment")
        answer_key = {
            item.question_id: item.correct_choice
            for item in draft.student_quiz.items
            if item.correct_choice is not None
        }
        if not answer_key:
            raise ValueError("current assessment has no server-side answer key")
        submitted_ids = set(submission.responses)
        expected_ids = set(answer_key)
        if submitted_ids != expected_ids:
            missing = sorted(expected_ids - submitted_ids)
            unknown = sorted(submitted_ids - expected_ids)
            if missing:
                raise ValueError(f"assessment responses are missing: {missing[0]}")
            raise ValueError(f"assessment response is unknown: {unknown[0]}")
        correct_count = sum(
            submission.responses[question_id] == correct_choice
            for question_id, correct_choice in answer_key.items()
        )
        return submission.model_copy(
            update={
                "score": correct_count / len(answer_key),
                "error_kind": None,
            }
        )

    def review_practice(
        self,
        run_id: str,
        submission: PracticeReviewSubmission | dict[str, object],
    ) -> PracticeReviewResult:
        with self._lock:
            existing = self._repository.get(run_id)
            request = self._repository.get_request(run_id)
            if existing is None or request is None:
                raise KeyError(f"platform run not found: {run_id}")
            submission = PracticeReviewSubmission.model_validate(submission)
            planning = existing.planning
            if (
                existing.status is not PlatformRunStatus.COMPLETED
                or existing.resources is None
                or planning is None
                or planning.current_node is None
            ):
                raise ValueError("practice review is only available for a ready learning node")
            if planning.current_node.concept_id != submission.concept_id:
                raise ValueError("practice concept does not match the current learning node")
            preview = existing.resources.preview_package
            practical = (
                preview.draft.practical_guide
                if preview is not None and preview.draft is not None
                else None
            )
            exercise = (
                practical.project_exercise
                if practical is not None and submission.exercise_kind == "project"
                else practical.exercise if practical is not None
                else None
            )
            if exercise is None:
                exercise = PracticeExercise(
                    task=(
                        "根据当前讲义完成一个最小 Python 示例，创建输入、执行当前知识点的核心变换、"
                        "打印结果，并用一句话解释输出。"
                    ),
                    starter_code=(
                        "# TODO: 根据当前讲义完成最小实现\n"
                        "result = None\n"
                        "print(result)\n"
                    ),
                    expected_output="请根据讲义中的示例填写并解释输出。",
                    checks=(
                        "代码包含输入与结果",
                        "打印结果",
                        "解释结果与当前知识点的关系",
                    ),
                    required_tokens=("result", "print"),
                )
            review = review_practice_submission(
                concept_id=submission.concept_id,
                source=submission.source,
                exercise=exercise,
                llm=cast(object, self._dependencies.practice_llm),
            )
            if review.accepted:
                practice_event_id = (
                    "practice_"
                    + sha256(
                        f"{run_id}:{submission.concept_id}:{submission.source}".encode()
                    ).hexdigest()
                )
                practice_digest = build_payload_digest(
                    {"concept_id": submission.concept_id, "source": submission.source}
                )
                recorded = self._repository.get_assessment(run_id, practice_event_id)
                if recorded is not None:
                    recorded_digest, _ = recorded
                    if recorded_digest != practice_digest:
                        raise ValueError(
                            "practice event ID was already used with a different payload"
                        )
                    return review
                observed_at = datetime.now(UTC)
                practice_event = AssessmentEvent(
                    event_id=practice_event_id,
                    profile_id=request.profile.profile_id,
                    graph_version=request.profile.graph_version,
                    concept_ids=(submission.concept_id,),
                    correct=True,
                    response_time_ms=0,
                    hint_count=0,
                    attempt_count=1,
                    timestamp=observed_at,
                    evidence_refs=(practice_event_id,),
                )
                update = apply_assessment_event(
                    self._dependencies.catalog,
                    AssessmentLedger(profile=request.profile),
                    practice_event,
                )
                updated_request = request.model_copy(update={"profile": update.ledger.profile})
                self._repository.update_request(run_id, updated_request)
                prior = existing.learning_progress
                progress = LearningProgress(
                    concept_id=submission.concept_id,
                    lecture_progress=(prior.lecture_progress if prior is not None else 0.0),
                    practice_completed=True,
                    assessment_passed=(
                        prior.assessment_passed
                        if prior is not None and prior.concept_id == submission.concept_id
                        else False
                    ),
                    assessment_attempts=(
                        prior.assessment_attempts
                        if prior is not None and prior.concept_id == submission.concept_id
                        else 0
                    ),
                    failed_attempts=(
                        prior.failed_attempts
                        if prior is not None and prior.concept_id == submission.concept_id
                        else 0
                    ),
                    remediation_required=False,
                )
                refreshed_event = PlanningAgentEvent(
                    event_id=f"event_{sha256(f'{run_id}:{practice_event_id}:refresh'.encode()).hexdigest()}",
                    kind=PlanningEventKind.PROFILE_REFRESHED,
                    profile=update.ledger.profile,
                    start_concept_id=submission.concept_id,
                    path_mode=updated_request.path_mode,
                )
                refreshed = self._execute(
                    updated_request,
                    run_id,
                    planning_event=refreshed_event,
                    previous_steps=existing.steps,
                    previous_progress=progress,
                )
                self._repository.save(refreshed)
                self._repository.save_assessment(
                    run_id,
                    practice_event_id,
                    practice_digest,
                    refreshed,
                )
                self._repository.save_prediction_observation(
                    run_id,
                    practice_event_id,
                    KnowledgeTracingObservation(
                        observation_id=practice_event_id,
                        profile_id=request.profile.profile_id,
                        concept_id=submission.concept_id,
                        model_version="practice.v1",
                        predicted_mastery=(
                            next(
                                (
                                    item.mastery_score
                                    for item in request.profile.knowledge_mastery
                                    if item.concept_id == submission.concept_id
                                ),
                                0.50,
                            )
                        ),
                        correct=True,
                        observed_at=observed_at,
                    ),
                )
            return review

    def record_lecture_progress(
        self,
        run_id: str,
        submission: LectureProgressSubmission | dict[str, object],
    ) -> PlatformRunResult:
        with self._lock:
            existing = self._repository.get(run_id)
            if existing is None:
                raise KeyError(f"platform run not found: {run_id}")
            submission = LectureProgressSubmission.model_validate(submission)
            planning = existing.planning
            if (
                existing.status is not PlatformRunStatus.COMPLETED
                or existing.resources is None
                or existing.handoff is None
                or planning is None
                or planning.current_node is None
            ):
                raise ValueError(
                    "lecture progress is only available for a ready learning node"
                )
            if existing.handoff.concept_id != submission.concept_id:
                raise ValueError(
                    "lecture progress concept does not match the current learning resource"
                )
            prior = existing.learning_progress
            if prior is not None and prior.concept_id != submission.concept_id:
                prior = None
            submitted_completion = submission.progress >= 1.0
            lecture_progress = (
                1.0
                if submitted_completion
                else max(
                    min(
                        submission.progress,
                        prior.max_next_lecture_progress
                        if prior is not None
                        else 0.25,
                    ),
                    prior.lecture_progress if prior is not None else 0.0,
                )
            )
            progress = LearningProgress(
                concept_id=submission.concept_id,
                lecture_progress=lecture_progress,
                lecture_completed=submitted_completion or (prior.lecture_completed if prior is not None else False),
                practice_completed=prior.practice_completed if prior is not None else False,
                assessment_passed=prior.assessment_passed if prior is not None else False,
                assessment_attempts=prior.assessment_attempts if prior is not None else 0,
                failed_attempts=prior.failed_attempts if prior is not None else 0,
                remediation_required=prior.remediation_required if prior is not None else False,
            )
            result = existing.model_copy(update={"learning_progress": progress})
            self._repository.save(result)
            return result

    def start_node(
        self,
        run_id: str,
        concept_id: str,
        path_mode: PlanningPathMode = PlanningPathMode.PERSONALIZED,
    ) -> PlatformRunResult:
        with self._lock:
            existing = self._repository.get(run_id)
            request = self._repository.get_request(run_id)
            if existing is None or request is None:
                raise KeyError(f"platform run not found: {run_id}")
            if existing.planning is None or existing.planning.path is None:
                raise ValueError("learning path is not ready")
            if (
                path_mode is PlanningPathMode.FULL
                and existing.planning.full_path is None
            ):
                raise ValueError("full learning path is not ready")
            node = next(
                (
                    item
                    for item in (
                        existing.planning.full_path
                        if path_mode is PlanningPathMode.FULL
                        else existing.planning.path
                    ).nodes
                    if item.concept_id == concept_id
                ),
                None,
            )
            if node is None:
                raise ValueError("requested node is not in the learning path")
            if node.status in {PathStatus.BLOCKED, PathStatus.SKIPPED, PathStatus.COMPLETED}:
                raise ValueError(
                    "requested node cannot be started: "
                    + (
                        "blocking prerequisites"
                        if node.status is PathStatus.BLOCKED
                        else node.status.value
                    )
                )
            suffix = f":start:{concept_id}"
            key = f"{request.idempotency_key}{suffix}"[-128:]
            started_request = request.model_copy(
                update={
                    "idempotency_key": key,
                    "start_concept_id": concept_id,
                    "path_mode": path_mode,
                }
            )
            return self.run(started_request)

    def peek(self, request: PlatformRunRequest) -> PlatformRunResult | None:
        return self._repository.peek(request)

    def get(self, run_id: str) -> PlatformRunResult | None:
        return self._repository.get(run_id)

    def evaluate_profile_knowledge_tracing(
        self,
        profile_id: str,
    ) -> tuple[KnowledgeTracingEvaluationReport, ...]:
        with self._lock:
            observations = self._repository.list_prediction_observations_for_profile(
                profile_id
            )
            if not observations:
                raise ValueError("no prediction observations")
            return evaluate_knowledge_tracing_by_model(observations)

    def search_evidence(
        self,
        query: str,
        top_k: int = 5,
    ) -> KnowledgeRetrievalResult:
        """Run a free-form candidate search across the knowledge corpus."""
        with self._lock:
            return self._dependencies.retrieval_agent.search(query, top_k)

    def _execute(
        self,
        request: PlatformRunRequest,
        run_id: str,
        *,
        planning_event: PlanningAgentEvent | None = None,
        previous_steps: tuple[PlatformStepRecord, ...] = (),
        previous_progress: LearningProgress | None = None,
    ) -> PlatformRunResult:
        state_input: PlatformGraphState = {
            "request": request,
            "run_id": run_id,
            "status": PlatformRunStatus.PENDING,
            "steps": previous_steps,
        }
        if previous_progress is not None:
            state_input["learning_progress"] = previous_progress
        if planning_event is not None:
            state_input["planning_event"] = planning_event
        state = cast(PlatformGraphState, self._graph.invoke(state_input))
        return _result_from_state(state)


def build_platform_graph(dependencies: PlatformGraphDependencies) -> PlatformGraph:
    def validate_input(state: PlatformGraphState) -> PlatformGraphState:
        request = PlatformRunRequest.model_validate(state["request"].model_dump())
        return _success_update(
            state,
            dependencies,
            PlatformStage.VALIDATE_INPUT,
            {"request": request, "status": PlatformRunStatus.PENDING},
            request,
        )

    def plan_course(state: PlatformGraphState) -> PlatformGraphState:
        request = state["request"]
        try:
            event = state.get("planning_event")
            if event is None:
                digest = build_request_digest(request)
                event = PlanningAgentEvent(
                    event_id=f"event_{sha256(digest.encode('utf-8')).hexdigest()}",
                    kind=PlanningEventKind.INITIALIZE,
                    profile=request.profile,
                    target_concept_id=request.target_concept_id,
                    start_concept_id=request.start_concept_id,
                    path_mode=request.path_mode,
                )
            planning = dependencies.planning_agent.invoke(event, state["run_id"])
            if (
                planning.status is not PlanningAgentStatus.READY
                or planning.path is None
                or planning.current_node is None
            ):
                message = (
                    planning.failure.message
                    if planning.failure is not None
                    else "planning Agent did not select a current node"
                )
                raise RuntimeError(message)
            return _success_update(
                state,
                dependencies,
                PlatformStage.PLAN_COURSE,
                {
                    "planning": planning,
                    "status": PlatformRunStatus.PLANNING,
                    "route": "continue",
                },
                planning,
            )
        except Exception as exc:
            return _failure_update(state, dependencies, PlatformStage.PLAN_COURSE, exc)

    def build_handoff_node(state: PlatformGraphState) -> PlatformGraphState:
        try:
            handoff = dependencies.handoff_factory.build(
                state["planning"],
                state["request"].profile,
            )
            return _success_update(
                state,
                dependencies,
                PlatformStage.BUILD_HANDOFF,
                {"handoff": handoff, "route": "continue"},
                handoff,
            )
        except Exception as exc:
            return _failure_update(state, dependencies, PlatformStage.BUILD_HANDOFF, exc)

    def retrieve_evidence(state: PlatformGraphState) -> PlatformGraphState:
        handoff = state["handoff"]
        request = state["request"]
        try:
            scope = _build_retrieval_scope(dependencies, handoff)
            rewritten_queries = (
                f"{scope} 定义 概念 解释 是什么",
                f"{scope} 代码 实现 示例 参数",
                f"{scope} 练习 习题 评估 例题",
            )
            retrieval_request = DomainRetrievalRequest(
                original_query=(
                    f"{handoff.concept_id} {handoff.delivery_depth.value}"
                ),
                rewritten_queries=rewritten_queries,
                profile_id=handoff.profile_id,
                concept_id=handoff.concept_id,
                depth=handoff.delivery_depth,
                top_k=request.top_k,
            )
            retrieval = dependencies.retrieval_agent.retrieve(
                retrieval_request,
                handoff,
            )
            return _success_update(
                state,
                dependencies,
                PlatformStage.RETRIEVE_EVIDENCE,
                {
                    "retrieval": retrieval,
                    "status": PlatformRunStatus.RETRIEVING,
                    "route": "continue",
                },
                retrieval,
            )
        except Exception as exc:
            return _failure_update(
                state,
                dependencies,
                PlatformStage.RETRIEVE_EVIDENCE,
                exc,
            )

    def evaluate_gate(state: PlatformGraphState) -> PlatformGraphState:
        handoff = state["handoff"]
        retrieval = state["retrieval"]
        request = state["request"]
        if handoff.generation_gate.allowed and retrieval.evidence_gap is None:
            route = "strict"
            status = PlatformRunStatus.GENERATING
        elif (
            request.execution_mode is ExecutionMode.CANDIDATE_PREVIEW
            and set(handoff.generation_gate.blocking_codes)
            == {"blocked_missing_published_evidence"}
            and bool(retrieval.candidate_evidence)
        ):
            route = "preview"
            status = PlatformRunStatus.GENERATING
        else:
            route = "blocked"
            status = PlatformRunStatus.BLOCKED
        gap = retrieval.evidence_gap
        if route == "blocked" and gap is None:
            gap = EvidenceGap(
                missing_content_kinds=handoff.evidence_filters.content_kinds,
                message=handoff.generation_gate.next_action,
            )
        values: PlatformGraphState = {
            "route": route,
            "status": status,
        }
        if gap is not None:
            values["evidence_gap"] = gap
        return _success_update(
            state,
            dependencies,
            PlatformStage.EVALUATE_GATE,
            values,
            {"route": route, "status": status.value},
            step_status=(
                PlatformStepStatus.BLOCKED
                if route == "blocked"
                else PlatformStepStatus.COMPLETED
            ),
        )

    def generate_strict(state: PlatformGraphState) -> PlatformGraphState:
        try:
            handoff = state["handoff"]
            brief = ResourceBrief.model_validate(handoff.model_dump())
            bundle = build_evidence_bundle(brief, dependencies.evidence_index)
            resources = dependencies.resource_agent.generate_strict(handoff, bundle)
            return _success_update(
                state,
                dependencies,
                PlatformStage.GENERATE_RESOURCE,
                {"resources": resources, "route": "continue"},
                resources,
            )
        except Exception as exc:
            return _failure_update(
                state,
                dependencies,
                PlatformStage.GENERATE_RESOURCE,
                exc,
            )

    def generate_preview(state: PlatformGraphState) -> PlatformGraphState:
        try:
            resources = dependencies.resource_agent.generate_preview(
                state["request"].profile,
                state["handoff"],
                state["retrieval"],
            )
            return _success_update(
                state,
                dependencies,
                PlatformStage.GENERATE_RESOURCE,
                {"resources": resources, "route": "continue"},
                resources,
            )
        except Exception as exc:
            return _failure_update(
                state,
                dependencies,
                PlatformStage.GENERATE_RESOURCE,
                exc,
            )

    def validate_resource(state: PlatformGraphState) -> PlatformGraphState:
        try:
            resources = ResourceAgentResult.model_validate(
                state["resources"].model_dump()
            )
            progress = state.get("learning_progress")
            if progress is not None and progress.concept_id != state["handoff"].concept_id:
                progress = None
            return _success_update(
                state,
                dependencies,
                PlatformStage.VALIDATE_RESOURCE,
                {
                    "resources": resources,
                    "route": "completed",
                    "learning_progress": progress,
                },
                resources,
            )
        except Exception as exc:
            return _failure_update(
                state,
                dependencies,
                PlatformStage.VALIDATE_RESOURCE,
                exc,
            )

    def finalize_completed(state: PlatformGraphState) -> PlatformGraphState:
        return _success_update(
            state,
            dependencies,
            PlatformStage.FINALIZE,
            {"status": PlatformRunStatus.COMPLETED},
            {"status": PlatformRunStatus.COMPLETED.value},
        )

    def finalize_blocked(state: PlatformGraphState) -> PlatformGraphState:
        return _success_update(
            state,
            dependencies,
            PlatformStage.FINALIZE,
            {"status": PlatformRunStatus.BLOCKED},
            {"status": PlatformRunStatus.BLOCKED.value},
            step_status=PlatformStepStatus.BLOCKED,
        )

    def finalize_failed(state: PlatformGraphState) -> PlatformGraphState:
        return _success_update(
            state,
            dependencies,
            PlatformStage.FINALIZE,
            {"status": PlatformRunStatus.FAILED},
            {"status": PlatformRunStatus.FAILED.value},
            step_status=PlatformStepStatus.COMPLETED,
        )

    builder = StateGraph(PlatformGraphState)
    builder.add_node("validate_input", validate_input)
    builder.add_node("plan_course", plan_course)
    builder.add_node("build_handoff", build_handoff_node)
    builder.add_node("retrieve_evidence", retrieve_evidence)
    builder.add_node("evaluate_generation_gate", evaluate_gate)
    builder.add_node("strict_generate", generate_strict)
    builder.add_node("preview_generate", generate_preview)
    builder.add_node("validate_resource", validate_resource)
    builder.add_node("completed_finalize", finalize_completed)
    builder.add_node("blocked_finalize", finalize_blocked)
    builder.add_node("failed_finalize", finalize_failed)
    builder.add_edge(START, "validate_input")
    builder.add_edge("validate_input", "plan_course")
    builder.add_conditional_edges(
        "plan_course",
        _continue_or_failure,
        {"continue": "build_handoff", "failure": "failed_finalize"},
    )
    builder.add_conditional_edges(
        "build_handoff",
        _continue_or_failure,
        {"continue": "retrieve_evidence", "failure": "failed_finalize"},
    )
    builder.add_conditional_edges(
        "retrieve_evidence",
        _continue_or_failure,
        {"continue": "evaluate_generation_gate", "failure": "failed_finalize"},
    )
    builder.add_conditional_edges(
        "evaluate_generation_gate",
        lambda state: state["route"],
        {
            "strict": "strict_generate",
            "preview": "preview_generate",
            "blocked": "blocked_finalize",
        },
    )
    builder.add_conditional_edges(
        "strict_generate",
        _continue_or_failure,
        {"continue": "validate_resource", "failure": "failed_finalize"},
    )
    builder.add_conditional_edges(
        "preview_generate",
        _continue_or_failure,
        {"continue": "validate_resource", "failure": "failed_finalize"},
    )
    builder.add_conditional_edges(
        "validate_resource",
        _completed_or_failure,
        {"completed": "completed_finalize", "failure": "failed_finalize"},
    )
    builder.add_edge("completed_finalize", END)
    builder.add_edge("blocked_finalize", END)
    builder.add_edge("failed_finalize", END)
    return builder.compile()


def _continue_or_failure(state: PlatformGraphState) -> str:
    return "failure" if "failure" in state else "continue"


def _completed_or_failure(state: PlatformGraphState) -> str:
    return "failure" if "failure" in state else "completed"


def _success_update(
    state: PlatformGraphState,
    dependencies: PlatformGraphDependencies,
    stage: PlatformStage,
    values: PlatformGraphState,
    output: object,
    *,
    step_status: PlatformStepStatus = PlatformStepStatus.COMPLETED,
) -> PlatformGraphState:
    started = dependencies.clock.now()
    finished = dependencies.clock.now()
    input_payload = _last_stage_payload(state)
    step = PlatformStepRecord(
        stage=stage,
        status=step_status,
        started_at=started,
        finished_at=finished,
        input_digest=build_payload_digest(input_payload),
        output_digest=build_payload_digest(_serializable(output)),
    )
    return {**values, "steps": (*state.get("steps", ()), step)}


def _failure_update(
    state: PlatformGraphState,
    dependencies: PlatformGraphDependencies,
    stage: PlatformStage,
    error: Exception,
) -> PlatformGraphState:
    code = "contract_mismatch" if isinstance(error, ValueError) else f"{stage.value}_failed"
    failure = PlatformFailure(
        code=code,
        message=str(error) or type(error).__name__,
        stage=stage,
        retryable=not isinstance(error, ValueError),
    )
    now = dependencies.clock.now()
    step = PlatformStepRecord(
        stage=stage,
        status=PlatformStepStatus.FAILED,
        started_at=now,
        finished_at=now,
        input_digest=build_payload_digest(_last_stage_payload(state)),
        failure=failure,
    )
    return {
        "route": "failure",
        "status": PlatformRunStatus.FAILED,
        "failure": failure,
        "steps": (*state.get("steps", ()), step),
    }


def _last_stage_payload(state: PlatformGraphState) -> object:
    for key in ("resources", "retrieval", "handoff", "planning", "request"):
        if key in state:
            return _serializable(state[key])
    return {}


def _serializable(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def _build_retrieval_scope(
    dependencies: PlatformGraphDependencies,
    handoff: ResourceHandoffContract,
) -> str:
    """Build a bilingual, natural-language retrieval scope for one node.

    Prefer the reviewed concept metadata (Chinese/English names, aliases,
    summary, and section title) over the raw concept ID so the BM25 query
    carries the terms a learner would actually use.
    """
    if dependencies.catalog is None:
        return (
            f"{handoff.concept_id} {handoff.chapter_id} "
            f"{handoff.section_id} {handoff.delivery_depth.value}"
        )
    try:
        concept = dependencies.catalog.get_concept(handoff.concept_id)
        section = dependencies.catalog.section_for(handoff.concept_id)
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


def _build_adaptation_trace(
    before: CoursePlanningAgentResult | None,
    after: CoursePlanningAgentResult | None,
    concept_id: str,
    passed: bool,
) -> tuple[str, ...]:
    """Summarize the feedback-to-replanning decision for the UI and audit log."""
    before_queue = (
        tuple(item.concept_id for item in before.path.recommendations)
        if before is not None and before.path is not None
        else ()
    )
    after_queue = (
        tuple(item.concept_id for item in after.path.recommendations)
        if after is not None and after.path is not None
        else ()
    )
    changed = tuple(item for item in after_queue if item not in before_queue)
    removed = tuple(item for item in before_queue if item not in after_queue)
    outcome = "通过" if passed else "未通过"
    trace = [f"{concept_id} 测评{outcome}，已更新掌握度并重新规划。"]
    if changed:
        trace.append("新增推荐：" + "、".join(changed) + "。")
    if removed:
        trace.append("移出推荐：" + "、".join(removed) + "。")
    if not changed and not removed:
        trace.append("推荐队列顺序保持不变，但资源深度和支架策略已重新计算。")
    return tuple(trace)


def _result_from_state(state: PlatformGraphState) -> PlatformRunResult:
    progress = state.get("learning_progress")
    if progress is None and state.get("handoff") is not None and state.get("resources") is not None:
        progress = LearningProgress(
            concept_id=state["handoff"].concept_id,
            lecture_progress=0.0,
        )
    return PlatformRunResult(
        run_id=state["run_id"],
        request_digest=build_request_digest(state["request"]),
        profile_id=state["request"].profile.profile_id,
        profile=state["request"].profile,
        status=state["status"],
        planning=state.get("planning"),
        retrieval=state.get("retrieval"),
        handoff=state.get("handoff"),
        resources=state.get("resources"),
        evidence_gap=state.get("evidence_gap"),
        failure=state.get("failure"),
        steps=state.get("steps", ()),
        learning_progress=progress,
    )
