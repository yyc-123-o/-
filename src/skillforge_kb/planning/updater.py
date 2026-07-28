from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import LearnerProfileSnapshot, RelationKind

from .models import PathDecision, PathNode, PathStatus, PlannerPolicy
from .ordering import PlanningError, course_positions, stable_required_concept_ids
from .planner import CoursePlanner, assign_execution_statuses
from .serialization import build_path_id


class DepthUpdater:
    def __init__(
        self,
        catalog: OntologyCatalog,
        policy: PlannerPolicy | None = None,
    ) -> None:
        self._catalog = catalog
        self._planner = CoursePlanner(catalog, policy)
        self._policy = self._planner.policy
        self._policy_digest = self._planner.policy_digest

    def update(
        self,
        existing: PathDecision,
        profile: LearnerProfileSnapshot,
        completed_concept_ids: set[str],
    ) -> PathDecision:
        self._validate_identity(existing, profile)
        existing_ids = [node.concept_id for node in existing.nodes]
        unknown_completed = completed_concept_ids - set(existing_ids)
        if unknown_completed:
            raise PlanningError(
                f"completed concept is not in path: {sorted(unknown_completed)[0]}"
            )
        self._validate_existing_path(existing)

        historical_completed = {
            node.concept_id
            for node in existing.nodes
            if node.status is PathStatus.COMPLETED
        }
        all_completed = historical_completed | completed_concept_ids
        fresh = self._planner.plan(profile, all_completed, allow_skips=False)
        if [node.concept_id for node in fresh.nodes] != existing_ids:
            raise PlanningError("path no longer matches catalog")
        fresh_by_id = {node.concept_id: node for node in fresh.nodes}
        merged: list[PathNode] = []
        for node in existing.nodes:
            if node.status in {PathStatus.SKIPPED, PathStatus.COMPLETED}:
                merged.append(node)
            elif node.concept_id in completed_concept_ids:
                merged.append(node.model_copy(update={"status": PathStatus.COMPLETED}))
            else:
                merged.append(fresh_by_id[node.concept_id])

        return existing.model_copy(
            update={
                "generated_at": profile.generated_at,
                "nodes": assign_execution_statuses(merged),
            }
        )

    def _validate_identity(
        self,
        existing: PathDecision,
        profile: LearnerProfileSnapshot,
    ) -> None:
        if profile.profile_id != existing.profile_id:
            raise PlanningError("profile ID does not match existing path")
        if profile.graph_version != existing.graph_version:
            raise PlanningError("profile graph version does not match existing path")
        if existing.graph_version != self._catalog.course_document.version:
            raise PlanningError("existing path graph version does not match catalog")
        if existing.policy_version != self._policy.version:
            raise PlanningError("policy version does not match existing path")
        if existing.policy_digest != self._policy_digest:
            raise PlanningError("policy digest does not match existing path")

    def _validate_existing_path(self, existing: PathDecision) -> None:
        expected_ids = stable_required_concept_ids(self._catalog)
        if [node.concept_id for node in existing.nodes] != expected_ids:
            raise PlanningError("path no longer matches catalog")
        positions = course_positions(self._catalog)
        hard_by_target: dict[str, list[str]] = {}
        for relation in self._catalog.relations(RelationKind.HARD_PREREQUISITE):
            hard_by_target.setdefault(relation.target, []).append(relation.source)
        expected_path_id = build_path_id(
            existing.profile_id,
            existing.graph_version,
            existing.policy_version,
            expected_ids,
            existing.policy_digest,
        )
        if existing.path_id != expected_path_id:
            raise PlanningError("path ID does not match path content")
        for expected_sequence, node in enumerate(existing.nodes, start=1):
            position = positions[node.concept_id]
            if (
                node.sequence != expected_sequence
                or (node.chapter_id, node.section_id)
                != (
                position.chapter_id,
                position.section_id,
                )
                or node.hard_prerequisite_ids
                != tuple(sorted(hard_by_target.get(node.concept_id, [])))
            ):
                raise PlanningError("path no longer matches catalog")
