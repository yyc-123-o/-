import json
from pathlib import Path

from skillforge_kb.agents.candidate_resource_pipeline import InputFolderResourceAgent


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _input_folder(tmp_path: Path, *, gate_allowed: bool = False, published: bool = False) -> Path:
    _write_json(
        tmp_path / "学情画像输出-最终版.json",
        {
            "profile_id": "PROFILE-1",
            "learning_scope": {"chapter_id": "ch03", "chapter_name": "卷积神经网络"},
            "knowledge_mastery": {"global_theta": 0.32},
            "error_patterns": {"items": [{"name": "概念混淆", "ratio": 0.42}]},
            "learning_preferences": {"format": {"content_order": ["概念", "公式", "代码"]}},
            "resource_generation_hints": {"target_depth": "advanced"},
        },
    )
    _write_json(
        tmp_path / "resource_agent_handoff_cnn.json",
        {
            "profile_id": "PROFILE-1",
            "concept_id": "dl.cnn.convolution",
            "depth": "intro",
            "learning_requirements": {"learning_outcomes": ["解释卷积。", "计算输出尺寸。"]},
            "resource_generation_gate": {
                "allowed": gate_allowed,
                "blocking_details": [] if gate_allowed else ["图像张量前置未完成"],
            },
        },
    )
    status = "published" if published else "candidate"
    license_status = "approved" if published else "unregistered"
    _write_json(
        tmp_path / "domain_retrieval_agent_output_cnn.json",
        {
            "request": {
                "profile_id": "PROFILE-1",
                "concept_id": "dl.cnn.convolution",
                "depth": "intro",
            },
            "candidate_evidence": [
                {
                    "chunk_id": "definition-1",
                    "content_kind": "definition",
                    "review_status": status,
                    "evidence_status": status,
                    "license_status": license_status,
                },
                {
                    "chunk_id": "code-1",
                    "content_kind": "code",
                    "review_status": status,
                    "evidence_status": status,
                    "license_status": license_status,
                },
                {
                    "chunk_id": "exercise-1",
                    "content_kind": "exercise",
                    "review_status": status,
                    "evidence_status": status,
                    "license_status": license_status,
                },
            ],
        },
    )
    return tmp_path


def _publication_manifest(folder: Path) -> None:
    _write_json(
        folder / "evidence_publication_manifest.json",
        {
            "concept_id": "dl.cnn.convolution",
            "depth": "intro",
            "records": [
                {
                    "evidence_id": evidence_id,
                    "review_status": "published",
                    "evidence_status": "published",
                    "license_status": "allowed",
                }
                for evidence_id in ("definition-1", "code-1", "exercise-1")
            ],
        },
    )


def test_blocked_handoff_does_not_generate_without_candidate_opt_in(tmp_path: Path) -> None:
    package = InputFolderResourceAgent().build(_input_folder(tmp_path))

    assert package.release_status == "blocked"
    assert package.resources == ()
    assert package.quality_report["planning_gate_allowed"] is False


def test_candidate_opt_in_generates_governed_three_resource_package(tmp_path: Path) -> None:
    package = InputFolderResourceAgent().build(
        _input_folder(tmp_path), allow_candidate_drafts=True
    )

    assert package.release_status == "candidate_draft"
    assert [item.resource_type for item in package.resources] == [
        "lecture_notes",
        "pytorch_practical_guide",
        "layered_assessment",
        "assessment_answer_key",
    ]
    assert package.decision_card["target"]["delivery_depth"] == "intro"
    assert package.evidence_matrix["resource_bindings"][0]["citation_status"] == "candidate_draft"
    assert package.notebook is not None
    assert package.quality_report["notebook_validation"]["status"] == "passed"
    assert package.quality_report["coverage_report"]["passed"] is True
    assert len(package.assessment_blueprint) == 8
    assert package.quality_report["claim_evidence_coverage"]["all_claims_have_evidence"] is True
    assert len(package.claim_evidence_ledger) == 6
    assert package.quality_report["personalization_trace_coverage"][
        "all_input_fields_have_output_effect"
    ] is True
    assert len(package.personalization_trace) == 8
    assert package.quality_report["missing_published_evidence_kinds"] == [
        "code",
        "definition",
        "exercise",
    ]


def test_published_package_requires_gate_and_all_evidence_kinds(tmp_path: Path) -> None:
    package = InputFolderResourceAgent().build(
        _input_folder(tmp_path, gate_allowed=True, published=True)
    )

    assert package.release_status == "published"
    assert len(package.resources) == 4
    assert package.quality_report["checks"]["formal_publish_allowed"] is True


def test_publication_manifest_can_upgrade_reviewed_candidate_evidence(tmp_path: Path) -> None:
    folder = _input_folder(tmp_path, gate_allowed=True)
    _publication_manifest(folder)

    package = InputFolderResourceAgent().build(folder)

    assert package.release_status == "published"
    assert package.quality_report["published_evidence_count"] == 3


def test_profile_features_change_scaffolding_and_visual_assets(tmp_path: Path) -> None:
    folder = _input_folder(tmp_path)
    profile_path = folder / "学情画像输出-最终版.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["ability_level"] = {
        "sub_dimensions": {
            "coding_ability": {"score": 0.30},
            "mathematical_foundation": {"score": 0.40},
        }
    }
    profile["knowledge_mastery"]["points"] = {
        "kp_cnn": {"mastery": 0.15, "status": "not_learned"}
    }
    profile["learning_scope"]["primary_kp_id"] = "kp_cnn"
    profile["learning_preferences"]["style"] = {"visual_learner": False}
    _write_json(profile_path, profile)

    package = InputFolderResourceAgent().build(folder, allow_candidate_drafts=True)

    policy = package.personalization_plan["scaffolding_policy"]
    assert "代码基础较弱" in policy["coding_strategy"]
    assert "数学支撑不足" in policy["math_strategy"]
    assert package.visual_assets == {}


def test_export_preserves_candidate_label(tmp_path: Path) -> None:
    agent = InputFolderResourceAgent()
    package = agent.build(_input_folder(tmp_path / "input"), allow_candidate_drafts=True)
    paths = agent.export(package, tmp_path / "output")

    assert {path.name for path in paths} >= {
        "01_resource_decision_card.json",
        "02_evidence_matrix.json",
        "03_quality_report.json",
        "04_assessment_blueprint.json",
        "08_claim_evidence_ledger.json",
        "09_personalization_trace.json",
        "resource_package.json",
        "lecture_notes.md",
        "assessment_answer_key.md",
        "pytorch_practical_notebook.ipynb",
    }
    manifest_path = tmp_path / "output" / "resource_package.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["release_status"] == "candidate_draft"
