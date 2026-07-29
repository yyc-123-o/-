import json
from hashlib import sha256
from typing import TypedDict

from skillforge_kb.ontology.models import DepthLevel
from skillforge_kb.ontology.resource_blueprints import ResourceType
from skillforge_kb.resources.briefs import RESOURCE_EVIDENCE_KINDS
from skillforge_kb.resources.evidence_bundle import EvidenceBundle
from skillforge_kb.resources.generator_contracts import (
    AssessmentResource,
    EvidenceBoundItem,
    GeneratedArtifact,
    LectureResource,
    PracticalGuideResource,
    ProjectResource,
    ResourceGenerator,
    ValidatedResourcePackage,
)
from skillforge_kb.resources.models import ResourceBrief


class _ArtifactFields(TypedDict):
    path_id: str
    graph_version: str
    concept_id: str
    delivery_depth: DepthLevel
    sequence: int
    hard_prerequisite_ids: tuple[str, ...]
    covered_learning_outcomes: tuple[str, ...]
    items: tuple[EvidenceBoundItem, ...]


class FakeResourceGenerator:
    def generate(
        self,
        brief: ResourceBrief,
        bundle: EvidenceBundle,
    ) -> tuple[GeneratedArtifact, ...]:
        artifacts: list[GeneratedArtifact] = []
        for resource_type in brief.required_resource_types:
            evidence_ids = tuple(
                record.evidence_id
                for record in bundle.records
                if record.content_kind in RESOURCE_EVIDENCE_KINDS[resource_type]
            )
            common: _ArtifactFields = {
                "path_id": brief.path_id,
                "graph_version": brief.graph_version,
                "concept_id": brief.concept_id,
                "delivery_depth": brief.delivery_depth,
                "sequence": brief.sequence,
                "hard_prerequisite_ids": brief.hard_prerequisite_ids,
                "covered_learning_outcomes": brief.learning_outcomes,
                "items": (
                    EvidenceBoundItem(
                        text=f"{resource_type.value}: {brief.learning_outcomes[0]}",
                        evidence_ids=evidence_ids,
                    ),
                ),
            }
            if resource_type is ResourceType.LECTURE:
                artifacts.append(
                    LectureResource(
                        **common,
                        resource_type=ResourceType.LECTURE,
                    )
                )
            elif resource_type is ResourceType.PRACTICAL_GUIDE:
                artifacts.append(
                    PracticalGuideResource(
                        **common,
                        resource_type=ResourceType.PRACTICAL_GUIDE,
                    )
                )
            elif resource_type is ResourceType.ASSESSMENT:
                artifacts.append(
                    AssessmentResource(
                        **common,
                        resource_type=ResourceType.ASSESSMENT,
                        assessment_kinds=brief.assessment_kinds,
                    )
                )
            else:
                artifacts.append(
                    ProjectResource(
                        **common,
                        resource_type=ResourceType.PROJECT,
                    )
                )
        return tuple(artifacts)


class ResourceGenerationTool:
    def invoke(
        self,
        brief: ResourceBrief,
        bundle: EvidenceBundle,
        generator: ResourceGenerator,
    ) -> ValidatedResourcePackage:
        return self.validate(brief, bundle, generator.generate(brief, bundle))

    def validate(
        self,
        brief: ResourceBrief,
        bundle: EvidenceBundle,
        artifacts: tuple[GeneratedArtifact, ...],
    ) -> ValidatedResourcePackage:
        if bundle.brief_id != brief.brief_id:
            raise ValueError("evidence bundle does not match resource brief")
        if (
            bundle.graph_version != brief.graph_version
            or bundle.concept_id != brief.concept_id
            or bundle.depth is not brief.delivery_depth
        ):
            raise ValueError("evidence bundle scope does not match resource brief")
        actual_types = [artifact.resource_type for artifact in artifacts]
        if len(actual_types) != len(set(actual_types)) or set(actual_types) != set(
            brief.required_resource_types
        ):
            raise ValueError("generated artifacts do not match required resource types")

        evidence_by_id = {record.evidence_id: record for record in bundle.records}
        allowed_evidence_ids = set(evidence_by_id)
        for artifact in artifacts:
            if (
                artifact.path_id != brief.path_id
                or artifact.graph_version != brief.graph_version
                or artifact.concept_id != brief.concept_id
                or artifact.delivery_depth is not brief.delivery_depth
                or artifact.sequence != brief.sequence
                or artifact.hard_prerequisite_ids != brief.hard_prerequisite_ids
            ):
                raise ValueError("generated artifact changed the path contract")
            if artifact.covered_learning_outcomes != brief.learning_outcomes:
                raise ValueError("generated artifact does not cover learning outcomes")
            if not artifact.items:
                raise ValueError("generated artifact requires evidence-bound items")
            for item in artifact.items:
                if not item.evidence_ids:
                    raise ValueError("generated item requires a citation")
                unknown = set(item.evidence_ids) - allowed_evidence_ids
                if unknown:
                    raise ValueError("generated item cites unknown evidence")
                allowed_kinds = set(RESOURCE_EVIDENCE_KINDS[artifact.resource_type])
                if any(
                    evidence_by_id[evidence_id].content_kind not in allowed_kinds
                    for evidence_id in item.evidence_ids
                ):
                    raise ValueError("generated item cites the wrong resource evidence kind")
            if isinstance(artifact, AssessmentResource) and (
                artifact.assessment_kinds != brief.assessment_kinds
            ):
                raise ValueError("assessment kinds do not match resource brief")

        ordered = tuple(
            sorted(artifacts, key=lambda artifact: artifact.resource_type.value)
        )
        payload = {
            "artifacts": [artifact.model_dump(mode="json") for artifact in ordered],
            "brief_id": brief.brief_id,
            "bundle_id": bundle.bundle_id,
        }
        return ValidatedResourcePackage(
            result_id=f"resource_result_{_hash(payload)}",
            brief_id=brief.brief_id,
            bundle_id=bundle.bundle_id,
            artifacts=ordered,
        )


def _hash(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
