import json
from collections.abc import Mapping
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from skillforge_kb.domain.enums import ContentKind
from skillforge_kb.evidence.manifest import EvidenceIndex
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import (
    DepthLevel,
    LearnerProfileSnapshot,
    RelationKind,
)
from skillforge_kb.ontology.resource_blueprints import (
    ResourceBlueprintCatalog,
    ResourceType,
    resource_blueprint,
)
from skillforge_kb.planning.adaptation import NodeAdaptationDecision
from skillforge_kb.planning.models import PathDecision, PathNode, PathStatus
from skillforge_kb.planning.serialization import build_path_id

from .allocation import allocate_resources
from .models import (
    AcceptanceChecks,
    CitationRequirements,
    ErrorPatternHint,
    EvidenceFilters,
    PresentationPreferences,
    ResourceBrief,
    ResourceBriefPayload,
    build_brief_id,
)

RESOURCE_EVIDENCE_KINDS: dict[ResourceType, tuple[ContentKind, ...]] = {
    ResourceType.LECTURE: (ContentKind.DEFINITION,),
    ResourceType.PRACTICAL_GUIDE: (ContentKind.CODE,),
    ResourceType.ASSESSMENT: (ContentKind.EXERCISE,),
    ResourceType.PROJECT: (ContentKind.CODE, ContentKind.EXERCISE),
}


class ResourceBriefBuilder(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    catalog: OntologyCatalog
    blueprints: ResourceBlueprintCatalog
    adaptations: tuple[NodeAdaptationDecision, ...]
    evidence_index: EvidenceIndex

    @field_validator("adaptations", mode="before")
    @classmethod
    def normalize_adaptations(
        cls,
        value: object,
    ) -> object:
        if isinstance(value, Mapping):
            return tuple(value.values())
        return value

    @model_validator(mode="after")
    def validate_dependencies(self) -> "ResourceBriefBuilder":
        self._validate_dependency_contract()
        return self

    def _validate_dependency_contract(self) -> None:
        graph_version = self.catalog.course_document.version
        if self.blueprints.graph_version != graph_version:
            raise ValueError("resource blueprint graph version does not match catalog")
        if self.evidence_index.graph_version != graph_version:
            raise ValueError("evidence graph version does not match catalog")
        concept_ids = [item.concept_id for item in self.adaptations]
        if len(concept_ids) != len(set(concept_ids)):
            raise ValueError("adaptation concept IDs must be unique")

    def build(
        self,
        decision: PathDecision,
        profile: LearnerProfileSnapshot,
        concept_id: str,
    ) -> ResourceBrief:
        self._validate_runtime_dependencies()
        decision = PathDecision.model_validate(decision.model_dump())
        profile = LearnerProfileSnapshot.model_validate(profile.model_dump())
        self._validate_versions(decision, profile)
        node = next(
            (item for item in decision.nodes if item.concept_id == concept_id),
            None,
        )
        if node is None:
            raise ValueError(f"concept is not present in path: {concept_id}")
        if node.status is PathStatus.SKIPPED:
            raise ValueError("skipped nodes cannot generate resource briefs")
        if node.status is PathStatus.COMPLETED:
            raise ValueError("completed nodes cannot generate resource briefs")
        if node.delivery_depth is None:
            raise ValueError("resource brief requires a delivery depth")
        self._validate_node_structure(node)

        adaptation = next(
            (item for item in self.adaptations if item.concept_id == concept_id),
            None,
        )
        if adaptation is None:
            raise ValueError(f"missing node adaptation: {concept_id}")
        if adaptation.delivery_depth is not node.delivery_depth:
            raise ValueError("adaptation depth does not match path depth")
        if adaptation.policy_digest != decision.policy_digest:
            raise ValueError("adaptation policy does not match path policy")
        if adaptation.profile_digest != _profile_digest(profile):
            raise ValueError("adaptation profile does not match learner profile")

        blueprint = resource_blueprint(self.blueprints, concept_id, node.delivery_depth)
        allocation = allocate_resources(blueprint, adaptation)
        content_kinds = _content_kinds(blueprint.resource_types)
        self._require_published_evidence(concept_id, node.delivery_depth, content_kinds)
        payload = ResourceBriefPayload(
            path_id=decision.path_id,
            graph_version=decision.graph_version,
            profile_id=decision.profile_id,
            policy_digest=decision.policy_digest,
            concept_id=concept_id,
            chapter_id=node.chapter_id,
            section_id=node.section_id,
            sequence=node.sequence,
            status=node.status,
            delivery_depth=node.delivery_depth,
            learning_outcomes=blueprint.learning_outcomes,
            assessment_kinds=blueprint.assessment_kinds,
            hard_prerequisite_ids=node.hard_prerequisite_ids,
            blocking_prerequisite_ids=node.blocking_prerequisite_ids,
            soft_prerequisite_ids=self._incoming_ids(
                concept_id,
                RelationKind.SOFT_PREREQUISITE,
            ),
            related_confusion_ids=self._related_confusion_ids(concept_id),
            required_resource_types=blueprint.resource_types,
            node_adaptation=adaptation,
            resource_allocation=allocation,
            error_pattern_hints=_error_pattern_hints(profile, concept_id),
            presentation_preferences=_presentation_preferences(profile),
            evidence_filters=EvidenceFilters(
                graph_version=decision.graph_version,
                concept_id=concept_id,
                depth=node.delivery_depth,
                content_kinds=content_kinds,
            ),
            citation_requirements=CitationRequirements(
                min_evidence_records=len(content_kinds),
            ),
            acceptance_checks=AcceptanceChecks(
                required_resource_types=blueprint.resource_types,
                learning_outcomes=blueprint.learning_outcomes,
                assessment_kinds=blueprint.assessment_kinds,
            ),
        )
        brief_id = build_brief_id(payload.model_dump(mode="json"))
        return ResourceBrief(
            **payload.model_dump(),
            brief_id=brief_id,
        )

    def _validate_runtime_dependencies(self) -> None:
        ResourceBlueprintCatalog.model_validate(self.blueprints.model_dump())
        EvidenceIndex.model_validate(self.evidence_index.model_dump())
        for adaptation in self.adaptations:
            NodeAdaptationDecision.model_validate(adaptation.model_dump())
        self._validate_dependency_contract()

    def _validate_versions(
        self,
        decision: PathDecision,
        profile: LearnerProfileSnapshot,
    ) -> None:
        graph_version = self.catalog.course_document.version
        if decision.graph_version != graph_version:
            raise ValueError("path graph version does not match catalog")
        if profile.graph_version != graph_version:
            raise ValueError("profile graph version does not match catalog")
        if decision.profile_id != profile.profile_id:
            raise ValueError("path profile does not match learner profile")
        expected_path_id = build_path_id(
            decision.profile_id,
            decision.graph_version,
            decision.policy_version,
            [node.concept_id for node in decision.nodes],
            decision.policy_digest,
        )
        if decision.path_id != expected_path_id:
            raise ValueError("path ID does not match structural path content")

    def _validate_node_structure(self, node: PathNode) -> None:
        section = self.catalog.section_for(node.concept_id)
        if node.section_id != section.id or node.chapter_id != section.chapter_id:
            raise ValueError("path node does not match catalog position")
        expected_hard = self._incoming_ids(
            node.concept_id,
            RelationKind.HARD_PREREQUISITE,
        )
        if node.hard_prerequisite_ids != expected_hard:
            raise ValueError("path node hard prerequisites do not match catalog")
        if not set(node.blocking_prerequisite_ids).issubset(expected_hard):
            raise ValueError("path node blockers are not hard prerequisites")

    def _require_published_evidence(
        self,
        concept_id: str,
        depth: DepthLevel,
        content_kinds: tuple[ContentKind, ...],
    ) -> None:
        for content_kind in content_kinds:
            if not self.evidence_index.query(
                concept_id,
                depth,
                content_kind=content_kind,
            ):
                raise ValueError(
                    "published evidence is required for "
                    f"{concept_id}:{depth.value}:{content_kind.value}"
                )

    def _incoming_ids(
        self,
        concept_id: str,
        kind: RelationKind,
    ) -> tuple[str, ...]:
        return tuple(
            relation.source
            for relation in self.catalog.relations(kind)
            if relation.target == concept_id
        )

    def _related_confusion_ids(self, concept_id: str) -> tuple[str, ...]:
        related: set[str] = set()
        for kind in (RelationKind.CONFUSED_WITH, RelationKind.CONTRASTS_WITH):
            for relation in self.catalog.relations(kind):
                if relation.source == concept_id:
                    related.add(relation.target)
                elif relation.target == concept_id:
                    related.add(relation.source)
        return tuple(sorted(related))


def _content_kinds(resource_types: tuple[ResourceType, ...]) -> tuple[ContentKind, ...]:
    kinds: list[ContentKind] = []
    for resource_type in resource_types:
        kinds.extend(RESOURCE_EVIDENCE_KINDS[resource_type])
    return tuple(dict.fromkeys(kinds))


def _error_pattern_hints(
    profile: LearnerProfileSnapshot,
    concept_id: str,
) -> tuple[ErrorPatternHint, ...]:
    return tuple(
        ErrorPatternHint(
            code=pattern.code,
            ratio=pattern.ratio,
            evidence_refs=tuple(pattern.evidence_refs),
        )
        for pattern in sorted(profile.error_patterns, key=lambda item: item.code)
        if concept_id in pattern.concept_ids
    )


def _presentation_preferences(
    profile: LearnerProfileSnapshot,
) -> PresentationPreferences:
    preferences = profile.preferences
    return PresentationPreferences(
        content_order=tuple(preferences.content_order),
        code_language=preferences.code_language,
        framework=preferences.framework,
        presentation=tuple(preferences.presentation),
        pace_hours_per_week=preferences.pace_hours_per_week,
        project_orientation=preferences.project_orientation,
    )


def _profile_digest(profile: LearnerProfileSnapshot) -> str:
    payload = profile.model_dump(mode="json", exclude={"observed_at", "generated_at"})
    return f"profile_{_hash(payload)}"


def _hash(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
