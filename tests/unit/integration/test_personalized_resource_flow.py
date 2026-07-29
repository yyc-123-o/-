import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from skillforge_kb.agents.resource_tools import (
    FakeResourceGenerator,
    ResourceGenerationTool,
)
from skillforge_kb.domain.enums import ContentKind, Language, LicenseStatus
from skillforge_kb.evidence.manifest import EvidenceIndex
from skillforge_kb.evidence.models import (
    EvidenceRecord,
    EvidenceReviewStatus,
    build_evidence_id,
)
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.concept_attributes import load_concept_attributes
from skillforge_kb.ontology.models import (
    AbilityScore,
    AssessmentStatus,
    ErrorPattern,
    KnowledgeMastery,
    LearnerProfileSnapshot,
    LearningPreferences,
)
from skillforge_kb.ontology.resource_blueprints import load_resource_blueprints
from skillforge_kb.planning.adaptation import NodeWeightEngine, SupportIntensity
from skillforge_kb.planning.models import PathStatus
from skillforge_kb.planning.planner import CoursePlanner
from skillforge_kb.resources.briefs import ResourceBriefBuilder
from skillforge_kb.resources.evidence_bundle import build_evidence_bundle

ROOT = Path(__file__).parents[3]
ONTOLOGY_ROOT = ROOT / "resources" / "ontology"
PROFILE_NAMES = ("zero_foundation", "intermediate", "advanced")
ABILITY_IDS = (
    "theoretical_understanding",
    "coding_ability",
    "mathematical_foundation",
    "problem_solving",
)


def _catalog() -> OntologyCatalog:
    return OntologyCatalog.load(
        ONTOLOGY_ROOT / "ai_course_v1.yaml",
        ONTOLOGY_ROOT / "ai_relations_v1.yaml",
    )


def _mastery_records(
    catalog: OntologyCatalog,
    score: float,
    skip_ids: set[str] | None = None,
) -> list[KnowledgeMastery]:
    skip_ids = skip_ids or set()
    return [
        KnowledgeMastery(
            concept_id=concept.id,
            mastery_score=0.90 if concept.id in skip_ids else score,
            assessment_status=AssessmentStatus.ASSESSED,
            confidence=0.90,
            observed_at=datetime(2026, 7, 29, tzinfo=UTC),
            evidence_refs=["assessment-acceptance"],
        )
        for concept in catalog.concepts()
    ]


def _abilities(score: float) -> dict[str, AbilityScore]:
    return {
        dimension: AbilityScore(
            score=score,
            confidence=0.90,
            assessment_run_id="assessment-acceptance",
        )
        for dimension in ABILITY_IDS
    }


def _profiles(catalog: OntologyCatalog) -> dict[str, LearnerProfileSnapshot]:
    first_ids = [concept.id for concept in catalog.concepts()[:10]]
    first_concept = catalog.concepts()[0].id
    common = {
        "schema_version": "learner-profile.v1",
        "learner_ref": "0" * 64,
        "graph_version": catalog.course_document.version,
        "generated_at": datetime(2026, 7, 29, tzinfo=UTC),
    }
    return {
        "zero_foundation": LearnerProfileSnapshot(
            **common,
            profile_id="profile-zero-foundation",
            error_patterns=[
                ErrorPattern(
                    code="concept_confusion",
                    count=2,
                    ratio=0.50,
                    concept_ids=[first_concept],
                    evidence_refs=["assessment-acceptance"],
                )
            ],
            preferences=LearningPreferences(
                presentation=["step_by_step", "visual_explanation"],
                pace_hours_per_week=4,
            ),
        ),
        "intermediate": LearnerProfileSnapshot(
            **common,
            profile_id="profile-intermediate",
            knowledge_mastery=_mastery_records(catalog, 0.80),
            abilities=_abilities(0.70),
            preferences=LearningPreferences(
                code_language="python",
                framework="pytorch",
                presentation=["code_first"],
                pace_hours_per_week=8,
            ),
        ),
        "advanced": LearnerProfileSnapshot(
            **common,
            profile_id="profile-advanced",
            knowledge_mastery=_mastery_records(catalog, 0.84, set(first_ids)),
            abilities=_abilities(0.95),
            preferences=LearningPreferences(
                content_order=["theory", "implementation", "assessment"],
                project_orientation="project_driven",
                pace_hours_per_week=12,
            ),
        ),
    }


def _evidence_index(catalog: OntologyCatalog) -> EvidenceIndex:
    records = []
    for concept in catalog.concepts():
        for depth in concept.levels:
            for content_kind in (
                ContentKind.DEFINITION,
                ContentKind.CODE,
                ContentKind.EXERCISE,
            ):
                identity = f"{concept.id}:{depth.level.value}:{content_kind.value}"
                digest = sha256(identity.encode("utf-8")).hexdigest()
                records.append(
                    EvidenceRecord(
                        evidence_id=build_evidence_id(
                            graph_version=catalog.course_document.version,
                            source_id=f"fixture-source-{digest[:12]}",
                            chunk_id=f"fixture-chunk-{digest[12:24]}",
                            concept_id=concept.id,
                            depth=depth.level,
                            locator=f"fixture:{identity}",
                            normalized_hash=sha256(
                                f"normalized:{identity}".encode()
                            ).hexdigest(),
                            language=Language.EN,
                            content_kind=content_kind,
                        ),
                        graph_version=catalog.course_document.version,
                        source_id=f"fixture-source-{digest[:12]}",
                        chunk_id=f"fixture-chunk-{digest[12:24]}",
                        concept_id=concept.id,
                        depth=depth.level,
                        source_url=f"https://example.edu/fixture/{digest}",
                        locator=f"fixture:{identity}",
                        normalized_hash=sha256(
                            f"normalized:{identity}".encode()
                        ).hexdigest(),
                        language=Language.EN,
                        content_kind=content_kind,
                        difficulty=concept.difficulty,
                        license_status=LicenseStatus.ALLOWED,
                        review_status=EvidenceReviewStatus.PUBLISHED,
                        reviewed_by="fixture-reviewer",
                        reviewed_at=datetime(2026, 7, 29, tzinfo=UTC),
                    )
                )
    return EvidenceIndex(
        version="acceptance-evidence-v1",
        graph_version=catalog.course_document.version,
        records=tuple(records),
    )


def _run_matrix() -> dict[str, object]:
    catalog = _catalog()
    profiles = _profiles(catalog)
    attributes = load_concept_attributes(
        catalog,
        ONTOLOGY_ROOT / "concept_attributes_v1.yaml",
    )
    blueprints = load_resource_blueprints(
        catalog,
        ONTOLOGY_ROOT / "resource_blueprints_v1.yaml",
    )
    evidence_index = _evidence_index(catalog)
    planner = CoursePlanner(catalog)
    decisions = {name: planner.plan(profile) for name, profile in profiles.items()}
    orders = {
        name: tuple(node.concept_id for node in decision.nodes)
        for name, decision in decisions.items()
    }
    assert all(order == orders["zero_foundation"] for order in orders.values())

    eligible_counts: dict[str, int] = {}
    brief_counts: dict[str, int] = {}
    package_counts: dict[str, int] = {}
    artifact_counts: dict[str, int] = {}
    missing_evidence_failures = 0
    tool = ResourceGenerationTool()
    generator = FakeResourceGenerator()

    for name in PROFILE_NAMES:
        profile = profiles[name]
        decision = decisions[name]
        profile_before = profile.model_dump(mode="json")
        decision_before = decision.model_dump(mode="json")
        engine = NodeWeightEngine(catalog, attributes)
        eligible_nodes = tuple(
            node
            for node in decision.nodes
            if node.status not in {PathStatus.SKIPPED, PathStatus.COMPLETED}
        )
        adaptations = {
            node.concept_id: engine.evaluate(profile, node)
            for node in eligible_nodes
        }
        builder = ResourceBriefBuilder(
            catalog=catalog,
            blueprints=blueprints,
            adaptations=adaptations,
            evidence_index=evidence_index,
        )

        briefs = tuple(
            builder.build(decision, profile, node.concept_id)
            for node in eligible_nodes
        )
        packages = []
        for brief in briefs:
            bundle = build_evidence_bundle(brief, evidence_index)
            packages.append(tool.invoke(brief, bundle, generator))
        empty_index = evidence_index.model_copy(update={"records": ()})
        with pytest.raises(ValueError, match="missing published evidence"):
            build_evidence_bundle(briefs[0], empty_index)
        missing_evidence_failures += 1

        assert profile.model_dump(mode="json") == profile_before
        assert decision.model_dump(mode="json") == decision_before
        eligible_counts[name] = len(eligible_nodes)
        brief_counts[name] = len(briefs)
        package_counts[name] = len(packages)
        artifact_counts[name] = sum(len(package.artifacts) for package in packages)

        if name == "zero_foundation":
            assert all(node.delivery_depth.value == "intro" for node in eligible_nodes)
            assert all(
                adaptation.support_intensity
                in {SupportIntensity.SCAFFOLDED, SupportIntensity.REMEDIATION}
                for adaptation in adaptations.values()
            )
        elif name == "intermediate":
            assert all(
                node.delivery_depth.value == "intermediate" for node in eligible_nodes
            )
        else:
            assert sum(node.status is PathStatus.SKIPPED for node in decision.nodes) == 10
            assert all(node.delivery_depth.value == "advanced" for node in eligible_nodes)

    total_briefs = sum(brief_counts.values())
    return {
        "schema_version": "personalized-flow-matrix.v1",
        "graph_version": catalog.course_document.version,
        "profile_scenarios": len(profiles),
        "required_nodes_per_path": len(orders["zero_foundation"]),
        "path_invariance_checks": len(profiles) - 1,
        "eligible_nodes": eligible_counts,
        "briefs_built": brief_counts,
        "validated_resource_packages": package_counts,
        "generated_artifacts": artifact_counts,
        "total_briefs_built": total_briefs,
        "fixture_evidence_records": len(evidence_index.records),
        "fixture_evidence_binding_rate": 1.0,
        "missing_evidence_failures": missing_evidence_failures,
        "production_published_evidence_records": 0,
        "not_measured_without_real_generation": [
            "hallucination_rate",
            "difficulty_adaptation_rate",
        ],
    }


def test_personalized_resource_flow_matches_acceptance_report() -> None:
    actual = _run_matrix()
    report_path = ROOT / "reports" / "generated" / "personalized-flow-matrix.json"
    expected = json.loads(report_path.read_text(encoding="utf-8"))

    assert actual == expected
