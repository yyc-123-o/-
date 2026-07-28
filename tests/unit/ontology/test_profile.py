import pytest

from skillforge_kb.ontology.models import ProfileIdMapping
from skillforge_kb.ontology.profile import ProfileAdaptationError, ProfileAdapter


def test_adapter_rejects_unmapped_legacy_id(catalog) -> None:
    adapter = ProfileAdapter(catalog, mappings=[])
    raw: dict[str, object] = {
        "profile_meta": {
            "profile_id": "p-1",
            "graph_version": "ai-course-v1",
        },
        "basic_info": {"learner_id": "learner-1"},
        "dimension_1_knowledge_mastery": {
            "assessed_nodes": [
                {
                    "kg_node_id": "KG-ML-001",
                    "mastery_score": 0.88,
                    "status": "mastered",
                    "confidence": 0.9,
                    "evidence_refs": ["test-run-1:q1"],
                    "last_tested": "2026-07-28T00:00:00Z",
                }
            ]
        },
    }

    with pytest.raises(ProfileAdaptationError, match="KG-ML-001"):
        adapter.adapt(raw)


def test_adapter_preserves_not_assessed_score_as_null(catalog) -> None:
    mapping = ProfileIdMapping(
        legacy_id="KG-TEST-001",
        concept_id="math.linear-algebra.vector",
        graph_version="ai-course-v1",
        reviewed_by="ontology-reviewer",
    )
    adapter = ProfileAdapter(catalog, mappings=[mapping])
    raw: dict[str, object] = {
        "profile_meta": {
            "profile_id": "p-2",
            "graph_version": "ai-course-v1",
        },
        "basic_info": {"learner_id": "learner-2"},
        "dimension_1_knowledge_mastery": {
            "assessed_nodes": [
                {
                    "kg_node_id": "KG-TEST-001",
                    "mastery_score": None,
                    "status": "unexplored",
                    "confidence": 0.0,
                    "evidence_refs": [],
                    "last_tested": None,
                }
            ]
        },
    }

    snapshot = adapter.adapt(raw)

    assert snapshot.knowledge_mastery[0].concept_id == "math.linear-algebra.vector"
    assert snapshot.knowledge_mastery[0].assessment_status == "not_assessed"
    assert snapshot.knowledge_mastery[0].mastery_score is None
    assert snapshot.learner_ref != "learner-2"


def test_adapter_rejects_path_or_resource_decisions(catalog) -> None:
    adapter = ProfileAdapter(catalog, mappings=[])

    with pytest.raises(ProfileAdaptationError, match="learning_path_context"):
        adapter.adapt(
            {
                "profile_meta": {"profile_id": "p-3", "graph_version": "ai-course-v1"},
                "basic_info": {"learner_id": "learner-3"},
                "dimension_1_knowledge_mastery": {"assessed_nodes": []},
                "learning_path_context": {},
            }
        )


def test_adapter_rejects_prior_chapter_decisions(catalog) -> None:
    adapter = ProfileAdapter(catalog, mappings=[])

    with pytest.raises(ProfileAdaptationError, match="prior_chapter_performance"):
        adapter.adapt(
            {
                "profile_meta": {"profile_id": "p-4", "graph_version": "ai-course-v1"},
                "basic_info": {"learner_id": "learner-4"},
                "dimension_1_knowledge_mastery": {"assessed_nodes": []},
                "prior_chapter_performance": {},
            }
        )
