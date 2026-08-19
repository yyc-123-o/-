# ruff: noqa: E501
"""Evidence-gated candidate resource generation from upstream Agent handoffs.

Candidate drafts and published teaching resources are deliberately different
states. A draft is available only after an explicit operator opt-in; a resource
is marked published only when the planning gate and formal evidence both pass.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from skillforge_kb.agents.assessment_feedback import (
    blueprint_to_dict,
    build_intro_cnn_blueprint,
)

ReleaseStatus = Literal["blocked", "candidate_draft", "published"]
_REQUIRED_EVIDENCE_KINDS = ("definition", "code", "exercise")


@dataclass(frozen=True)
class CandidateResource:
    resource_type: str
    title: str
    content: str
    evidence_ids: tuple[str, ...]
    release_status: ReleaseStatus


@dataclass(frozen=True)
class CandidateResourcePackage:
    release_status: ReleaseStatus
    target_concept_id: str
    target_depth: str
    decision_card: dict[str, Any]
    evidence_matrix: dict[str, Any]
    quality_report: dict[str, Any]
    resources: tuple[CandidateResource, ...]
    notebook: dict[str, Any] | None
    assessment_blueprint: list[dict[str, object]]
    personalization_plan: dict[str, Any]
    visual_assets: dict[str, str]
    claim_evidence_ledger: list[dict[str, Any]]
    personalization_trace: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InputFolderResourceAgent:
    """Prepare and export a governed resource package from three upstream inputs."""

    def build(
        self,
        input_dir: str | Path,
        *,
        allow_candidate_drafts: bool = False,
    ) -> CandidateResourcePackage:
        root = Path(input_dir).expanduser().resolve()
        profile_file, handoff_file, retrieval_file, manifest_file = self._find_inputs(root)
        profile = _read_json(profile_file)
        handoff = _read_json(handoff_file)
        retrieval = _read_json(retrieval_file)
        manifest = _read_json(manifest_file) if manifest_file else None

        concept_id = _required_text(handoff, "concept_id", handoff_file)
        depth = _required_text(handoff, "depth", handoff_file)
        gate = _mapping(handoff.get("resource_generation_gate"))
        requirements = _mapping(handoff.get("learning_requirements"))
        blockers = _string_list(gate.get("blocking_details"))
        warnings: list[str] = []
        self._validate_scope(profile, handoff, retrieval, depth, blockers, warnings)

        candidates = _candidate_evidence(retrieval, handoff)
        try:
            candidates = _apply_publication_manifest(candidates, manifest, concept_id, depth)
        except ValueError as error:
            blockers.append(str(error))
        published = [item for item in candidates if _is_published(item)]
        candidate_kinds = {str(item.get("content_kind")) for item in candidates}
        published_kinds = {str(item.get("content_kind")) for item in published}
        missing_candidate = sorted(set(_REQUIRED_EVIDENCE_KINDS) - candidate_kinds)
        missing_published = sorted(set(_REQUIRED_EVIDENCE_KINDS) - published_kinds)
        notebook = _build_notebook(profile, handoff)
        notebook_validation = _validate_notebook(notebook)
        if notebook_validation["status"] != "passed":
            blockers.append("实操 Notebook 未通过自动运行校验。")
        formal_ready = (
            gate.get("allowed") is True
            and not blockers
            and not missing_published
            and notebook_validation["status"] == "passed"
        )

        release_status: ReleaseStatus
        if formal_ready:
            release_status = "published"
        elif allow_candidate_drafts:
            release_status = "candidate_draft"
            warnings.append("本次为候选草稿演示，未通过审核前不得作为正式资源发布。")
        else:
            release_status = "blocked"

        personalization_plan = _build_personalization_plan(profile, handoff)
        visual_assets = _build_visual_assets(profile)
        personalization_trace = _personalization_trace(
            profile,
            handoff,
            personalization_plan,
            visual_assets,
        )
        resources = (
            _build_resources(
                profile,
                handoff,
                candidates,
                release_status,
                personalization_plan,
            )
            if release_status != "blocked"
            else ()
        )
        assessment_blueprint = (
            blueprint_to_dict(
                build_intro_cnn_blueprint(tuple(_string_list(requirements.get("learning_outcomes"))))
            )
            if resources
            else []
        )
        decision_card = _decision_card(
            root=root,
            profile_file=profile_file,
            handoff_file=handoff_file,
            retrieval_file=retrieval_file,
            manifest_file=manifest_file,
            profile=profile,
            handoff=handoff,
            concept_id=concept_id,
            depth=depth,
            release_status=release_status,
            blockers=blockers,
            warnings=warnings,
        )
        claim_evidence_ledger = _claim_evidence_ledger(candidates, release_status)
        evidence_matrix = _evidence_matrix(
            resources,
            candidates,
            release_status,
            claim_evidence_ledger,
        )
        quality_report = {
            "release_status": release_status,
            "planning_gate_allowed": gate.get("allowed") is True,
            "candidate_evidence_count": len(candidates),
            "published_evidence_count": len(published),
            "candidate_evidence_kinds": sorted(candidate_kinds),
            "missing_candidate_evidence_kinds": missing_candidate,
            "missing_published_evidence_kinds": missing_published,
            "resource_types_generated": [item.resource_type for item in resources],
            "coverage_report": _coverage_report(profile, requirements, resources),
            "assessment_blueprint_item_count": len(assessment_blueprint),
            "personalization_checks": _personalization_checks(personalization_plan, visual_assets),
            "personalization_trace_coverage": _personalization_trace_coverage(
                personalization_trace
            ),
            "claim_evidence_coverage": _claim_evidence_coverage(claim_evidence_ledger),
            "notebook_validation": notebook_validation,
            "checks": {
                "scope_consistent": not any("不一致" in item for item in blockers),
                "formal_evidence_complete": not missing_published,
                "formal_publish_allowed": formal_ready,
                "candidate_draft_requires_opt_in": (
                    release_status != "candidate_draft" or allow_candidate_drafts
                ),
            },
            "next_actions": _next_actions(release_status, missing_published, gate),
        }
        return CandidateResourcePackage(
            release_status=release_status,
            target_concept_id=concept_id,
            target_depth=depth,
            decision_card=decision_card,
            evidence_matrix=evidence_matrix,
            quality_report=quality_report,
            resources=resources,
            notebook=notebook if release_status != "blocked" else None,
            assessment_blueprint=assessment_blueprint,
            personalization_plan=personalization_plan,
            visual_assets=visual_assets if release_status != "blocked" else {},
            claim_evidence_ledger=claim_evidence_ledger if resources else [],
            personalization_trace=personalization_trace if resources else [],
        )

    def export(self, package: CandidateResourcePackage, output_dir: str | Path) -> tuple[Path, ...]:
        """Write an inspectable package without changing its release state."""
        destination = Path(output_dir).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for filename, payload in (
            ("00_personalization_plan.json", package.personalization_plan),
            ("01_resource_decision_card.json", package.decision_card),
            ("02_evidence_matrix.json", package.evidence_matrix),
            ("03_quality_report.json", package.quality_report),
            ("04_assessment_blueprint.json", package.assessment_blueprint),
            ("08_claim_evidence_ledger.json", package.claim_evidence_ledger),
            ("09_personalization_trace.json", package.personalization_trace),
            ("resource_package.json", package.to_dict()),
        ):
            path = destination / filename
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            written.append(path)
        for resource in package.resources:
            path = destination / f"{resource.resource_type}.md"
            path.write_text(resource.content, encoding="utf-8")
            written.append(path)
        if package.notebook is not None:
            path = destination / "pytorch_practical_notebook.ipynb"
            path.write_text(
                json.dumps(package.notebook, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            written.append(path)
        for filename, svg in package.visual_assets.items():
            path = destination / filename
            path.write_text(svg, encoding="utf-8")
            written.append(path)
        return tuple(written)

    def _find_inputs(self, root: Path) -> tuple[Path, Path, Path, Path | None]:
        if not root.is_dir():
            raise ValueError(f"输入目录不存在: {root}")
        files = tuple(path for path in root.rglob("*.json") if path.is_file())
        return (
            _find_latest(files, "学情画像"),
            _find_latest(files, "resource_agent_handoff"),
            _find_latest(files, "domain_retrieval_agent_output"),
            _find_optional(files, "evidence_publication_manifest"),
        )

    def _validate_scope(
        self,
        profile: dict[str, Any],
        handoff: dict[str, Any],
        retrieval: dict[str, Any],
        depth: str,
        blockers: list[str],
        warnings: list[str],
    ) -> None:
        profile_id = _text(profile.get("profile_id"))
        handoff_profile_id = _text(handoff.get("profile_id"))
        request = _mapping(retrieval.get("request"))
        if profile_id and handoff_profile_id and profile_id != handoff_profile_id:
            blockers.append("学情画像与课程规划交接的 profile_id 不一致。")
        handoff_concept_id = _text(handoff.get("concept_id"))
        if request and _text(request.get("concept_id")) not in {None, handoff_concept_id}:
            blockers.append("领域检索结果与课程规划交接的 concept_id 不一致。")
        if request and _text(request.get("depth")) not in {None, depth}:
            blockers.append("领域检索结果与课程规划交接的 depth 不一致。")
        hints = _mapping(profile.get("resource_generation_hints"))
        requested_depth = _text(hints.get("target_depth"))
        if requested_depth and requested_depth != depth:
            warnings.append(f"画像建议深度为“{requested_depth}”，本次以课程规划交接的“{depth}”为准。")


def _find_latest(files: tuple[Path, ...], marker: str) -> Path:
    matches = [path for path in files if marker.lower() in path.name.lower()]
    if not matches:
        raise ValueError(f"缺少必要输入文件：名称需包含 {marker!r}")
    return max(matches, key=lambda path: (path.stat().st_mtime_ns, path.name))


def _find_optional(files: tuple[Path, ...], marker: str) -> Path | None:
    matches = [path for path in files if marker.lower() in path.name.lower()]
    return max(matches, key=lambda path: (path.stat().st_mtime_ns, path.name)) if matches else None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON 无法解析: {path.name}: {error.msg}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根节点必须是对象: {path.name}")
    return value


def _required_text(payload: dict[str, Any], key: str, path: Path) -> str:
    value = _text(payload.get(key))
    if value is None:
        raise ValueError(f"{path.name} 缺少非空字段 {key!r}")
    return value


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _candidate_evidence(retrieval: dict[str, Any], handoff: dict[str, Any]) -> list[dict[str, Any]]:
    values = retrieval.get("candidate_evidence")
    if not isinstance(values, list):
        values = _mapping(handoff.get("retrieval_context")).get("candidate_evidence", [])
    return [item for item in values if isinstance(item, dict)]


def _apply_publication_manifest(
    candidates: list[dict[str, Any]],
    manifest: dict[str, Any] | None,
    concept_id: str,
    depth: str,
) -> list[dict[str, Any]]:
    if manifest is None:
        return candidates
    if _text(manifest.get("concept_id")) != concept_id or _text(manifest.get("depth")) != depth:
        raise ValueError("证据发布清单与课程规划交接的概念或深度不一致。")
    records = manifest.get("records")
    if not isinstance(records, list):
        raise ValueError("证据发布清单缺少 records 列表。")
    published_by_id = {
        _text(record.get("evidence_id")): record
        for record in records
        if isinstance(record, dict)
        and _text(record.get("evidence_id"))
        and record.get("review_status") == "published"
        and record.get("evidence_status") == "published"
        and record.get("license_status") == "allowed"
    }
    return [
        {
            **candidate,
            **published_by_id.get(_evidence_id(candidate), {}),
        }
        for candidate in candidates
    ]


def _is_published(item: dict[str, Any]) -> bool:
    return (
        item.get("review_status") == "published"
        and item.get("evidence_status") == "published"
        and item.get("license_status") in {"allowed", "approved", "registered"}
    )


def _evidence_id(item: dict[str, Any]) -> str:
    for key in ("evidence_id", "chunk_id", "id"):
        value = _text(item.get(key))
        if value:
            return value
    return "unidentified_evidence"


def _target_title(profile: dict[str, Any], handoff: dict[str, Any]) -> str:
    scope = _mapping(profile.get("learning_scope"))
    return (
        _text(scope.get("chapter_name"))
        or _text(scope.get("primary_kp_name"))
        or _text(handoff.get("concept_id"))
        or "当前知识点"
    )


def _top_errors(profile: dict[str, Any]) -> list[str]:
    items = _mapping(profile.get("error_patterns")).get("items", [])
    if isinstance(items, list):
        results = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = _text(item.get("name")) or _text(item.get("code"))
            if name:
                results.append(name)
        if results:
            return results[:3]
    attention = _text(
        _mapping(_mapping(profile.get("resource_generation_hints")).get("lecture_notes")).get(
            "error_pattern_attention"
        )
    )
    return [attention] if attention else []


def _presentation_order(profile: dict[str, Any], handoff: dict[str, Any]) -> list[str]:
    profile_order = _string_list(
        _mapping(_mapping(profile.get("learning_preferences")).get("format")).get("content_order")
    )
    handoff_order = _string_list(
        _mapping(_mapping(handoff.get("learner_adaptation")).get("presentation_preferences")).get(
            "content_order"
        )
    )
    return profile_order or handoff_order or ["概念直觉", "数学公式", "代码实操", "辨析测验"]


def _support_notes(handoff: dict[str, Any]) -> list[str]:
    hints = _mapping(handoff.get("learner_adaptation")).get("error_pattern_hints", [])
    if not isinstance(hints, list):
        return []
    return [
        text
        for hint in hints
        if isinstance(hint, dict)
        for text in [_text(hint.get("instruction"))]
        if text
    ]


def _resource_constraints(handoff: dict[str, Any]) -> list[str]:
    resources = _mapping(handoff.get("resource_requirements")).get("resources", [])
    if not isinstance(resources, list):
        return []
    constraints = []
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        for item in _string_list(resource.get("content_requirements")):
            if item not in constraints:
                constraints.append(item)
    return constraints


def _evidence_sources(candidates: list[dict[str, Any]]) -> list[str]:
    sources = []
    for candidate in candidates:
        title = _text(candidate.get("source_title")) or _text(candidate.get("title"))
        evidence_id = _evidence_id(candidate)
        kind = _text(candidate.get("content_kind")) or "unknown"
        status = _text(candidate.get("evidence_status")) or "candidate_only"
        if title:
            sources.append(f"{kind}：{title}（{evidence_id}，{status}）")
    return sources


def _build_personalization_plan(
    profile: dict[str, Any],
    handoff: dict[str, Any],
) -> dict[str, Any]:
    scope = _mapping(profile.get("learning_scope"))
    target_kp_id = _text(scope.get("primary_kp_id"))
    target_point = _mapping(_mapping(profile.get("knowledge_mastery")).get("points")).get(
        target_kp_id or ""
    )
    target_point = _mapping(target_point)
    ability = _mapping(profile.get("ability_level"))
    dimensions = _mapping(ability.get("sub_dimensions"))
    preferences = _mapping(profile.get("learning_preferences"))
    pace = _mapping(preferences.get("pace"))
    motivation = _mapping(preferences.get("motivation"))
    allocation = _mapping(_mapping(handoff.get("resource_requirements")).get("allocation"))
    total_minutes = allocation.get("estimated_minutes")
    estimated_minutes = total_minutes if isinstance(total_minutes, int) else 90
    attention = pace.get("session_attention_minutes")
    attention_minutes = attention if isinstance(attention, int) else 50
    first_session = min(estimated_minutes, attention_minutes)
    second_session = max(estimated_minutes - first_session, 0)
    weekly_hours = pace.get("weekly_hours")
    weekly_minutes = weekly_hours * 60 if isinstance(weekly_hours, (int, float)) else None
    remaining_minutes = max(int(weekly_minutes) - estimated_minutes, 0) if weekly_minutes else None
    hints = _mapping(profile.get("resource_generation_hints"))
    advanced_hints = _string_list(_mapping(hints.get("lecture_notes")).get("must_include"))
    coding_score = _number(_mapping(dimensions.get("coding_ability")).get("score"))
    math_score = _number(_mapping(dimensions.get("mathematical_foundation")).get("score"))
    mastery_score = _number(target_point.get("mastery"))

    return {
        "learner_snapshot": {
            "target_mastery": mastery_score,
            "target_mastery_status": target_point.get("status"),
            "target_mastery_confidence": target_point.get("confidence"),
            "global_theta": _mapping(profile.get("knowledge_mastery")).get("global_theta"),
            "coding_ability": _mapping(dimensions.get("coding_ability")).get("score"),
            "mathematical_foundation": _mapping(dimensions.get("mathematical_foundation")).get(
                "score"
            ),
            "theoretical_understanding": _mapping(
                dimensions.get("theoretical_understanding")
            ).get("score"),
        },
        "current_resource_boundary": {
            "delivery_depth": handoff.get("depth"),
            "generation_gate": _mapping(handoff.get("resource_generation_gate")).get("status"),
            "reason": "当前仅生成卷积运算补救包；完整 CNN 章节内容等待先修与证据门禁解除。",
        },
        "resource_shape": {
            "worked_example_count": allocation.get("worked_example_count", 4),
            "guided_exercise_count": allocation.get("guided_exercise_count", 8),
            "assessment_item_count": allocation.get("assessment_item_count", 8),
            "code_cell_max_lines": 30,
            "visual_assets": [
                "01_nchw_tensor_layout.svg",
                "02_convolution_window.svg",
                "03_shape_reasoning_flow.svg",
            ],
        },
        "scaffolding_policy": {
            "mastery_strategy": _mastery_strategy(mastery_score),
            "coding_strategy": _coding_strategy(coding_score),
            "math_strategy": _math_strategy(math_score),
        },
        "session_plan": [
            {
                "session": 1,
                "minutes": first_session,
                "goal": "概念直觉与两次尺寸推导",
                "materials": ["讲义第 2–6 节", "卷积滑窗图", "Q1–Q5"],
                "success_check": "能解释 NCHW、卷积/互相关区别，并手算 32→16。",
            },
            {
                "session": 2,
                "minutes": second_session,
                "goal": "PyTorch shape 验证与代码纠错",
                "materials": ["Notebook 全部代码单元", "Q6–Q8"],
                "success_check": "能运行 Conv2d/池化断言并定位 NHWC 错误。",
            },
        ],
        "weekly_capacity": {
            "weekly_hours": weekly_hours,
            "current_pack_minutes": estimated_minutes,
            "remaining_minutes_after_current_pack": remaining_minutes,
            "recommended_use_of_remaining_time": (
                "先完成图像张量前置复习与错题复盘；不要在课程规划未解锁前跳到完整 CNN 训练。"
            ),
        },
        "presentation_strategy": {
            "content_order": _presentation_order(profile, handoff),
            "visual_learner": _mapping(preferences.get("style")).get("visual_learner") is True,
            "step_by_step": _mapping(preferences.get("style")).get("prefers_step_by_step") is True,
            "comparison_tables": _mapping(preferences.get("style")).get(
                "prefers_comparison_tables"
            )
            is True,
            "formula_first_for_calculation_errors": True,
        },
        "project_connection": {
            "target_project": motivation.get("target_project"),
            "current_connection": "用 CIFAR-10 的 32×32×3 输入理解卷积 shape；后续连接图像分类与目标检测。",
        },
        "deferred_advanced_content": advanced_hints,
        "prior_chapter_signal": _prior_chapter_signal(profile),
    }


def _prior_chapter_signal(profile: dict[str, Any]) -> dict[str, Any]:
    chapters = profile.get("prior_chapters", [])
    if not isinstance(chapters, list) or not chapters:
        return {}
    latest = next((item for item in reversed(chapters) if isinstance(item, dict)), {})
    return {
        "chapter_name": latest.get("chapter_name"),
        "accuracy": latest.get("accuracy"),
        "observed_errors": latest.get("error_patterns_observed", []),
        "adaptation": "保留神经网络概念对比与分步论证，避免从前一章直接跳到复杂 CNN。",
    }


def _build_visual_assets(profile: dict[str, Any]) -> dict[str, str]:
    style = _mapping(_mapping(profile.get("learning_preferences")).get("style"))
    if style.get("visual_learner") is not True:
        return {}
    return {
        "01_nchw_tensor_layout.svg": _svg_nchw_layout(),
        "02_convolution_window.svg": _svg_convolution_window(),
        "03_shape_reasoning_flow.svg": _svg_shape_flow(),
    }


def _svg_nchw_layout() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" width="900" height="280" viewBox="0 0 900 280">
<rect width="900" height="280" fill="#f8fafc"/><text x="40" y="48" font-size="28" fill="#0f172a">PyTorch 图像张量：NCHW</text>
<g font-family="Microsoft YaHei, sans-serif" text-anchor="middle"><rect x="45" y="95" width="180" height="110" rx="14" fill="#dbeafe"/><text x="135" y="140" font-size="24">N</text><text x="135" y="174" font-size="17">batch：2 张图片</text>
<rect x="255" y="95" width="180" height="110" rx="14" fill="#dcfce7"/><text x="345" y="140" font-size="24">C</text><text x="345" y="174" font-size="17">channel：RGB = 3</text>
<rect x="465" y="95" width="180" height="110" rx="14" fill="#fef3c7"/><text x="555" y="140" font-size="24">H</text><text x="555" y="174" font-size="17">height：32</text>
<rect x="675" y="95" width="180" height="110" rx="14" fill="#fce7f3"/><text x="765" y="140" font-size="24">W</text><text x="765" y="174" font-size="17">width：32</text></g>
<text x="450" y="250" text-anchor="middle" font-size="20" fill="#334155">输入 x.shape = (2, 3, 32, 32)，Conv2d 的 in_channels 必须等于第二维 3</text></svg>"""


def _svg_convolution_window() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" width="900" height="330" viewBox="0 0 900 330">
<rect width="900" height="330" fill="#f8fafc"/><text x="35" y="43" font-size="27" fill="#0f172a">卷积窗口：局部连接 + 参数共享</text>
<g stroke="#64748b" fill="#fff"><rect x="60" y="80" width="220" height="220"/><path d="M115 80v220M170 80v220M225 80v220M60 135h220M60 190h220M60 245h220"/></g>
<rect x="115" y="135" width="110" height="110" fill="#bfdbfe" fill-opacity=".75" stroke="#2563eb" stroke-width="4"/>
<path d="M325 185h155" stroke="#2563eb" stroke-width="5" marker-end="url(#a)"/><defs><marker id="a" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#2563eb"/></marker></defs>
<g stroke="#64748b" fill="#fff"><rect x="525" y="105" width="135" height="135"/><path d="M570 105v135M615 105v135M525 150h135M525 195h135"/></g>
<text x="170" y="320" text-anchor="middle" font-size="18" fill="#334155">输入特征图：窗口只看局部 3×3 区域</text><text x="592" y="270" text-anchor="middle" font-size="18" fill="#334155">同一卷积核滑动后形成输出特征图</text>
<text x="740" y="145" font-size="19" fill="#0f172a">先预测：</text><text x="740" y="178" font-size="18" fill="#334155">kernel=3</text><text x="740" y="207" font-size="18" fill="#334155">padding=1</text><text x="740" y="236" font-size="18" fill="#334155">stride=2</text></svg>"""


def _svg_shape_flow() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" width="900" height="250" viewBox="0 0 900 250">
<rect width="900" height="250" fill="#f8fafc"/><text x="35" y="42" font-size="27" fill="#0f172a">输出 shape 推理流程</text>
<g font-family="Microsoft YaHei, sans-serif" text-anchor="middle"><rect x="35" y="95" width="170" height="80" rx="12" fill="#dbeafe"/><text x="120" y="128" font-size="19">输入</text><text x="120" y="155" font-size="16">(2, 3, 32, 32)</text>
<rect x="270" y="95" width="210" height="80" rx="12" fill="#fef3c7"/><text x="375" y="128" font-size="17">代入公式</text><text x="375" y="155" font-size="14">floor((32+2P-K)/S)+1</text>
<rect x="545" y="95" width="150" height="80" rx="12" fill="#dcfce7"/><text x="620" y="128" font-size="17">空间尺寸</text><text x="620" y="155" font-size="16">32 → 16</text>
<rect x="760" y="95" width="110" height="80" rx="12" fill="#fce7f3"/><text x="815" y="128" font-size="17">输出</text><text x="815" y="155" font-size="14">(2,8,16,16)</text></g>
<path d="M205 135h65M480 135h65M695 135h65" stroke="#2563eb" stroke-width="5" marker-end="url(#a)"/><defs><marker id="a" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#2563eb"/></marker></defs>
<text x="450" y="220" text-anchor="middle" font-size="18" fill="#334155">每次先手算，再运行 assert；不一致时依次检查 NCHW、padding、stride。</text></svg>"""


def _personalization_checks(
    plan: dict[str, Any],
    visual_assets: dict[str, str],
) -> dict[str, bool]:
    snapshot = _mapping(plan.get("learner_snapshot"))
    strategy = _mapping(plan.get("presentation_strategy"))
    capacity = _mapping(plan.get("weekly_capacity"))
    return {
        "mastery_used": snapshot.get("target_mastery") is not None,
        "ability_dimensions_used": snapshot.get("coding_ability") is not None,
        "pace_used": capacity.get("weekly_hours") is not None,
        "visual_preference_honored": bool(visual_assets)
        if strategy.get("visual_learner")
        else True,
        "project_goal_used": bool(_mapping(plan.get("project_connection")).get("target_project")),
        "prior_chapter_used": bool(_mapping(plan.get("prior_chapter_signal"))),
    }


def _personalization_trace(
    profile: dict[str, Any],
    handoff: dict[str, Any],
    plan: dict[str, Any],
    visual_assets: dict[str, str],
) -> list[dict[str, Any]]:
    snapshot = _mapping(plan.get("learner_snapshot"))
    preferences = _mapping(profile.get("learning_preferences"))
    pace = _mapping(preferences.get("pace"))
    motivation = _mapping(preferences.get("motivation"))
    prior = _mapping(plan.get("prior_chapter_signal"))
    scaffold = _mapping(plan.get("scaffolding_policy"))
    return [
        {
            "input_field": "knowledge_mastery.target_cnn",
            "observed_value": snapshot.get("target_mastery"),
            "decision": scaffold.get("mastery_strategy"),
            "output_locations": ["讲义第 0、2 节", "测验 Q1–Q8", "session_plan"],
        },
        {
            "input_field": "ability_level.coding_ability",
            "observed_value": snapshot.get("coding_ability"),
            "decision": scaffold.get("coding_strategy"),
            "output_locations": ["实操指南第 1–7 节", "Notebook 代码单元", "测验 Q7–Q8"],
        },
        {
            "input_field": "ability_level.mathematical_foundation",
            "observed_value": snapshot.get("mathematical_foundation"),
            "decision": scaffold.get("math_strategy"),
            "output_locations": ["讲义第 5、6 节", "Notebook 公式单元", "测验 Q4–Q6"],
        },
        {
            "input_field": "learning_preferences.pace",
            "observed_value": {
                "weekly_hours": pace.get("weekly_hours"),
                "session_attention_minutes": pace.get("session_attention_minutes"),
            },
            "decision": "按注意力时长拆为两次学习，并保留每周剩余时间用于先修与错题复盘。",
            "output_locations": ["个性化学习计划.session_plan", "讲义第 0 节"],
        },
        {
            "input_field": "learning_preferences.style",
            "observed_value": _mapping(preferences.get("style")),
            "decision": (
                "生成 NCHW、卷积滑窗和 shape 推理图，并以表格和逐步验证组织内容。"
                if visual_assets
                else "不额外生成视觉图示，保留文字与公式说明。"
            ),
            "output_locations": list(visual_assets) + ["讲义第 3、5、7 节", "实操指南第 4.5 节"],
        },
        {
            "input_field": "prior_chapters",
            "observed_value": prior,
            "decision": "保留神经网络概念对比与分步论证，不从前章直接跳到完整 CNN。",
            "output_locations": ["讲义第 0、4、9 节", "测验 Q1–Q3"],
        },
        {
            "input_field": "learning_preferences.motivation.target_project",
            "observed_value": motivation.get("target_project"),
            "decision": "用 CIFAR-10 图像张量建立当前项目连接，并将后续图像分类/检测设为解锁后任务。",
            "output_locations": ["讲义第 10 节", "实操指南第 8 节"],
        },
        {
            "input_field": "planning_handoff",
            "observed_value": {
                "depth": handoff.get("depth"),
                "gate": _mapping(handoff.get("resource_generation_gate")).get("status"),
            },
            "decision": "规划交接优先，禁止画像中的进阶需求越过先修和证据门禁。",
            "output_locations": ["决策卡", "讲义第 0、10 节", "质量报告"],
        },
    ]


def _personalization_trace_coverage(trace: list[dict[str, Any]]) -> dict[str, Any]:
    unlinked = [
        item["input_field"]
        for item in trace
        if not item.get("decision") or not item.get("output_locations")
    ]
    return {
        "trace_count": len(trace),
        "unlinked_input_fields": unlinked,
        "all_input_fields_have_output_effect": not unlinked,
    }


def _mastery_strategy(score: float | None) -> str:
    if score is None:
        return "掌握度证据不足：使用保守入门材料，并在测验后重新诊断。"
    if score < 0.30:
        return "掌握度较低：采用补救型入门路径，先给完整示例，再给带提示练习。"
    if score < 0.65:
        return "掌握度中等：减少重复定义，增加参数修改和解释性练习。"
    return "掌握度较高：保留最少回顾，增加迁移性代码与综合分析题。"


def _coding_strategy(score: float | None) -> str:
    if score is None or score < 0.45:
        return "代码基础较弱：每个单元先阅读再填空，提供完整 shape 注释与逐行提示。"
    if score < 0.75:
        return "代码能力可用但框架经验有限：提供可运行最小示例，要求一次只修改一个参数并用断言验证。"
    return "代码能力较强：提供紧凑骨架，要求自主实现公式核对与调试记录。"


def _math_strategy(score: float | None) -> str:
    if score is None or score < 0.50:
        return "数学支撑不足：所有尺寸题拆成代入、化简、取整三个步骤，并给出额外练习。"
    if score < 0.75:
        return "数学基础可支持推导：保留两道完整尺寸例题与参数量核对，要求写出中间步骤。"
    return "数学基础较强：压缩基础例题，加入通道、感受野或计算量比较。"


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _build_resources(
    profile: dict[str, Any],
    handoff: dict[str, Any],
    candidates: list[dict[str, Any]],
    release_status: ReleaseStatus,
    personalization_plan: dict[str, Any],
) -> tuple[CandidateResource, ...]:
    requirements = _mapping(handoff.get("learning_requirements"))
    outcomes = _string_list(requirements.get("learning_outcomes"))
    outcome_lines = "\n".join(f"- {item}" for item in outcomes) or "- 以课程规划交接为准。"
    error_lines = "\n".join(f"- {item}" for item in _top_errors(profile))
    if not error_lines:
        error_lines = "- 先做概念检查，再进入代码。"
    evidence_by_kind = {
        kind: tuple(_evidence_id(item) for item in candidates if item.get("content_kind") == kind)
        for kind in _REQUIRED_EVIDENCE_KINDS
    }
    heading = _target_title(profile, handoff)
    depth = _text(handoff.get("depth")) or "intro"
    publication_note = (
        "> 资源状态：published。资源已通过当前课程门禁与证据发布校验。\n"
        if release_status == "published"
        else (
            f"> 资源状态：{release_status}。这是可学习、可审核的候选草稿；"
            "正式教学发布前仍需完成证据审核与课程门禁。\n"
        )
    )
    preferences = _presentation_order(profile, handoff)
    support_lines = "\n".join(f"- {item}" for item in _support_notes(handoff))
    if not support_lines:
        support_lines = "- 先建立图像张量和卷积窗口的直觉，再进行公式和代码映射。"
    constraint_lines = "\n".join(f"- {item}" for item in _resource_constraints(handoff))
    if not constraint_lines:
        constraint_lines = "- 本轮只处理基础 Conv2d，不进入完整架构训练。"
    sources = _evidence_sources(candidates)
    source_lines = "\n".join(f"- {item}" for item in sources) or "- 当前没有可定位候选证据。"
    session_lines = "\n".join(
        f"- 第 {item.get('session')} 次（{item.get('minutes')} 分钟）："
        f"{item.get('goal')}；检查：{item.get('success_check')}"
        for item in personalization_plan.get("session_plan", [])
        if isinstance(item, dict)
    )
    weekly_capacity = _mapping(personalization_plan.get("weekly_capacity"))
    project_connection = _mapping(personalization_plan.get("project_connection"))
    scaffolding = _mapping(personalization_plan.get("scaffolding_policy"))

    lecture = CandidateResource(
        resource_type="lecture_notes",
        title=f"{heading}个性化讲义",
        evidence_ids=evidence_by_kind["definition"],
        release_status=release_status,
        content=(
            f"# {heading}：卷积运算学习讲义\n\n"
            "## 你将解决的真实问题\n\n"
            "给一张 32×32 的 RGB 图片，为什么一个小小的 3×3 窗口能提取有用特征？"
            "为什么 stride 从 1 改成 2，输出会从 32×32 变成 16×16？"
            "本讲义不要求你背定义，而要求你能先预测、再计算、最后用代码验证。\n\n"
            "## 本次学习边界\n\n"
            f"当前学习深度为 **{depth}**：先把图像张量、卷积窗口、padding、stride 与"
            "Conv2d 的联系建立起来。完整 CNN 训练、BatchNorm 和更复杂架构会在后续"
            "先修解锁后单独进入，不在这一节混讲。\n\n"
            f"推荐学习顺序：{' → '.join(preferences)}。\n\n"
            "### 本周两次学习安排\n\n"
            f"{session_lines}\n\n"
            f"本周可投入 {weekly_capacity.get('weekly_hours', '未提供')} 小时；当前资源包只占"
            f" {weekly_capacity.get('current_pack_minutes', 90)} 分钟。剩余时间建议："
            f"{weekly_capacity.get('recommended_use_of_remaining_time', '完成错题复盘。')}\n\n"
            "## 1. 学习目标与完成标准\n\n"
            f"{outcome_lines}\n\n"
            "完成标准不是“看懂代码”：你需要能手算一次输出尺寸，解释一个卷积核如何同时"
            "处理 RGB 三个通道，并在 PyTorch 中确认每一步的 NCHW shape。\n\n"
            "## 2. 先补一块必要前置：图像张量\n\n"
            "![NCHW 图像张量](01_nchw_tensor_layout.svg)\n\n"
            "PyTorch 图像默认使用 NCHW：N 是批次，C 是通道，H、W 是高度与宽度。"
            "一批两张 CIFAR-10 彩色图片应写成 (2, 3, 32, 32)，而不是 NHWC。"
            "后续 Conv2d 的 in_channels 必须等于 C；这是代码形状错误最常见的根源。\n\n"
            "## 3. 为什么图像适合卷积：从 MLP 的参数爆炸开始\n\n"
            "若将 32×32×3 图像直接展平并连接到 1000 个隐藏单元，参数量约为"
            " 32×32×3×1000 = 3,072,000。一个 3×3、3 输入通道、8 输出通道的卷积层"
            "只有 3×3×3×8 + 8 = 224 个参数。卷积依靠两件事减少参数：\n\n"
            "- 局部连接：一个输出位置只看输入附近的小窗口；\n"
            "- 参数共享：同一个卷积核在整张图上滑动，边缘和纹理无论出现在哪里都可复用。\n\n"
            "## 4. 卷积、互相关与特征图\n\n"
            "![卷积滑窗](02_convolution_window.svg)\n\n"
            "把 3×3 卷积核看成一个小检测器。它在输入上滑动，每个位置做逐元素相乘再求和，"
            "得到一张输出特征图。严格的数学卷积会翻转卷积核；深度学习框架的 Conv2d 通常计算"
            "互相关，但工程里仍习惯称为卷积层。\n\n"
            "| 对比项 | 数学卷积 | CNN 常用互相关 |\n|---|---|---|\n"
            "| 卷积核 | 先翻转 | 通常不翻转 |\n"
            "| 共同点 | 局部窗口、乘加汇聚 | 局部窗口、乘加汇聚 |\n"
            "| 学习时要点 | 术语与手算要区分 | 代码接口仍叫 Conv2d |\n\n"
            "## 5. 输出尺寸：必须逐步计算\n\n"
            "![shape 推理流程](03_shape_reasoning_flow.svg)\n\n"
            f"本学生的数学支架策略：{scaffolding.get('math_strategy')}\n\n"
            "单个空间维度的公式为：\n\n"
            "~~~text\n输出 = floor((输入 + 2×padding - kernel_size) / stride) + 1\n~~~\n\n"
            "例 1：输入 32、kernel=3、padding=1、stride=1："
            "floor((32+2-3)/1)+1=32，空间尺寸保持不变。\n\n"
            "例 2：输入 32、kernel=3、padding=1、stride=2："
            "floor((32+2-3)/2)+1=16，输出为 16×16。"
            "这里最容易错的是漏掉两侧填充的 2×padding，或把 stride 当成减法。\n\n"
            "## 6. 通道、卷积核与参数量\n\n"
            "彩色图片有 3 个输入通道。设置 Conv2d(3, 8, 3) 时，8 表示要学习 8 组卷积核，"
            "每一组都覆盖全部 3 个输入通道。因此忽略 bias 的参数量为 3×8×3×3=216；"
            "默认启用 8 个 bias，总参数为 224。out_channels 改变的是输出特征图数量，"
            "不是特征图的高和宽。\n\n"
            "## 7. stride、padding、池化：不要混为一谈\n\n"
            "| 操作 | 是否有可学习参数 | 主要作用 | 常见误解 |\n|---|---:|---|---|\n"
            "| Conv2d | 是 | 提取局部特征 | 以为只改变通道 |\n"
            "| padding | 否 | 控制边界和尺寸 | 忘记公式中的 2P |\n"
            "| stride | 否 | 控制窗口移动距离 | 忽略对尺寸的下采样 |\n"
            "| MaxPool2d | 否 | 汇聚局部响应 | 误以为等同卷积 |\n\n"
            "## 8. 公式如何映射到 PyTorch\n\n"
            "~~~python\nnn.Conv2d(\n    in_channels=3, out_channels=8,\n    kernel_size=3, stride=2, padding=1\n)\n~~~\n\n"
            "调用前先打印 x.shape；调用后先打印 y.shape；再用公式核对 32 是否变成 16。"
            "这一顺序对应“概念 → 公式 → 代码 → 验证”，避免只运行、不理解。\n\n"
            "## 9. 针对本学习者的防错设计\n\n"
            f"{error_lines}\n\n"
            f"{support_lines}\n\n"
            "学习建议：先看讲义第 2–6 节，完成 Notebook 的 shape 断言，再做测验中的"
            "计算题；如果连续两题算错，不进入下一节，而是回到第 5 节逐项代入。\n\n"
            "## 10. 本轮边界与下一阶段\n\n"
            f"{constraint_lines}\n\n"
            "当图像张量先修完成、正式证据发布且课程规划重新允许时，下一轮可增加"
            "特征图可视化、BatchNorm、完整 CNN 训练与 CIFAR-10 项目。\n\n"
            "当前项目连接："
            f"{project_connection.get('current_connection', '后续连接到实际图像任务。')}\n\n"
            "## 候选证据来源\n\n"
            f"{source_lines}\n\n{publication_note}"
        ),
    )
    practical = CandidateResource(
        resource_type="pytorch_practical_guide",
        title=f"{heading} PyTorch 实操指南",
        evidence_ids=evidence_by_kind["code"],
        release_status=release_status,
        content=(
            f"# {heading}：PyTorch Conv2d 实操工作簿\n\n"
            "这是一份边预测、边运行、边记录的实验工作簿。每个实验先在纸上写预测结果，"
            "再运行代码；如果预测与结果不同，按调试表定位原因。\n\n"
            "## 0. 本实操的目标与边界\n\n"
            "本实操不是直接训练大型 CNN，而是把“张量 → Conv2d 参数 → 输出 shape → 参数量”"
            "这条链跑通。每段代码不超过一个概念：先预测，再运行，再解释差异。\n\n"
            f"本学生的代码支架策略：{scaffolding.get('coding_strategy')}\n\n"
            "## 1. 环境与输入检查\n\n"
            "使用 Python、PyTorch 与 Jupyter。先执行：\n\n"
            "~~~python\nimport torch\nfrom torch import nn\nx = torch.randn(2, 3, 32, 32)\nprint(tuple(x.shape))  # 预期 (2, 3, 32, 32)\n~~~\n\n"
            "如果第二维不是 3，不要先改 Conv2d；先检查数据是否被错误地组织成 NHWC。\n\n"
            "## 2. 工作示例 A：保持空间尺寸\n\n"
            "~~~python\nlayer = nn.Conv2d(3, 8, kernel_size=3, stride=1, padding=1)\ny = layer(x)\nassert y.shape == (2, 8, 32, 32)\nprint(tuple(y.shape))\n~~~\n\n"
            "解释：padding=1 抵消 3×3 卷积核带来的边界缩小；out_channels=8 只改变通道数。\n\n"
            "## 3. 工作示例 B：使用 stride 下采样\n\n"
            "~~~python\nlayer = nn.Conv2d(3, 8, kernel_size=3, stride=2, padding=1)\ny = layer(x)\nassert y.shape == (2, 8, 16, 16)\n~~~\n\n"
            "请在运行前写下 floor((32+2×1-3)/2)+1=16，再用断言验证。\n\n"
            "## 4. 工作示例 C：核对参数量\n\n"
            "~~~python\nweight_params = layer.weight.numel()\nbias_params = 0 if layer.bias is None else layer.bias.numel()\nprint(weight_params, bias_params, weight_params + bias_params)\nassert weight_params == 3 * 8 * 3 * 3\n~~~\n\n"
            "这一步专门防止把 8 个输出通道误当成 8×8 的空间尺寸。\n\n"
            "## 4.5 先看图，再改代码\n\n"
            "请先打开资源包中的 01_nchw_tensor_layout.svg、02_convolution_window.svg 和"
            "03_shape_reasoning_flow.svg：前两张用于建立视觉直觉，最后一张用于每次运行前"
            "手动预测 shape。图示偏好不会改变课程深度，只改变解释与练习方式。\n\n"
            "## 5. 工作示例 D：卷积后接池化\n\n"
            "~~~python\npool = nn.MaxPool2d(kernel_size=2, stride=2)\nz = pool(y)\nassert z.shape == (2, 8, 8, 8)\nprint('conv:', tuple(y.shape), 'pool:', tuple(z.shape))\n~~~\n\n"
            "池化没有可训练卷积核；它是在每个通道内做局部汇聚。不要把池化的尺寸变化归因于 out_channels。\n\n"
            "## 6. 形状调试清单\n\n"
            "| 现象 | 首先检查 | 修复动作 |\n|---|---|---|\n"
            "| expected input to have 3 channels | x.shape 的第二维 | 调整数据到 NCHW 或修改 in_channels |\n"
            "| 输出宽高和手算不一致 | kernel、padding、stride | 逐项代入公式，不凭直觉 |\n"
            "| 参数量对不上 | weight 与 bias | 分开计算 3×8×3×3 和 8 |\n"
            "| 代码能跑但解释不出 | 没有记录中间 shape | 每层都打印输入与输出 |\n\n"
            "## 7. 四个引导练习\n\n"
            "1. 将 padding 从 1 改为 0，先预测输出为 15×15，再运行验证。\n"
            "2. 将 stride 从 2 改为 1，解释为什么输出回到 32×32。\n"
            "3. 将 out_channels 从 8 改为 16，列出变化与不变的维度。\n"
            "4. 创建形状为 (2, 32, 32, 3) 的张量，解释为什么不能直接送入 Conv2d。\n\n"
            "## 8. 连接到后续项目\n\n"
            "当课程规划解除前置阻塞后，这些 shape 与参数量检查会直接迁移到 CIFAR-10："
            "真实数据加载、训练/验证划分、损失曲线、特征图可视化与模型保存。现在先把每一层"
            "的输入输出说清楚，后续训练才不会被维度错误掩盖。\n\n"
            "## 候选证据来源\n\n"
            f"{source_lines}\n\n{publication_note}"
        ),
    )
    assessment = CandidateResource(
        resource_type="layered_assessment",
        title=f"{heading}分层测验（学生卷）",
        evidence_ids=evidence_by_kind["exercise"],
        release_status=release_status,
        content=(
            f"# {heading}：分层测验（学生卷）\n\n"
            "建议用时：45 分钟。请先独立完成，不要直接打开答案卷。"
            "计算题必须写出代入过程；代码题必须写出判断依据。\n\n"
            "## A. 概念辨析\n\n"
            "### Q1｜卷积与互相关\n\n"
            "PyTorch 的 Conv2d 在实现上通常更接近数学卷积还是互相关？为什么工程里仍称其为卷积层？\n\n"
            "### Q2｜局部连接与参数共享\n\n"
            "为什么卷积比全连接层更适合 32×32 图像？请各写出一个原因。\n\n"
            "### Q3｜卷积与池化\n\n"
            "下列哪项有可学习参数：Conv2d、padding、stride、MaxPool2d？\n\n"
            "## B. 公式推导\n\n"
            "### Q4｜保持尺寸\n\n"
            "输入宽度 32，kernel=3，padding=1，stride=1。输出宽度是多少？\n\n"
            "请写出公式、代入、化简和最终结果四步。\n\n"
            "### Q5｜stride 下采样\n\n"
            "输入宽度 32，kernel=3，padding=1，stride=2。输出宽度是多少？\n\n"
            "请特别标出 padding 对应的 2×1，以及最后的 +1。\n\n"
            "### Q6｜参数量\n\n"
            "Conv2d(3, 8, kernel_size=3, bias=True) 的参数量是多少？\n\n"
            "请分别写出 weight 参数和 bias 参数；不要把输出空间尺寸写入参数量公式。\n\n"
            "## C. 代码阅读与纠错\n\n"
            "### Q7｜填参数\n\n"
            "要把 (2, 3, 32, 32) 变为 (2, 8, 16, 16)，补全：\n\n"
            "~~~python\nnn.Conv2d(3, 8, kernel_size=3, stride=___, padding=___)\n~~~\n\n"
            "除填写参数外，请用输出尺寸公式验证。\n\n"
            "### Q8｜定位 NCHW 错误\n\n"
            "x 的 shape 是 (2, 32, 32, 3)，layer 是 nn.Conv2d(3, 8, 3)。为什么可能报通道错误？\n\n"
            "请指出 Conv2d 把哪个维度当成通道，并写出一种正确调整方式。\n\n"
            "## 作答后怎么做\n\n"
            "将答案提交给测验反馈模块。它会根据 Q1–Q8 的错误类型生成下一轮补救重点；"
            "高分只会触发课程规划复核，不会自动跳过先修。\n\n"
            f"{publication_note}"
        ),
    )
    answer_key = CandidateResource(
        resource_type="assessment_answer_key",
        title=f"{heading}分层测验（教师答案与反馈卷）",
        evidence_ids=evidence_by_kind["exercise"],
        release_status=release_status,
        content=(
            f"# {heading}：分层测验答案与反馈卷\n\n"
            "此文件用于教师审核或系统自动批改，不与学生卷同时发放。\n\n"
            "## 参考答案与评分点\n\n"
            "### Q1（概念混淆）\n\n"
            "答：Conv2d 通常实现互相关，卷积核不做数学卷积的翻转；工程命名仍沿用卷积层。"
            "写出“核不翻转”和“工程命名”各得分。\n\n"
            "### Q2（逻辑跳跃）\n\n"
            "答：局部连接只看邻近像素；参数共享让同一卷积核在不同位置复用。"
            "只写“参数少”但无原因，不给满分。\n\n"
            "### Q3（概念混淆）\n\n"
            "答：只有 Conv2d 有可学习的卷积核和 bias；padding、stride 是超参数，"
            "MaxPool2d 是无参数汇聚操作。\n\n"
            "### Q4\n\n"
            "floor((32+2×1-3)/1)+1=32。评分必须检查是否写出 2×padding。\n\n"
            "### Q5\n\n"
            "floor((32+2×1-3)/2)+1=16。若得到 15，通常漏掉最后的 +1；"
            "若得到 14 或更小，检查是否遗漏 padding。\n\n"
            "### Q6\n\n"
            "weight=3×8×3×3=216，bias=8，总计 224。输出宽高不影响该层参数量。\n\n"
            "### Q7\n\n"
            "stride=2，padding=1；并用 Q5 的公式验证输出为 16×16。\n\n"
            "### Q8\n\n"
            "Conv2d 将第二维解释为通道，当前第二维为 32 而不是 3；"
            "可使用 x.permute(0, 3, 1, 2) 转换为 NCHW。\n\n"
            "## 错题回流表\n\n"
            "| 错题 | 错误类型 | 下一步资源 |\n|---|---|---|\n"
            "| Q1/Q3 | 概念混淆 | 讲义第 4、7 节 + 对比图 |\n"
            "| Q4/Q5/Q6 | 计算错误 | Notebook 公式与参数量单元 |\n"
            "| Q7/Q8 | 代码 shape 错误 | Notebook NCHW 与调试单元 |\n\n"
            "## 证据来源\n\n"
            f"{source_lines}\n\n{publication_note}"
        ),
    )
    return lecture, practical, assessment, answer_key


def _build_notebook(profile: dict[str, Any], handoff: dict[str, Any]) -> dict[str, Any]:
    """Create a runnable, step-by-step notebook for the permitted Conv2d scope."""
    heading = _target_title(profile, handoff)
    depth = _text(handoff.get("depth")) or "intro"
    cells = [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                f"# {heading}：Conv2d 最小可运行实操\n",
                "\n",
                f"当前教学深度：{depth}。按“预测 → 运行 → 核对公式 → 修改参数”完成。\n",
                "\n",
                "本 Notebook 不训练完整 CNN；它先解决图像张量、卷积参数和 shape 三个前置问题。\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "import torch\n",
                "from torch import nn\n",
                "\n",
                "torch.manual_seed(7)\n",
            ],
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 1. 先确认 NCHW\n",
                "\n",
                "PyTorch 的图像输入为 [batch, channel, height, width]。不要把 NHWC 直接送入 Conv2d。\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "x = torch.randn(2, 3, 32, 32)  # [batch, channel, height, width]\n",
                "conv_same = nn.Conv2d(3, 8, kernel_size=3, stride=1, padding=1)\n",
                "y_same = conv_same(x)\n",
                "assert y_same.shape == (2, 8, 32, 32)\n",
                "print('same padding:', tuple(x.shape), '->', tuple(y_same.shape))\n",
            ],
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 2. 公式与实际输出必须一致\n",
                "\n",
                "先用函数计算，再由 Conv2d 的输出 shape 交叉验证。这里专门防止漏写 2×padding。\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "def output_size(size, kernel, padding, stride):\n",
                "    return (size + 2 * padding - kernel) // stride + 1\n",
                "\n",
                "assert output_size(32, 3, 1, 1) == 32\n",
                "assert output_size(32, 3, 1, 2) == 16\n",
                "print('formula checks:', output_size(32, 3, 1, 1), output_size(32, 3, 1, 2))\n",
            ],
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 2.5 手算一个窗口\n",
                "\n",
                "先看单通道、2×2 卷积核的一个位置，理解“逐元素相乘再求和”。\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "small = torch.tensor([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]])\n",
                "kernel = torch.tensor([[1.0, 0.0], [0.0, -1.0]])\n",
                "manual_first = (small[:2, :2] * kernel).sum()\n",
                "assert manual_first.item() == -4.0\n",
                "print('first window correlation result:', manual_first.item())\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "conv_stride = nn.Conv2d(3, 8, kernel_size=3, stride=2, padding=1)\n",
                "y_stride = conv_stride(x)\n",
                "assert y_stride.shape == (2, 8, 16, 16)\n",
                "parameter_count = sum(\n",
                "    parameter.numel() for parameter in conv_stride.parameters()\n",
                ")\n",
                "print('stride=2:', tuple(y_stride.shape), 'parameters:', parameter_count)\n",
            ],
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 3. 通道数改变与空间尺寸改变是两件事\n",
                "\n",
                "out_channels 改变输出特征图数量；stride/padding 改变空间大小。下面将两者分开验证。\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "conv_channels = nn.Conv2d(3, 16, kernel_size=3, stride=1, padding=1)\n",
                "y_channels = conv_channels(x)\n",
                "assert y_channels.shape == (2, 16, 32, 32)\n",
                "assert sum(parameter.numel() for parameter in conv_channels.parameters()) == 448\n",
                "print('channels changed:', tuple(y_channels.shape))\n",
            ],
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 4. 卷积后接池化\n",
                "\n",
                "池化会缩小空间尺寸，但没有可训练卷积核。请与 stride=2 的卷积结果比较。\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "pool = nn.MaxPool2d(kernel_size=2, stride=2)\n",
                "pooled = pool(y_same)\n",
                "assert pooled.shape == (2, 8, 16, 16)\n",
                "print('pooling:', tuple(y_same.shape), '->', tuple(pooled.shape))\n",
            ],
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 5. 调试练习\n",
                "\n",
                "将 padding 改为 0：先预测 32 会变成多少，再修改代码和断言。"
                "若报通道错误，先打印 x.shape，而不是随意改 in_channels。\n",
            ],
        },
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 6. 提交前自检\n",
                "\n",
                "1. 能写出 NCHW 的含义；2. 能手算两组输出尺寸；3. 能解释 224 个参数来自哪里；"
                "4. 能区分卷积与池化。完成后再进入分层测验。\n",
            ],
        },
    ]
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _validate_notebook(notebook: dict[str, Any]) -> dict[str, Any]:
    """Compile and run static generated code cells in a fresh namespace."""
    namespace: dict[str, Any] = {}
    cell_count = 0
    try:
        for index, cell in enumerate(notebook["cells"], start=1):
            if cell.get("cell_type") != "code":
                continue
            source = "".join(cell.get("source", []))
            compile(source, f"<resource-notebook-cell-{index}>", "exec")
            exec(source, namespace)  # noqa: S102 - generated static template only
            cell_count += 1
    except Exception as error:
        return {
            "status": "failed",
            "executed_code_cells": cell_count,
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
    return {
        "status": "passed",
        "executed_code_cells": cell_count,
        "runtime": "local_python_with_torch",
    }


def _coverage_report(
    profile: dict[str, Any],
    requirements: dict[str, Any],
    resources: tuple[CandidateResource, ...],
) -> dict[str, Any]:
    combined = "\n".join(resource.content for resource in resources)
    outcomes = _string_list(requirements.get("learning_outcomes"))
    errors = _top_errors(profile)
    missing_outcomes = [item for item in outcomes if item not in combined]
    missing_errors = [item for item in errors if item not in combined]
    unbound_resources = [item.resource_type for item in resources if not item.evidence_ids]
    return {
        "learning_outcomes_total": len(outcomes),
        "learning_outcomes_missing_from_package": missing_outcomes,
        "error_focus_total": len(errors),
        "error_focus_missing_from_package": missing_errors,
        "resources_without_evidence_binding": unbound_resources,
        "passed": not missing_outcomes and not missing_errors and not unbound_resources,
    }


def _decision_card(
    *,
    root: Path,
    profile_file: Path,
    handoff_file: Path,
    retrieval_file: Path,
    manifest_file: Path | None,
    profile: dict[str, Any],
    handoff: dict[str, Any],
    concept_id: str,
    depth: str,
    release_status: ReleaseStatus,
    blockers: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    scope = _mapping(profile.get("learning_scope"))
    return {
        "release_status": release_status,
        "target": {
            "concept_id": concept_id,
            "delivery_depth": depth,
            "chapter_id": _text(scope.get("chapter_id")),
            "chapter_name": _target_title(profile, handoff),
        },
        "authority_rule": "课程规划交接决定概念、深度、先修与发布门禁；画像只决定呈现和支持方式。",
        "learner_adaptation": {
            "global_theta": _mapping(profile.get("knowledge_mastery")).get("global_theta"),
            "error_focus": _top_errors(profile),
            "preferences": _mapping(profile.get("learning_preferences")),
        },
        "planning_gate": _mapping(handoff.get("resource_generation_gate")),
        "blockers": blockers,
        "warnings": warnings,
        "input_provenance": {
            "input_dir": str(root),
            "profile": profile_file.name,
            "planning_handoff": handoff_file.name,
            "retrieval_output": retrieval_file.name,
            "publication_manifest": manifest_file.name if manifest_file else None,
        },
    }


def _evidence_matrix(
    resources: tuple[CandidateResource, ...],
    candidates: list[dict[str, Any]],
    release_status: ReleaseStatus,
    claim_evidence_ledger: list[dict[str, Any]],
) -> dict[str, Any]:
    records = {
        _evidence_id(item): {
            "content_kind": item.get("content_kind"),
            "source_title": item.get("source_title") or item.get("title"),
            "review_status": item.get("review_status"),
            "evidence_status": item.get("evidence_status"),
            "license_status": item.get("license_status"),
            "locator": item.get("locator") or item.get("heading_path"),
        }
        for item in candidates
    }
    return {
        "release_status": release_status,
        "policy": "候选证据只能支持候选草稿；只有审核、发布和许可证均合规的证据才能支持正式发布。",
        "resource_bindings": [
            {
                "resource_type": resource.resource_type,
                "evidence_ids": list(resource.evidence_ids),
                "citation_status": release_status,
            }
            for resource in resources
        ],
        "claim_bindings": claim_evidence_ledger,
        "evidence_records": records,
    }


def _claim_evidence_ledger(
    candidates: list[dict[str, Any]],
    release_status: ReleaseStatus,
) -> list[dict[str, Any]]:
    by_kind = {
        kind: [_evidence_id(item) for item in candidates if item.get("content_kind") == kind]
        for kind in _REQUIRED_EVIDENCE_KINDS
    }
    status = "published" if release_status == "published" else "candidate_only"
    claims = (
        (
            "lecture.local_connection",
            "lecture_notes",
            "第 3 节：为什么图像适合卷积",
            "局部连接与参数共享解释 CNN 相对全连接层的参数优势。",
            "definition",
        ),
        (
            "lecture.correlation_boundary",
            "lecture_notes",
            "第 4 节：卷积、互相关与特征图",
            "数学卷积与深度学习常用互相关需在卷积核翻转上明确区分。",
            "definition",
        ),
        (
            "lecture.shape_formula",
            "lecture_notes",
            "第 5 节：输出尺寸",
            "输出尺寸计算使用 kernel、padding 和 stride 的标准公式。",
            "definition",
        ),
        (
            "practical.conv2d_mapping",
            "pytorch_practical_guide",
            "第 2–5 节：Conv2d 工作示例",
            "PyTorch Conv2d 参数与输入输出 shape 的映射。",
            "code",
        ),
        (
            "assessment.shape_items",
            "layered_assessment",
            "Q4–Q6：尺寸与参数量",
            "输出尺寸和参数量题目及逐步解析。",
            "exercise",
        ),
        (
            "assessment.code_items",
            "layered_assessment",
            "Q7–Q8：代码阅读",
            "NCHW 与 Conv2d 参数纠错题。",
            "exercise",
        ),
    )
    return [
        {
            "claim_id": claim_id,
            "resource_type": resource_type,
            "section": section,
            "claim": claim,
            "required_evidence_kind": evidence_kind,
            "evidence_ids": by_kind[evidence_kind],
            "citation_status": status if by_kind[evidence_kind] else "missing",
            "publishable": release_status == "published" and bool(by_kind[evidence_kind]),
        }
        for claim_id, resource_type, section, claim, evidence_kind in claims
    ]


def _claim_evidence_coverage(ledger: list[dict[str, Any]]) -> dict[str, Any]:
    unbound = [item["claim_id"] for item in ledger if not item["evidence_ids"]]
    candidate_only = [
        item["claim_id"] for item in ledger if item["citation_status"] == "candidate_only"
    ]
    return {
        "claim_count": len(ledger),
        "unbound_claim_ids": unbound,
        "candidate_only_claim_ids": candidate_only,
        "all_claims_have_evidence": not unbound,
        "all_claims_publishable": bool(ledger)
        and all(item["publishable"] is True for item in ledger),
    }


def _next_actions(
    release_status: ReleaseStatus,
    missing_published_kinds: list[str],
    gate: dict[str, Any],
) -> list[str]:
    if release_status == "published":
        return ["资源已满足发布门禁；仍应执行 Notebook 运行测试和专家抽检。"]
    actions = []
    if missing_published_kinds:
        required_kinds = "、".join(missing_published_kinds)
        actions.append("领域检索/知识库侧需审核发布证据类型：" + required_kinds + "。")
    if gate.get("allowed") is not True:
        actions.append("课程规划侧需在先修完成后重新下发资源交接，并更新发布门禁。")
    actions.append("资源生成侧仅可保留 candidate_draft，不得标为正式课程资源。")
    return actions
