from pathlib import Path

import pytest
import yaml

from skillforge_kb.ontology.models import ProfileIdMapping, ProfileMappingDocument
from skillforge_kb.ontology.profile import ProfileAdaptationError, ProfileAdapter


def _complete_raw_profile() -> dict[str, object]:
    return {
        "profile_meta": {
            "profile_id": "STU-2026-0001",
            "graph_version": "ai-course-v1",
            "observed_at": "2026-07-27T10:25:00Z",
            "generated_at": "2026-07-27T14:30:00Z",
            "assessment_runs": ["adaptive-test-2026-07-27-v1"],
        },
        "basic_info": {"learner_id": "LRN-AI-0042"},
        "dimension_1_knowledge_mastery": {
            "assessed_nodes": [
                {
                    "kg_node_id": "KG-DL-004",
                    "mastery_score": 0.30,
                    "status": "not_learned",
                    "confidence": 0.90,
                    "evidence_refs": ["adaptive-test-2026-07-27-v1:q12-q15"],
                    "last_tested": "2026-07-27T10:25:00Z",
                }
            ]
        },
        "dimension_2_ability_level": {
            "sub_dimensions": {
                "theoretical_understanding": {
                    "score": 0.55,
                    "confidence": 0.80,
                    "assessment_run_id": "adaptive-test-2026-07-27-v1",
                },
                "coding_ability": {
                    "score": 0.70,
                    "confidence": 0.75,
                    "assessment_run_id": "adaptive-test-2026-07-27-v1",
                },
                "mathematical_foundation": {
                    "score": 0.50,
                    "confidence": 0.70,
                    "assessment_run_id": "adaptive-test-2026-07-27-v1",
                },
                "problem_solving": {
                    "score": 0.60,
                    "confidence": 0.78,
                    "assessment_run_id": "adaptive-test-2026-07-27-v1",
                },
            }
        },
        "dimension_3_error_patterns": {
            "error_distribution": {
                "concept_confusion": {
                    "count": 3,
                    "ratio": 0.60,
                    "kg_nodes_involved": ["KG-DL-004"],
                    "evidence_refs": ["adaptive-test-2026-07-27-v1:q13"],
                }
            }
        },
        "dimension_4_learning_preferences": {
            "format_preferences": {
                "preferred_content_order": [
                    "concept_intuition",
                    "mathematical_derivation",
                    "code_practice",
                ],
                "code_language": "Python",
                "framework": "PyTorch",
                "jupyter_notebook": True,
            },
            "style_preferences": {
                "visual_learner": True,
                "prefers_diagrams": True,
                "prefers_math_formulas": True,
                "prefers_step_by_step": True,
                "prefers_comparison_tables": True,
            },
            "pace_preferences": {"estimated_hours_per_week": 8},
            "motivation_profile": {"prefers_project_driven": True},
        },
    }


@pytest.fixture
def reviewed_mapping() -> ProfileIdMapping:
    return ProfileIdMapping(
        legacy_id="KG-DL-004",
        concept_id="dl.cnn.architecture",
        graph_version="ai-course-v1",
        reviewed_by="ontology-reviewer",
    )


def test_production_mapping_manifest_is_empty() -> None:
    mapping_path = (
        Path(__file__).parents[3] / "resources" / "ontology" / "legacy_profile_ids_v1.yaml"
    )
    document = ProfileMappingDocument.model_validate(
        yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    )

    assert document.mappings == []


def test_adapter_preserves_complete_profile_facts(catalog, reviewed_mapping) -> None:
    snapshot = ProfileAdapter(catalog, mappings=[reviewed_mapping]).adapt(
        _complete_raw_profile()
    )

    assert snapshot.profile_id == "STU-2026-0001"
    assert snapshot.assessment_runs == ["adaptive-test-2026-07-27-v1"]
    assert snapshot.observed_at is not None
    assert snapshot.generated_at is not None
    assert snapshot.knowledge_mastery[0].concept_id == "dl.cnn.architecture"
    assert snapshot.knowledge_mastery[0].evidence_refs == [
        "adaptive-test-2026-07-27-v1:q12-q15"
    ]
    assert set(snapshot.abilities) == {
        "theoretical_understanding",
        "coding_ability",
        "mathematical_foundation",
        "problem_solving",
    }
    assert snapshot.abilities["coding_ability"].score == 0.70
    assert snapshot.abilities["coding_ability"].confidence == 0.75
    assert snapshot.abilities["coding_ability"].assessment_run_id == (
        "adaptive-test-2026-07-27-v1"
    )
    assert snapshot.error_patterns[0].code == "concept_confusion"
    assert snapshot.error_patterns[0].concept_ids == ["dl.cnn.architecture"]
    assert snapshot.error_patterns[0].evidence_refs == [
        "adaptive-test-2026-07-27-v1:q13"
    ]
    assert snapshot.preferences.content_order == [
        "concept_intuition",
        "mathematical_derivation",
        "code_practice",
    ]
    assert snapshot.preferences.code_language == "Python"
    assert snapshot.preferences.framework == "PyTorch"
    assert snapshot.preferences.presentation == [
        "jupyter_notebook",
        "visual",
        "diagrams",
        "math_formulas",
        "step_by_step",
        "comparison_tables",
    ]
    assert snapshot.preferences.pace_hours_per_week == 8
    assert snapshot.preferences.project_orientation == "project_driven"


def test_adapter_accepts_top_level_assessment_runs(catalog) -> None:
    mapping = ProfileIdMapping(
        legacy_id="KG-DL-004",
        concept_id="dl.cnn.architecture",
        graph_version="ai-course-v1",
        reviewed_by="ontology-reviewer",
    )
    raw = _complete_raw_profile()
    meta = raw["profile_meta"]
    assert isinstance(meta, dict)
    assessment_runs = meta.pop("assessment_runs")
    assert isinstance(assessment_runs, list)
    raw["assessment_runs"] = [*assessment_runs, "questionnaire-2026-07-27-v1"]

    snapshot = ProfileAdapter(catalog, mappings=[mapping]).adapt(raw)

    assert snapshot.assessment_runs == [
        "adaptive-test-2026-07-27-v1",
        "questionnaire-2026-07-27-v1",
    ]


def test_adapter_rejects_conflicting_assessment_run_locations(catalog) -> None:
    raw = _complete_raw_profile()
    raw["assessment_runs"] = ["different-assessment-run"]
    mapping = ProfileIdMapping(
        legacy_id="KG-DL-004",
        concept_id="dl.cnn.architecture",
        graph_version="ai-course-v1",
        reviewed_by="ontology-reviewer",
    )

    with pytest.raises(ProfileAdaptationError, match="conflicting assessment_runs"):
        ProfileAdapter(catalog, mappings=[mapping]).adapt(raw)


def test_adapter_rejects_explicit_empty_assessment_runs_with_ability_reference(
    catalog,
) -> None:
    raw = _complete_raw_profile()
    meta = raw["profile_meta"]
    assert isinstance(meta, dict)
    meta["assessment_runs"] = []
    mapping = ProfileIdMapping(
        legacy_id="KG-DL-004",
        concept_id="dl.cnn.architecture",
        graph_version="ai-course-v1",
        reviewed_by="ontology-reviewer",
    )

    with pytest.raises(ProfileAdaptationError, match="undeclared assessment run"):
        ProfileAdapter(catalog, mappings=[mapping]).adapt(raw)


def test_mapping_loader_rejects_unknown_mapping_document_version(catalog, tmp_path) -> None:
    path = tmp_path / "legacy_profile_ids.yaml"
    path.write_text(
        "version: profile-id-map-v2\n"
        "graph_version: ai-course-v1\n"
        "mappings: []\n",
        encoding="utf-8",
    )

    with pytest.raises(ProfileAdaptationError, match="mapping document version"):
        ProfileAdapter.load_mappings(catalog, path)


def test_adapter_rejects_duplicate_mapping_target(catalog) -> None:
    mappings = [
        ProfileIdMapping(
            legacy_id=legacy_id,
            concept_id="dl.cnn.architecture",
            graph_version="ai-course-v1",
            reviewed_by="ontology-reviewer",
        )
        for legacy_id in ("KG-DL-004", "KG-DL-004-ALIAS")
    ]

    with pytest.raises(ProfileAdaptationError, match="duplicate canonical concept mapping"):
        ProfileAdapter(catalog, mappings=mappings)


def test_adapter_rejects_duplicate_legacy_mapping(catalog) -> None:
    mapping = ProfileIdMapping(
        legacy_id="KG-DL-004",
        concept_id="dl.cnn.architecture",
        graph_version="ai-course-v1",
        reviewed_by="ontology-reviewer",
    )

    with pytest.raises(ProfileAdaptationError, match="duplicate legacy profile ID"):
        ProfileAdapter(catalog, mappings=[mapping, mapping])


def test_adapter_rejects_mapping_for_another_graph_version(catalog) -> None:
    mapping = ProfileIdMapping(
        legacy_id="KG-DL-004",
        concept_id="dl.cnn.architecture",
        graph_version="ai-course-v2",
        reviewed_by="ontology-reviewer",
    )

    with pytest.raises(ProfileAdaptationError, match="mapping graph version mismatch"):
        ProfileAdapter(catalog, mappings=[mapping])


def test_adapter_rejects_mapping_to_unknown_concept(catalog) -> None:
    mapping = ProfileIdMapping(
        legacy_id="KG-DL-004",
        concept_id="unknown.concept",
        graph_version="ai-course-v1",
        reviewed_by="ontology-reviewer",
    )

    with pytest.raises(ProfileAdaptationError, match="mapping targets unknown concept"):
        ProfileAdapter(catalog, mappings=[mapping])


def test_adapter_rejects_duplicate_mastery_concept(catalog) -> None:
    mapping = ProfileIdMapping(
        legacy_id="KG-DL-004",
        concept_id="dl.cnn.architecture",
        graph_version="ai-course-v1",
        reviewed_by="ontology-reviewer",
    )
    raw = _complete_raw_profile()
    mastery = raw["dimension_1_knowledge_mastery"]
    assert isinstance(mastery, dict)
    assessed_nodes = mastery["assessed_nodes"]
    assert isinstance(assessed_nodes, list)
    assessed_nodes.append(dict(assessed_nodes[0]))

    with pytest.raises(ProfileAdaptationError, match="duplicate mastery concept"):
        ProfileAdapter(catalog, mappings=[mapping]).adapt(raw)


def test_adapter_rejects_unknown_error_pattern_concept(catalog) -> None:
    mapping = ProfileIdMapping(
        legacy_id="KG-DL-004",
        concept_id="dl.cnn.architecture",
        graph_version="ai-course-v1",
        reviewed_by="ontology-reviewer",
    )
    raw = _complete_raw_profile()
    errors = raw["dimension_3_error_patterns"]
    assert isinstance(errors, dict)
    distribution = errors["error_distribution"]
    assert isinstance(distribution, dict)
    pattern = distribution["concept_confusion"]
    assert isinstance(pattern, dict)
    pattern["kg_nodes_involved"] = ["KG-ML-001"]

    with pytest.raises(ProfileAdaptationError, match="KG-ML-001"):
        ProfileAdapter(catalog, mappings=[mapping]).adapt(raw)


def test_adapter_rejects_missing_ability_confidence(catalog) -> None:
    mapping = ProfileIdMapping(
        legacy_id="KG-DL-004",
        concept_id="dl.cnn.architecture",
        graph_version="ai-course-v1",
        reviewed_by="ontology-reviewer",
    )
    raw = _complete_raw_profile()
    abilities = raw["dimension_2_ability_level"]
    assert isinstance(abilities, dict)
    sub_dimensions = abilities["sub_dimensions"]
    assert isinstance(sub_dimensions, dict)
    coding = sub_dimensions["coding_ability"]
    assert isinstance(coding, dict)
    del coding["confidence"]

    with pytest.raises(ProfileAdaptationError, match="coding_ability.confidence"):
        ProfileAdapter(catalog, mappings=[mapping]).adapt(raw)


def test_adapter_rejects_profile_graph_version_mismatch(catalog) -> None:
    raw = _complete_raw_profile()
    meta = raw["profile_meta"]
    assert isinstance(meta, dict)
    meta["graph_version"] = "ai-course-v2"

    with pytest.raises(ProfileAdaptationError, match="profile graph version"):
        ProfileAdapter(catalog, mappings=[]).adapt(raw)


@pytest.mark.parametrize("field", ["recommendation", "depth_prescription"])
def test_adapter_rejects_nested_downstream_fields(catalog, field: str) -> None:
    raw = _complete_raw_profile()
    mastery = raw["dimension_1_knowledge_mastery"]
    assert isinstance(mastery, dict)
    assessed_nodes = mastery["assessed_nodes"]
    assert isinstance(assessed_nodes, list)
    node = assessed_nodes[0]
    assert isinstance(node, dict)
    node[field] = "intro"

    with pytest.raises(ProfileAdaptationError, match=field):
        ProfileAdapter(catalog, mappings=[]).adapt(raw)


def test_adapter_rejects_score_for_unexplored_mastery(catalog) -> None:
    mapping = ProfileIdMapping(
        legacy_id="KG-DL-004",
        concept_id="dl.cnn.architecture",
        graph_version="ai-course-v1",
        reviewed_by="ontology-reviewer",
    )
    raw = _complete_raw_profile()
    mastery = raw["dimension_1_knowledge_mastery"]
    assert isinstance(mastery, dict)
    assessed_nodes = mastery["assessed_nodes"]
    assert isinstance(assessed_nodes, list)
    node = assessed_nodes[0]
    assert isinstance(node, dict)
    node["status"] = "unexplored"
    node["mastery_score"] = 0.05
    node["last_tested"] = None

    with pytest.raises(ProfileAdaptationError, match="unexplored score must be null"):
        ProfileAdapter(catalog, mappings=[mapping]).adapt(raw)


def test_adapter_rejects_unknown_mastery_status(catalog) -> None:
    mapping = ProfileIdMapping(
        legacy_id="KG-DL-004",
        concept_id="dl.cnn.architecture",
        graph_version="ai-course-v1",
        reviewed_by="ontology-reviewer",
    )
    raw = _complete_raw_profile()
    mastery = raw["dimension_1_knowledge_mastery"]
    assert isinstance(mastery, dict)
    assessed_nodes = mastery["assessed_nodes"]
    assert isinstance(assessed_nodes, list)
    node = assessed_nodes[0]
    assert isinstance(node, dict)
    node["status"] = "unexplorred"

    with pytest.raises(ProfileAdaptationError, match="unsupported status"):
        ProfileAdapter(catalog, mappings=[mapping]).adapt(raw)


@pytest.mark.parametrize("legacy_id", ["KG-UNKNOWN-999", "KG-ML-001"])
def test_adapter_rejects_unmapped_or_composite_legacy_id(catalog, legacy_id: str) -> None:
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
                    "kg_node_id": legacy_id,
                    "mastery_score": 0.88,
                    "status": "mastered",
                    "confidence": 0.9,
                    "evidence_refs": ["test-run-1:q1"],
                    "last_tested": "2026-07-28T00:00:00Z",
                }
            ]
        },
    }

    with pytest.raises(ProfileAdaptationError, match=legacy_id):
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


def test_adapter_rejects_resource_generation_hints(catalog) -> None:
    adapter = ProfileAdapter(catalog, mappings=[])

    with pytest.raises(ProfileAdaptationError, match="resource_generation_hints"):
        adapter.adapt(
            {
                "profile_meta": {"profile_id": "p-3", "graph_version": "ai-course-v1"},
                "basic_info": {"learner_id": "learner-3"},
                "dimension_1_knowledge_mastery": {"assessed_nodes": []},
                "resource_generation_hints": {},
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
