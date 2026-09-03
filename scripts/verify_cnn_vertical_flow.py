"""Verify the reviewable CNN evidence-to-resource path without network access."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from skillforge_kb.agents.resource_agent import ResourceGenerationAgent
from skillforge_kb.evidence.manifest import load_evidence_index
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.concept_attributes import load_concept_attributes
from skillforge_kb.ontology.models import AssessmentStatus, KnowledgeMastery
from skillforge_kb.ontology.resource_blueprints import load_resource_blueprints
from skillforge_kb.planning.adaptation import NodeWeightEngine
from skillforge_kb.planning.planner import CoursePlanner
from skillforge_kb.platform.runtime import (
    DefaultPlatformPaths,
    build_default_profile_agent_adapter,
)
from skillforge_kb.resources.briefs import ResourceBriefBuilder
from skillforge_kb.resources.evidence_bundle import build_evidence_bundle


def main(evidence_file: Path | None = None) -> None:
    root = Path(__file__).resolve().parents[1]
    paths = DefaultPlatformPaths.from_project_root(root)
    catalog = OntologyCatalog.load(paths.course_file, paths.relations_file)
    attributes = load_concept_attributes(catalog, paths.attributes_file)
    blueprints = load_resource_blueprints(catalog, paths.blueprints_file)
    evidence_path = evidence_file or (
        root / "examples" / "evidence" / "cnn_intro_manifest.yaml"
    )
    evidence = load_evidence_index(catalog, evidence_path)
    adapter = build_default_profile_agent_adapter(root)
    raw = json.loads(
        (root / "examples" / "test_profiles" / "profile_mid.json").read_text(
            encoding="utf-8"
        )
    )
    profile = adapter.adapt(raw).snapshot
    prerequisite = KnowledgeMastery(
        concept_id="dl.vision.image-tensor",
        mastery_score=0.85,
        assessment_status=AssessmentStatus.ASSESSED,
        confidence=0.90,
        observed_at=datetime.now(UTC),
        evidence_refs=["demo-prerequisite"],
    )
    profile = profile.model_copy(
        update={"knowledge_mastery": [*profile.knowledge_mastery, prerequisite]}
    )
    path = CoursePlanner(catalog).plan(
        profile, target_concept_id="dl.cnn.convolution"
    )
    node = next(item for item in path.nodes if item.concept_id == "dl.cnn.convolution")
    adaptation = NodeWeightEngine(catalog, attributes).evaluate(profile, node, set())
    handoff = ResourceBriefBuilder(
        catalog=catalog,
        blueprints=blueprints,
        adaptations=(adaptation,),
        evidence_index=evidence,
    ).build_handoff(path, profile, node.concept_id)
    bundle = build_evidence_bundle(handoff, evidence)
    result = ResourceGenerationAgent().generate_strict(handoff, bundle)
    assert result.formal_package is not None
    citations = sum(
        len(item.citations)
        for artifact in result.formal_package.artifacts
        for item in artifact.items
    )
    print(
        f"gate={handoff.generation_gate.status} "
        f"records={len(bundle.records)} artifacts={len(result.formal_package.artifacts)} "
        f"items={sum(len(a.items) for a in result.formal_package.artifacts)} "
        f"citations={citations}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Verify the CNN evidence-to-resource path without network access."
    )
    parser.add_argument(
        "--evidence-file",
        type=Path,
        help="Evidence manifest to validate (defaults to the demo manifest).",
    )
    args = parser.parse_args()
    main(args.evidence_file)
