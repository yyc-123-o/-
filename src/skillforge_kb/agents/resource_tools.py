from typing import TypedDict

from pydantic import TypeAdapter

from skillforge_kb.ontology.models import DepthLevel
from skillforge_kb.ontology.resource_blueprints import ResourceType
from skillforge_kb.resources.briefs import RESOURCE_EVIDENCE_KINDS
from skillforge_kb.resources.evidence_bundle import EvidenceBundle
from skillforge_kb.resources.generator_contracts import (
    AssessmentResource,
    CitationRecord,
    EvidenceBoundItem,
    GeneratedArtifact,
    LectureResource,
    PracticalGuideResource,
    ProjectResource,
    ResourceGenerator,
    ValidatedResourcePackage,
    build_resource_result_id,
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


_ARTIFACTS_ADAPTER = TypeAdapter(tuple[GeneratedArtifact, ...])


class FakeResourceGenerator:
    def generate(
        self,
        brief: ResourceBrief,
        bundle: EvidenceBundle,
    ) -> tuple[GeneratedArtifact, ...]:
        artifacts: list[GeneratedArtifact] = []
        for resource_type in brief.required_resource_types:
            citations = tuple(
                CitationRecord(
                    evidence_id=record.evidence_id,
                    source_id=record.source_id,
                    chunk_id=record.chunk_id,
                    locator=record.locator,
                    normalized_hash=record.normalized_hash,
                )
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
                        citations=citations,
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
        validated_brief, validated_bundle = self._validate_inputs(brief, bundle)
        return self.validate(
            validated_brief,
            validated_bundle,
            generator.generate(validated_brief, validated_bundle),
        )

    def validate(
        self,
        brief: ResourceBrief,
        bundle: EvidenceBundle,
        artifacts: tuple[GeneratedArtifact, ...],
    ) -> ValidatedResourcePackage:
        brief, bundle = self._validate_inputs(brief, bundle)
        artifacts = _ARTIFACTS_ADAPTER.validate_python(artifacts)
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
            cited_kinds = set()
            for item in artifact.items:
                if not item.citations:
                    raise ValueError("generated item requires a citation")
                unknown = set(item.evidence_ids) - allowed_evidence_ids
                if unknown:
                    raise ValueError("generated item cites unknown evidence")
                allowed_kinds = set(RESOURCE_EVIDENCE_KINDS[artifact.resource_type])
                for citation in item.citations:
                    record = evidence_by_id[citation.evidence_id]
                    if (
                        citation.source_id != record.source_id
                        or citation.chunk_id != record.chunk_id
                        or citation.locator != record.locator
                        or citation.normalized_hash != record.normalized_hash
                    ):
                        raise ValueError("generated citation metadata does not match evidence")
                    if record.content_kind not in allowed_kinds:
                        raise ValueError(
                            "generated item cites the wrong resource evidence kind"
                        )
                    cited_kinds.add(record.content_kind)
            if not allowed_kinds.issubset(cited_kinds):
                raise ValueError(
                    "generated artifact does not cite all required evidence kinds"
                )
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
            result_id=build_resource_result_id(payload),
            brief_id=brief.brief_id,
            bundle_id=bundle.bundle_id,
            artifacts=ordered,
        )

    @staticmethod
    def _validate_inputs(
        brief: ResourceBrief,
        bundle: EvidenceBundle,
    ) -> tuple[ResourceBrief, EvidenceBundle]:
        return (
            ResourceBrief.model_validate(brief.model_dump()),
            EvidenceBundle.model_validate(bundle.model_dump()),
        )
