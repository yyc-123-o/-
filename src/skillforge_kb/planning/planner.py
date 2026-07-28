from collections import defaultdict

from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import (
    AssessmentStatus,
    DepthLevel,
    KnowledgeMastery,
    LearnerProfileSnapshot,
    Relation,
    RelationKind,
)

from .models import (
    ABILITY_DIMENSIONS,
    PathDecision,
    PathNode,
    PathStatus,
    PlannerPolicy,
    ReasonCode,
)
from .ordering import PlanningError, course_positions, stable_required_concept_ids
from .serialization import build_path_id, build_policy_digest


class CoursePlanner:
    def __init__(
        self,
        catalog: OntologyCatalog,
        policy: PlannerPolicy | None = None,
    ) -> None:
        self._catalog = catalog
        source_policy = policy or PlannerPolicy()
        self._policy = PlannerPolicy.model_validate(source_policy.model_dump())
        self._policy_digest = build_policy_digest(self._policy)
        self._ordered_ids = stable_required_concept_ids(catalog)
        self._known_ids = {concept.id for concept in catalog.concepts()}
        self._positions = course_positions(catalog)
        self._hard_relations = self._index_hard_relations()

    @property
    def policy(self) -> PlannerPolicy:
        return self._policy.model_copy(deep=True)

    @property
    def policy_digest(self) -> str:
        return self._policy_digest

    def plan(
        self,
        profile: LearnerProfileSnapshot,
        completed_concept_ids: set[str] | None = None,
        *,
        allow_skips: bool = True,
    ) -> PathDecision:
        completed = completed_concept_ids or set()
        unknown_completed = completed - self._known_ids
        if unknown_completed:
            raise PlanningError(f"unknown completed concept: {sorted(unknown_completed)[0]}")
        mastery = self._mastery_index(profile)
        ability_score, ability_reasons = self._ability_score(profile)
        initial_nodes = [
            self._build_node(
                concept_id,
                sequence,
                mastery,
                ability_score,
                ability_reasons,
                completed,
                allow_skips,
            )
            for sequence, concept_id in enumerate(self._ordered_ids, start=1)
        ]
        nodes = assign_execution_statuses(initial_nodes)
        return PathDecision(
            path_id=build_path_id(
                profile.profile_id,
                profile.graph_version,
                self._policy.version,
                self._ordered_ids,
                self._policy_digest,
            ),
            profile_id=profile.profile_id,
            graph_version=profile.graph_version,
            policy_version=self._policy.version,
            policy_digest=self._policy_digest,
            generated_at=profile.generated_at,
            nodes=nodes,
        )

    def _mastery_index(
        self,
        profile: LearnerProfileSnapshot,
    ) -> dict[str, KnowledgeMastery]:
        if profile.graph_version != self._catalog.course_document.version:
            raise PlanningError("profile graph version does not match catalog")
        result: dict[str, KnowledgeMastery] = {}
        for item in profile.knowledge_mastery:
            if item.concept_id not in self._known_ids:
                raise PlanningError(f"unknown mastery concept: {item.concept_id}")
            if item.concept_id in result:
                raise PlanningError(f"duplicate mastery concept: {item.concept_id}")
            result[item.concept_id] = item
        return result

    def _ability_score(
        self,
        profile: LearnerProfileSnapshot,
    ) -> tuple[float | None, list[ReasonCode]]:
        if set(profile.abilities) != set(ABILITY_DIMENSIONS):
            return None, [ReasonCode.ABILITY_INCOMPLETE]
        if any(
            profile.abilities[dimension].confidence < self._policy.minimum_confidence
            for dimension in ABILITY_DIMENSIONS
        ):
            return None, [ReasonCode.ABILITY_LOW_CONFIDENCE]
        return (
            sum(
                profile.abilities[dimension].score
                * self._policy.ability_weights[dimension]
                for dimension in ABILITY_DIMENSIONS
            ),
            [],
        )

    def _build_node(
        self,
        concept_id: str,
        sequence: int,
        mastery: dict[str, KnowledgeMastery],
        ability_score: float | None,
        ability_reasons: list[ReasonCode],
        completed_concept_ids: set[str],
        allow_skips: bool,
    ) -> PathNode:
        position = self._positions[concept_id]
        concept_mastery = mastery.get(concept_id)
        if allow_skips and self._can_skip(concept_mastery):
            return PathNode(
                concept_id=concept_id,
                chapter_id=position.chapter_id,
                section_id=position.section_id,
                sequence=sequence,
                status=PathStatus.SKIPPED,
                delivery_depth=None,
                hard_prerequisite_ids=self._prerequisite_ids(concept_id),
                reason_codes=(ReasonCode.MASTERY_SKIP_THRESHOLD_MET,),
            )

        blocking_ids, blocking_reasons = self._blocking_prerequisites(
            concept_id, mastery, completed_concept_ids
        )
        depth, depth_reasons = self._delivery_depth(
            concept_mastery,
            ability_score,
            ability_reasons,
            bool(blocking_ids),
        )
        return PathNode(
            concept_id=concept_id,
            chapter_id=position.chapter_id,
            section_id=position.section_id,
            sequence=sequence,
            status=PathStatus.BLOCKED if blocking_ids else PathStatus.PENDING,
            delivery_depth=depth,
            hard_prerequisite_ids=self._prerequisite_ids(concept_id),
            blocking_prerequisite_ids=tuple(blocking_ids),
            reason_codes=tuple(_unique([*depth_reasons, *blocking_reasons])),
        )

    def _can_skip(self, mastery: KnowledgeMastery | None) -> bool:
        return bool(
            mastery is not None
            and mastery.assessment_status is AssessmentStatus.ASSESSED
            and mastery.mastery_score is not None
            and mastery.mastery_score >= self._policy.skip_mastery
            and mastery.confidence >= self._policy.skip_confidence
        )

    def _blocking_prerequisites(
        self,
        concept_id: str,
        mastery: dict[str, KnowledgeMastery],
        completed_concept_ids: set[str],
    ) -> tuple[list[str], list[ReasonCode]]:
        blocking_ids: list[str] = []
        reasons: list[ReasonCode] = []
        for relation in self._hard_relations[concept_id]:
            if relation.min_mastery is None:
                raise PlanningError("hard prerequisite relation requires min_mastery")
            if relation.source in completed_concept_ids:
                continue
            prerequisite = mastery.get(relation.source)
            if (
                prerequisite is None
                or prerequisite.assessment_status is AssessmentStatus.NOT_ASSESSED
                or prerequisite.mastery_score is None
            ):
                blocking_ids.append(relation.source)
                reasons.append(ReasonCode.HARD_PREREQUISITE_UNASSESSED)
            elif prerequisite.confidence < self._policy.minimum_confidence:
                blocking_ids.append(relation.source)
                reasons.append(ReasonCode.HARD_PREREQUISITE_LOW_CONFIDENCE)
            elif prerequisite.mastery_score < relation.min_mastery:
                blocking_ids.append(relation.source)
                reasons.append(ReasonCode.HARD_PREREQUISITE_BELOW_THRESHOLD)
        return blocking_ids, _unique(reasons)

    def _delivery_depth(
        self,
        mastery: KnowledgeMastery | None,
        ability_score: float | None,
        ability_reasons: list[ReasonCode],
        blocked: bool,
    ) -> tuple[DepthLevel, list[ReasonCode]]:
        evidence_reasons: list[ReasonCode] = []
        if (
            mastery is None
            or mastery.assessment_status is AssessmentStatus.NOT_ASSESSED
            or mastery.mastery_score is None
        ):
            evidence_reasons.append(ReasonCode.MASTERY_MISSING)
        elif mastery.confidence < self._policy.minimum_confidence:
            evidence_reasons.append(ReasonCode.MASTERY_LOW_CONFIDENCE)

        if evidence_reasons or ability_score is None or blocked:
            return (
                DepthLevel.INTRO,
                _unique(
                    [
                        *evidence_reasons,
                        *ability_reasons,
                        ReasonCode.READY_FOR_INTRO,
                    ]
                ),
            )

        assert mastery is not None and mastery.mastery_score is not None
        readiness = (
            mastery.mastery_score * self._policy.mastery_weight
            + ability_score * self._policy.ability_weight
        )
        if readiness >= self._policy.advanced_threshold:
            return DepthLevel.ADVANCED, [ReasonCode.READY_FOR_ADVANCED]
        if readiness >= self._policy.intermediate_threshold:
            return DepthLevel.INTERMEDIATE, [ReasonCode.READY_FOR_INTERMEDIATE]
        return DepthLevel.INTRO, [ReasonCode.READY_FOR_INTRO]

    def _index_hard_relations(self) -> dict[str, list[Relation]]:
        result: dict[str, list[Relation]] = defaultdict(list)
        for relation in self._catalog.relations(RelationKind.HARD_PREREQUISITE):
            result[relation.target].append(relation)
        for rows in result.values():
            rows.sort(key=lambda item: item.source)
        return result

    def _prerequisite_ids(self, concept_id: str) -> tuple[str, ...]:
        return tuple(relation.source for relation in self._hard_relations[concept_id])


def assign_execution_statuses(nodes: list[PathNode]) -> tuple[PathNode, ...]:
    available_assigned = False
    result: list[PathNode] = []
    for node in nodes:
        if node.status in {PathStatus.SKIPPED, PathStatus.COMPLETED, PathStatus.BLOCKED}:
            result.append(node)
        elif not available_assigned:
            result.append(node.model_copy(update={"status": PathStatus.AVAILABLE}))
            available_assigned = True
        else:
            result.append(node.model_copy(update={"status": PathStatus.PENDING}))
    return tuple(result)


def _unique[T](items: list[T]) -> list[T]:
    return list(dict.fromkeys(items))
