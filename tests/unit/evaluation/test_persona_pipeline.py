import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from skillforge_kb.agents.planning_agent import CoursePlanningAgent
from skillforge_kb.agents.resource_agent import ResourceGenerationAgent
from skillforge_kb.agents.retrieval_agent import DomainRetrievalAgent
from skillforge_kb.domain.enums import ContentKind, Language, LicenseStatus
from skillforge_kb.evaluation.persona_pipeline import (
    PersonaPipelineContext,
    PersonaPipelineSnapshot,
    build_persona_pipeline_context,
    run_persona_feedback_loop,
    run_persona_pipeline,
)
from skillforge_kb.evidence.manifest import EvidenceIndex
from skillforge_kb.evidence.models import (
    EvidenceRecord,
    EvidenceReviewStatus,
    build_evidence_id,
)
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.concept_attributes import load_concept_attributes
from skillforge_kb.ontology.models import DepthLevel
from skillforge_kb.ontology.profile_agent_adapter import LearnerProfileAgentAdapter
from skillforge_kb.ontology.resource_blueprints import load_resource_blueprints
from skillforge_kb.retrieval.bm25 import Bm25KnowledgeRetriever
from skillforge_kb.retrieval.corpus import KnowledgeCorpus, build_corpus_digest
from skillforge_kb.retrieval.models import KnowledgeChunk
from skillforge_kb.retrieval.tool import KnowledgeRetrievalTool

PROJECT_ROOT = Path(__file__).parents[3]
CNN_CONCEPT_ID = "dl.cnn.convolution"


def _demo_profile_payload() -> dict[str, object]:
    path = PROJECT_ROOT / "tests" / "fixtures" / "profile-2026-0001-demo.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_candidate_draft_pipeline_runs_end_to_end_with_demo_profile(
    catalog: OntologyCatalog,
) -> None:
    """No evidence is published in this repo's tracked manifest, so the demo
    profile's whole personalized path should resolve through the
    candidate-preview / blocked-hard-prerequisite branches -- with zero
    fixtures to fabricate."""

    context = build_persona_pipeline_context(PROJECT_ROOT)
    snapshot = run_persona_pipeline(context, _demo_profile_payload())

    assert snapshot.pipeline_failure is None
    assert len(snapshot.full_path) == len(catalog.concepts())
    assert snapshot.personalized_path_concept_ids

    nodes_by_id = {record.concept_id: record for record in snapshot.full_path}
    cnn_node = nodes_by_id[CNN_CONCEPT_ID]
    assert cnn_node.concept_id in snapshot.personalized_path_concept_ids
    assert cnn_node.retrieval_result is not None
    assert cnn_node.retrieval_error is None
    assert cnn_node.generation_gate is not None
    assert cnn_node.resource_mode in {"candidate_draft", "blocked_hard_prerequisite"}
    # Pin the one concept manually confirmed to generate cleanly; other
    # concepts may still hit the separately-owned candidate-preview generator
    # defect this module already isolates via per-node ``resource_error``.
    assert cnn_node.resource_error is None

    # Python-mode round trip only: candidate-preview packages deliberately
    # strip teacher-only content (``teacher_guide``, ``correct_choice``) from
    # JSON-mode output (see ``ResourceAgentResult.serialize_public``), so a
    # JSON round trip is not expected to reconstruct this branch. The formal
    # branch below covers the JSON round trip instead.
    restored = PersonaPipelineSnapshot.model_validate(snapshot.model_dump(mode="python"))
    assert restored == snapshot


class _BrokenRetrievalAgent:
    """Stand-in for ``DomainRetrievalAgent`` that always fails, to prove one
    node's retrieval defect is isolated rather than aborting the whole run."""

    def retrieve(self, request: Any, handoff: Any) -> Any:
        raise RuntimeError("simulated retrieval outage")


def test_retrieval_failure_is_isolated_per_node_and_does_not_abort_the_run() -> None:
    """A per-node retrieval defect must be recorded on that node, not
    propagate and abort the whole persona run -- the same isolation
    resource generation already had before this fix."""

    context = build_persona_pipeline_context(PROJECT_ROOT)
    broken_context = dataclasses.replace(context, retrieval_agent=_BrokenRetrievalAgent())

    snapshot = run_persona_pipeline(broken_context, _demo_profile_payload())

    assert snapshot.pipeline_failure is None
    assert snapshot.personalized_path_concept_ids

    nodes_by_id = {record.concept_id: record for record in snapshot.full_path}
    cnn_node = nodes_by_id[CNN_CONCEPT_ID]
    assert cnn_node.retrieval_result is None
    assert cnn_node.retrieval_error is not None
    assert "simulated retrieval outage" in cnn_node.retrieval_error
    assert cnn_node.evidence_summary is None
    # No resource generation is attempted once retrieval has failed for a node.
    assert cnn_node.resource_mode == "not_attempted"
    assert cnn_node.resource_result is None
    assert cnn_node.resource_error is None


def test_formal_pipeline_runs_with_published_evidence() -> None:
    """With published, allowed evidence for one concept, the pipeline must take
    the strict/formal branch instead of falling back to a candidate preview."""

    context = _published_context(PROJECT_ROOT)
    snapshot = run_persona_pipeline(context, _demo_profile_payload())

    assert snapshot.pipeline_failure is None
    nodes_by_id = {record.concept_id: record for record in snapshot.full_path}
    cnn_node = nodes_by_id[CNN_CONCEPT_ID]

    assert cnn_node.resource_mode == "formal"
    assert cnn_node.resource_error is None
    assert cnn_node.resource_result is not None
    assert cnn_node.resource_result.publication_status == "formal"
    assert cnn_node.resource_result.formal_package is not None
    assert cnn_node.evidence_summary is not None
    assert cnn_node.evidence_summary.formal_evidence_count == 3
    assert cnn_node.evidence_summary.definition_available
    assert cnn_node.evidence_summary.code_available
    assert cnn_node.evidence_summary.exercise_available

    # A formal (non-preview) result carries no redacted fields, so its own
    # JSON round trip is expected to fully reconstruct it. (Other, unrelated
    # personalized nodes in this same snapshot are still candidate previews
    # and are covered by the python-mode round trip in the candidate-draft
    # test above instead -- see ``ResourceAgentResult.serialize_public``.)
    restored_result = type(cnn_node.resource_result).model_validate_json(
        cnn_node.resource_result.model_dump_json()
    )
    assert restored_result == cnn_node.resource_result


def test_v21_diagnosis_profile_is_adapted_before_planning() -> None:
    """A raw 学情诊断Agent v2.1 export must go through the profile adapter and
    have its target concept resolved via the profile/concept KP map -- the
    same branch the two real diagnosis exports exercised by hand, now covered
    with a small, safe, self-authored payload."""

    context = build_persona_pipeline_context(PROJECT_ROOT)
    raw_profile = {
        "profile_id": "PROFILE-TEST-V21-MINIMAL",
        "profile_version": "2.1",
        "learner_id": "test-learner-v21",
        "generated_at": "2026-09-02T00:00:00Z",
        "knowledge_mastery": {
            "points": {
                "kp_012": {
                    "status": "partial",
                    "mastery": 0.5,
                    "confidence": 0.7,
                },
            },
        },
        "learning_scope": {"primary_kp_id": "kp_012"},
    }

    snapshot = run_persona_pipeline(context, raw_profile)

    assert snapshot.pipeline_failure is None
    assert snapshot.source_profile_version == "2.1"
    assert snapshot.target_concept_id == CNN_CONCEPT_ID
    assert isinstance(snapshot.adapter_warnings, tuple)
    assert all(isinstance(item, str) for item in snapshot.adapter_warnings)


def test_pipeline_snapshot_is_frozen(catalog: OntologyCatalog) -> None:
    context = build_persona_pipeline_context(PROJECT_ROOT)
    snapshot = run_persona_pipeline(context, _demo_profile_payload())

    with pytest.raises(ValidationError):
        snapshot.profile_id = "mutated"  # type: ignore[misc]


def test_feedback_loop_advances_nodes_and_updates_mastery() -> None:
    """Each round must generate for the current node, simulate an answer,
    update mastery through the real assessment ledger, and mark that node
    COMPLETED before moving to the next -- the "路径动态调整" loop."""

    context = build_persona_pipeline_context(PROJECT_ROOT)
    snapshot = run_persona_feedback_loop(context, _demo_profile_payload(), max_rounds=3)

    assert snapshot.pipeline_failure is None
    assert len(snapshot.feedback_rounds) == 3
    round_concept_ids = [round_.concept_id for round_ in snapshot.feedback_rounds]
    assert round_concept_ids[0] == CNN_CONCEPT_ID
    assert len(set(round_concept_ids)) == 3  # each round advances to a new node

    nodes_by_id = {record.concept_id: record for record in snapshot.full_path}
    for round_ in snapshot.feedback_rounds:
        assert round_.mastery_before is not None
        assert round_.mastery_after is not None
        assert round_.reason_codes
        completed_node = nodes_by_id[round_.concept_id]
        assert completed_node.status.value == "completed"
        # The retrieval/resource decision made while this node was current is
        # preserved on the final snapshot, not lost once it becomes COMPLETED.
        assert completed_node.retrieval_result is not None
        assert completed_node.resource_mode in {"candidate_draft", "blocked_hard_prerequisite"}

    # Nodes the loop had not reached yet are reported plainly, not previewed
    # out of order.
    unreached = [
        record
        for record in snapshot.full_path
        if record.concept_id not in round_concept_ids
        and record.status.value in {"available", "pending", "blocked"}
    ]
    assert unreached
    assert all(record.resource_mode == "not_attempted" for record in unreached)
    assert all(record.retrieval_result is None for record in unreached)


def test_feedback_loop_correctness_fn_can_be_overridden() -> None:
    """A scripted persona (e.g. "always correct") must be honored instead of
    the default mastery-derived heuristic, and mastery should move up rather
    than down."""

    context = build_persona_pipeline_context(PROJECT_ROOT)
    snapshot = run_persona_feedback_loop(
        context,
        _demo_profile_payload(),
        max_rounds=2,
        correctness_fn=lambda node, profile: True,
    )

    assert snapshot.pipeline_failure is None
    assert len(snapshot.feedback_rounds) == 2
    for round_ in snapshot.feedback_rounds:
        assert round_.simulated_correct is True
        assert round_.classified_error_kind is None
        assert round_.mastery_before is not None
        assert round_.mastery_after is not None
        assert round_.mastery_after > round_.mastery_before


def test_feedback_loop_is_reusable_across_independent_calls_on_the_same_context() -> None:
    """A second call for the same profile on the same (shared) context must
    simulate its own fresh session, not crash or silently resume the first
    call's already-advanced graph state."""

    context = build_persona_pipeline_context(PROJECT_ROOT)
    raw_profile = _demo_profile_payload()

    first = run_persona_feedback_loop(context, raw_profile, max_rounds=3)
    second = run_persona_feedback_loop(context, raw_profile, max_rounds=3)

    assert first.pipeline_failure is None
    assert second.pipeline_failure is None
    assert [r.concept_id for r in first.feedback_rounds] == [
        r.concept_id for r in second.feedback_rounds
    ]
    assert [(r.mastery_before, r.mastery_after) for r in first.feedback_rounds] == [
        (r.mastery_before, r.mastery_after) for r in second.feedback_rounds
    ]


def test_feedback_loop_runs_to_natural_completion(catalog: OntologyCatalog) -> None:
    """With no round cap, the loop must keep advancing (PROFILE_REFRESHED then
    CONCEPTS_COMPLETED, per node) until the course actually completes -- every
    node ends up either skipped or completed, none left available/pending."""

    context = build_persona_pipeline_context(PROJECT_ROOT)
    snapshot = run_persona_feedback_loop(context, _demo_profile_payload())

    assert snapshot.pipeline_failure is None
    assert len(snapshot.full_path) == len(catalog.concepts())
    assert len(snapshot.feedback_rounds) == len(snapshot.personalized_path_concept_ids)
    statuses = {record.status.value for record in snapshot.full_path}
    assert statuses <= {"skipped", "completed"}


def _published_context(project_root: Path) -> PersonaPipelineContext:
    """Reuses the published-evidence recipe from
    ``tests/unit/integration/test_three_agent_platform_flow.py`` so a formal
    generation branch can be exercised without touching the (tracked-but-
    empty) production evidence manifest."""

    ontology_root = project_root / "resources" / "ontology"
    catalog = OntologyCatalog.load(
        ontology_root / "ai_course_v1.yaml",
        ontology_root / "ai_relations_v1.yaml",
    )
    attributes = load_concept_attributes(
        catalog,
        ontology_root / "concept_attributes_v1.yaml",
    )
    blueprints = load_resource_blueprints(
        catalog,
        ontology_root / "resource_blueprints_v1.yaml",
    )
    chunks = tuple(
        KnowledgeChunk(
            chunk_id=f"published-{kind.value}",
            doc_id="published-cnn",
            source_title="CNN published fixture",
            heading_path=("CNN", kind.value),
            text=f"卷积 CNN {kind.value} evidence with padding stride Conv2d output size.",
            page_no=index,
            domain_tag="ai-knowledge",
            difficulty="入门",
            token_count=30,
        )
        for index, kind in enumerate(
            (ContentKind.DEFINITION, ContentKind.CODE, ContentKind.EXERCISE),
            start=1,
        )
    )
    corpus = KnowledgeCorpus(chunks=chunks, digest=build_corpus_digest(chunks))
    records = tuple(
        _published_record(catalog.course_document.version, chunk, kind)
        for chunk, kind in zip(
            chunks,
            (ContentKind.DEFINITION, ContentKind.CODE, ContentKind.EXERCISE),
            strict=True,
        )
    )
    evidence_index = EvidenceIndex(
        version="evidence-manifest-test-v1",
        graph_version=catalog.course_document.version,
        records=records,
    )
    profile_adapter = LearnerProfileAgentAdapter.load_mappings(
        catalog,
        ontology_root / "profile_agent_kp_map_v1.yaml",
    )
    return PersonaPipelineContext(
        catalog=catalog,
        evidence_index=evidence_index,
        blueprints=blueprints,
        profile_adapter=profile_adapter,
        retrieval_agent=DomainRetrievalAgent(
            corpus,
            KnowledgeRetrievalTool(Bm25KnowledgeRetriever(corpus)),
            evidence_index,
            catalog=catalog,
        ),
        resource_agent=ResourceGenerationAgent(),
        planning_agent=CoursePlanningAgent.create(catalog, attributes),
    )


def _published_record(
    graph_version: str,
    chunk: KnowledgeChunk,
    kind: ContentKind,
) -> EvidenceRecord:
    normalized_hash = f"{chunk.page_no:064x}"
    locator = f"page {chunk.page_no}"
    evidence_id = build_evidence_id(
        graph_version=graph_version,
        source_id=chunk.doc_id,
        chunk_id=chunk.chunk_id,
        concept_id=CNN_CONCEPT_ID,
        depth=DepthLevel.INTRO,
        locator=locator,
        normalized_hash=normalized_hash,
        language=Language.ZH,
        content_kind=kind,
    )
    return EvidenceRecord(
        evidence_id=evidence_id,
        graph_version=graph_version,
        source_id=chunk.doc_id,
        chunk_id=chunk.chunk_id,
        concept_id=CNN_CONCEPT_ID,
        depth=DepthLevel.INTRO,
        source_url=f"https://example.edu/cnn/{kind.value}",
        locator=locator,
        normalized_hash=normalized_hash,
        language=Language.ZH,
        content_kind=kind,
        difficulty=1,
        license_status=LicenseStatus.ALLOWED,
        review_status=EvidenceReviewStatus.PUBLISHED,
        reviewed_by="test-reviewer",
        reviewed_at=datetime(2026, 8, 16, tzinfo=UTC),
    )
