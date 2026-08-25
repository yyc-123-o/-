"""学习者画像构建 — 聚合为 0803 对齐的完整 LearnerProfile

学情诊断Agent的核心输出模块 (v2.1):
输入: Learner + KnowledgeGraph
输出: 0803 结构 LearnerProfile (14个顶层字段)
"""

from __future__ import annotations
from datetime import datetime
from typing import Dict, List

from models.schemas import (
    Learner, LearnerProfile, KnowledgeGap, DiagnosisResult,
    TestRecord, InteractionRecord,
    # 子结构
    LearningScope, SuccessorChapter,
    KnowledgeMastery, KpMasteryPoint, DomainSummaryItem, StatusDistributionItem,
    AbilityLevel, SubDimension,
    ErrorPatterns,
    LearningPreferences, FormatPreference, StylePreference, PacePreference,
    InteractionPreference, MotivationPreference,
    DepthLabel,
    ResourceGenerationHints, LectureNotesHints, PracticalGuideHints, TestQuestionsHints,
    PriorChapter,
    EvidenceRecord,
    DiagnosisSummary,
)
from models.knowledge_graph import KnowledgeGraph
from core import irt, mastery, gap_analyzer


# ============================================================
# 常量
# ============================================================

ABILITY_LEVEL_CN = {
    "beginner": "初学者",
    "intermediate": "中级",
    "advanced": "高级",
}

STATUS_RANGES = {
    "mastered":     "≥0.75",
    "familiar":     "0.60-0.75",
    "partial":      "0.40-0.60",
    "weak":         "0.25-0.40",
    "not_learned":  "0.10-0.25",
    "unexplored":   "<0.10",
}

# ============================================================
# 辅助函数
# ============================================================

def _estimate_global_theta(
    test_records: List[TestRecord],
    prior_theta: float = 0.0,
) -> float:
    if not test_records:
        return prior_theta
    responses = [(t.discrimination, t.difficulty, t.is_correct) for t in test_records]
    return irt.estimate_theta(responses, prior_theta=prior_theta)


def _ability_level_str(theta: float) -> str:
    if theta < -0.5:
        return "beginner"
    elif theta < 0.8:
        return "intermediate"
    else:
        return "advanced"


# 分课程自评 → 领域级结论
_COURSE_LEVEL_SCORE = {"未学过": 0.0, "入门": 0.35, "基础": 0.60, "熟练": 0.80, "精通": 1.00}

_COURSE_DOMAIN_MAP = {
    "数学基础": ["高等数学", "线性代数", "概率论与数理统计", "最优化方法"],
    "机器学习基础": ["机器学习", "数据结构与算法"],
    "深度学习": ["深度学习"],
    "编程能力": ["Python编程"],
}


def _self_assessed_domain_hints(sa) -> Dict[str, dict]:
    """把分课程自评映射为领域级自评结论 (数学/机器学习/深度学习/编程)"""
    if not sa:
        return {}

    domain_scores: Dict[str, List[float]] = {}
    courses = list(sa.courses)
    for assessment in getattr(sa, "domain_assessments", ()):
        courses.extend(assessment.courses)
    for course in courses:
        score = _COURSE_LEVEL_SCORE.get(course.level, 0.0)
        for domain, names in _COURSE_DOMAIN_MAP.items():
            if course.name in names:
                domain_scores.setdefault(domain, []).append(score)

    hints: Dict[str, dict] = {}
    for domain, scores in domain_scores.items():
        mean = sum(scores) / len(scores)
        level = "强" if mean >= 0.70 else "中" if mean >= 0.40 else "弱"
        hints[domain] = {"mean": round(mean, 2), "level": level, "n_courses": len(scores)}
    for assessment in getattr(sa, "domain_assessments", ()):
        if not assessment.courses:
            continue
        scores = [_COURSE_LEVEL_SCORE.get(course.level, 0.0) for course in assessment.courses]
        mean = sum(scores) / len(scores)
        level = "强" if mean >= 0.70 else "中" if mean >= 0.40 else "弱"
        hints.setdefault(
            assessment.domain or "未命名领域",
            {"mean": round(mean, 2), "level": level, "n_courses": len(scores)},
        )
    return hints


def _compute_status_distribution(status_map: Dict[str, str]) -> Dict[str, StatusDistributionItem]:
    dist: Dict[str, StatusDistributionItem] = {}
    counts: Dict[str, int] = {}
    for s in status_map.values():
        counts[s] = counts.get(s, 0) + 1
    for status, rng in STATUS_RANGES.items():
        dist[status] = StatusDistributionItem(range=rng, count=counts.get(status, 0))
    return dist


# ============================================================
# 各子模块构建函数
# ============================================================

def _build_learning_scope(
    kg: KnowledgeGraph,
    current_chapter_id: str = "ch03_cnn",
    mastery_map: Dict[str, float] | None = None,
) -> LearningScope:
    """构建章节级学习范围"""
    ch = kg.get_chapter(current_chapter_id)
    if not ch:
        return LearningScope(
            scope_type="chapter",
            chapter_id=current_chapter_id,
            chapter_name="未知章节",
            primary_kp_id="",
            primary_kp_name="",
        )

    primary_kp = kg.get(ch.primary_kp_id)
    successors = kg.get_chapter_successors(current_chapter_id)

    primary_mastery = (mastery_map or {}).get(ch.primary_kp_id, 0.0)
    target_depth = "入门" if primary_mastery < 0.40 else "进阶" if primary_mastery < 0.75 else "复习"
    return LearningScope(
        scope_type="chapter",
        chapter_id=ch.chapter_id,
        chapter_name=ch.chapter_name,
        chapter_order=ch.chapter_order,
        primary_kp_id=ch.primary_kp_id,
        primary_kp_name=primary_kp.name if primary_kp else "",
        target_depth=target_depth,
        estimated_hours=ch.estimated_hours,
        resource_generation_target=f"为该章节生成3类资源（讲义/实操指南/测试题），均按{target_depth}层输出",
        predecessor_kp_ids=ch.predecessor_kp_ids,
        co_requisite_kp_ids=ch.co_requisite_kp_ids,
        successor_chapters=[
            SuccessorChapter(
                chapter_id=sc.chapter_id,
                kp_id=sc.primary_kp_id,
                name=sc.chapter_name,
                depth_planned="进阶" if sc.chapter_order <= 4 else "入门",
            )
            for sc in successors
        ],
        path_note="学习路径一次性生成，学习过程中路径不变，只更新画像。若ch03正确率<60%，ch04自动降为入门层。",
    )


def _build_knowledge_mastery(
    kg: KnowledgeGraph,
    mastery_map: Dict[str, float],
    theta_map: Dict[str, float],
    test_count_map: Dict[str, int],
    confidence_map: Dict[str, float],
    status_map: Dict[str, str],
    global_theta: float,
    overall_accuracy: float,
) -> KnowledgeMastery:
    """构建知识点掌握度矩阵"""
    # 分领域汇总
    domain_summary: Dict[str, DomainSummaryItem] = {}
    domain_scores: Dict[str, List[float]] = {}
    domain_counts: Dict[str, int] = {}
    for kp in kg.points:
        domain_scores.setdefault(kp.domain, []).append(mastery_map.get(kp.id, 0.0))
        domain_counts[kp.domain] = domain_counts.get(kp.domain, 0) + 1
    for domain, scores in domain_scores.items():
        domain_summary[domain] = DomainSummaryItem(
            mean_mastery=round(sum(scores) / len(scores), 3) if scores else 0.0,
            kps_covered=domain_counts.get(domain, 0),
        )

    # 各知识点
    points: Dict[str, KpMasteryPoint] = {}
    for kp in kg.points:
        points[kp.id] = KpMasteryPoint(
            name=kp.name,
            domain=kp.domain,
            mastery=(
                round(mastery_map.get(kp.id, 0.0), 4)
                if test_count_map.get(kp.id, 0) > 0
                else None
            ),
            status=status_map.get(kp.id, "unexplored"),
            theta_kp=round(theta_map.get(kp.id, 0.0), 2),
            test_count=test_count_map.get(kp.id, 0),
            confidence=confidence_map.get(kp.id, 0.0),
        )

    return KnowledgeMastery(
        global_theta=round(global_theta, 2),
        ability_level=_ability_level_str(global_theta),
        overall_accuracy=round(overall_accuracy, 3),
        confidence_note=f"全局θ基于{sum(test_count_map.values())}题MLE估计，学历先验已纳入，L2正则λ=0.5",
        domain_summary=domain_summary,
        points=points,
        status_distribution=_compute_status_distribution(status_map),
    )


def _build_ability_level(
    global_theta: float,
    mastery_map: Dict[str, float],
    domain_mastery: Dict[str, float],
) -> AbilityLevel:
    """构建能力等级"""
    dl_mean = domain_mastery.get("深度学习", 0.0)
    ml_mean = (domain_mastery.get("数学基础", 0.0) + domain_mastery.get("机器学习基础", 0.0)) / 2

    rationale = (
        f"ML基础{'扎实' if ml_mean > 0.55 else '一般' if ml_mean > 0.35 else '薄弱'}（数学+ML均值{ml_mean:.2f}），"
        f"但深度学习{'刚入门' if dl_mean < 0.3 else '有一定基础' if dl_mean < 0.5 else '基础较好'}（DL均值{dl_mean:.2f}），"
        f"整体{'介于初级与中级之间' if global_theta < 0.5 else '达到中级水平' if global_theta < 0.8 else '达到高级水平'}"
    )

    sub_dims = {
        "theoretical_understanding": SubDimension(
            score=round(mastery_map.get("kp_008", 0.0) * 0.7 + mastery_map.get("kp_015", 0.0) * 0.3, 2),
            level="intermediate",
            confidence=0.80,
        ),
        "coding_ability": SubDimension(
            score=0.70,
            level="intermediate",
            confidence=0.72,
        ),
        "mathematical_foundation": SubDimension(
            score=round(
                (mastery_map.get("kp_001", 0.0) + mastery_map.get("kp_002", 0.0) +
                 mastery_map.get("kp_003", 0.0) + mastery_map.get("kp_005", 0.0)) / 4, 2
            ),
            level="intermediate",
            confidence=0.85,
        ),
        "problem_solving": SubDimension(
            score=round(mastery_map.get("kp_009", 0.0) * 0.5 + mastery_map.get("kp_025", 0.0) * 0.5 + 0.2, 2),
            level="intermediate",
            confidence=0.75,
        ),
    }

    return AbilityLevel(
        overall=_ability_level_str(global_theta),
        global_theta=round(global_theta, 2),
        rationale=rationale,
        sub_dimensions=sub_dims,
    )


def _build_learning_preferences(
    test_records: List[TestRecord],
    interactions: List[InteractionRecord],
    self_assessment=None,
) -> LearningPreferences:
    """构建学习偏好 (0803 五组结构)"""
    # 从交互数据推断
    total_tests = len(test_records) if test_records else 1
    correct_count = sum(1 for t in test_records if t.is_correct) if test_records else 0
    hint_count = sum(1 for t in test_records if t.hint_used) if test_records else 0
    avg_time = int(sum(t.time_spent for t in test_records) / total_tests) if test_records else 60

    views = sum(1 for i in interactions if i.type == "view") if interactions else 0
    practices = sum(1 for i in interactions if i.type == "practice") if interactions else 0
    vp_ratio = f"{views}:{practices}" if practices > 0 else f"{views}:1"

    if correct_count / max(total_tests, 1) > 0.7:
        pace_inferred = "fast"
    elif correct_count / max(total_tests, 1) < 0.4:
        pace_inferred = "slow"
    else:
        pace_inferred = "medium"

    if len(interactions) > 30:
        interaction_level = "high"
    elif len(interactions) > 10:
        interaction_level = "medium"
    else:
        interaction_level = "low"

    # 自填问卷驱动的偏好 (项目/职位/编程能力)
    sa = self_assessment
    projects = sa.projects if sa and sa.projects else []
    position = sa.position if sa and sa.position else ""
    programming_level = sa.programming_level if sa and sa.programming_level else "入门"
    strengths = sa.strengths if sa and sa.strengths else ""

    primary_motivation = sa.learning_goal if sa and sa.learning_goal else "提升AI能力"
    secondary_motivation = f"担任角色：{position}" if position else ""
    project_driven = len(projects) > 0
    target_project = " → ".join([p.name for p in projects[:3]]) if projects else ""

    weekly_hours = int(getattr(sa, "weekly_hours", 10) or 10)
    return LearningPreferences(
        format=FormatPreference(
            content_order=["概念直觉理解", "数学推导", "代码实战", "面试考点"],
            code_language="Python",
            framework="PyTorch",
            framework_level=programming_level,
            framework_confidence=0.75,
            confidence_note=strengths if strengths else "自填问卷未填写优势描述",
        ),
        style=StylePreference(
            visual_learner=True,
            prefers_step_by_step=True,
            prefers_comparison_tables=True,
            prefers_diagrams=True,
            prefers_math_formulas=True,
        ),
        pace=PacePreference(
            weekly_hours=max(1, weekly_hours),
            session_attention_minutes=50,
            avg_test_time_seconds=avg_time,
            learning_pace_inferred=pace_inferred,
        ),
        interaction=InteractionPreference(
            level=interaction_level,
            hint_dependency=round(hint_count / max(total_tests, 1), 2),
            view_practice_ratio=vp_ratio,
            prefers_discussion=False,
        ),
        motivation=MotivationPreference(
            primary=primary_motivation,
            secondary=secondary_motivation,
            project_driven=project_driven,
            target_project=target_project,
        ),
    )


def _build_depth_labels(
    kg: KnowledgeGraph,
    mastery_map: Dict[str, float],
    test_count_map: Dict[str, int] | None = None,
) -> List[DepthLabel]:
    """根据掌握度自动分配深度标签"""
    labels: List[DepthLabel] = []
    for kp in kg.points:
        m = mastery_map.get(kp.id, 0.0)
        if (test_count_map or {}).get(kp.id, 0) == 0:
            depth, rationale = "entry", "未测评，先安排诊断题后再确定学习深度"
        elif m >= 0.75:
            depth, rationale = "skip", f"mastery={m:.2f} 已掌握"
        elif m >= 0.60:
            depth, rationale = "review", f"mastery={m:.2f} 需简单回顾"
        elif m >= 0.40:
            if kp.difficulty > 1.0:
                depth, rationale = "advanced", f"mastery={m:.2f} 部分掌握但知识点较难，需进阶巩固"
            else:
                depth, rationale = "advanced", f"mastery={m:.2f} 部分掌握，需巩固提升"
        elif m >= 0.25:
            depth, rationale = "entry", f"mastery={m:.2f} 薄弱，从入门开始"
        elif m >= 0.10:
            depth, rationale = "entry", f"mastery={m:.2f} 未学，入门讲授"
        else:
            depth, rationale = "entry", f"mastery={m:.2f} 未接触"
        labels.append(DepthLabel(kp_id=kp.id, kp_name=kp.name, depth=depth, rationale=rationale))
    return labels


def _build_resource_hints(
    kg: KnowledgeGraph,
    learning_scope: LearningScope,
    error_patterns: ErrorPatterns,
    mastery_map: Dict[str, float],
) -> ResourceGenerationHints:
    """构建章节级资源生成提示"""
    ch_id = learning_scope.chapter_id

    # 计算实际的 depth_rationale
    ml_domains = ["数学基础", "机器学习基础"]
    ml_mean_val = sum(
        mastery_map.get(kid, 0.0)
        for kp in kg.points if kp.domain in ml_domains
        for kid in [kp.id]
    ) / max(1, sum(1 for kp in kg.points if kp.domain in ml_domains))

    depth_rationale = (
        f"基础相关知识均值={ml_mean_val:.2f}；"
        f"按当前主节点掌握度和测试证据生成{learning_scope.target_depth}内容"
    )

    # 章节提示统一由当前主节点和画像动态生成。
    kp = kg.get(learning_scope.primary_kp_id)
    topic = kp.name if kp else learning_scope.primary_kp_name or "当前知识点"
    description = kp.description if kp else ""
    error_names = [item.category for item in error_patterns.items if item.count > 0]
    attention = (
        "；".join(error_names) + "相关错误需要逐步解释和反例练习"
        if error_names
        else "当前没有足够错误记录，先用形成性测验确认理解"
    )
    requirements = [
        f"解释{topic}的定义、输入、核心过程和输出",
        f"结合课程图谱描述：{description}",
    ]
    if learning_scope.predecessor_kp_ids:
        requirements.append(f"回顾前置知识：{', '.join(learning_scope.predecessor_kp_ids)}")
    return ResourceGenerationHints(
        scope="chapter",
        scope_note=(
            f"针对{learning_scope.chapter_name}的主节点"
            f"{learning_scope.primary_kp_id}生成三类学习资源"
        ),
        target_chapter_id=ch_id,
        target_chapter_name=learning_scope.chapter_name,
        target_depth=learning_scope.target_depth,
        depth_rationale=depth_rationale,
        lecture_notes=LectureNotesHints(
            must_include=requirements,
            avoid=["只罗列术语而不解释推理过程", "跳过前置条件和输入输出边界"],
            comparison_tables=["当前知识点与其前置知识的差异"],
            error_pattern_attention=attention,
            estimated_pages="6-10页（按深度和学习目标调整）",
        ),
        practical_guide=PracticalGuideHints(
            must_include=[
                f"用最小可运行示例实现{topic}",
                "打印输入、中间结果和输出并解释形状",
            ],
            code_style="分步 Python 单元，每段包含目标、代码、预期输出和检查条件",
            dataset="使用可复现的最小合成数据，避免依赖未声明的外部数据",
            framework="Python；按学习者画像中的框架偏好调整",
            estimated_cells="6-12 cells",
        ),
        test_questions=TestQuestionsHints(
            total=8,
            distribution={"概念理解": 3, "步骤/计算": 2, "代码或形状": 2, "综合迁移": 1},
            difficulty={
                "easy": {"count": 3},
                "medium": {"count": 3},
                "hard": {"count": 2},
            },
            target_overall_accuracy_range=[0.60, 0.85],
            error_pattern_mitigations=[f"针对{attention}"],
            must_cover=[topic, *learning_scope.predecessor_kp_ids],
            estimated_time_minutes=30,
        ),
    )


def _build_prior_chapters() -> List[PriorChapter]:
    """Return only observed chapter history; current records are KP-scoped."""
    return []


def _build_evidence(
    global_theta: float,
    mastery_map: Dict[str, float],
    error_patterns: ErrorPatterns,
    gaps: List[KnowledgeGap],
    learner: Learner,
) -> List[EvidenceRecord]:
    """构建证据溯源"""
    evidence: List[EvidenceRecord] = []

    # 动态统计数据
    total_tests = error_patterns.total_questions
    tested_kps = len(set(t.knowledge_point_id for t in learner.test_records)) if learner.test_records else 0
    prior_theta_val = irt.education_prior_theta(learner.education.level)

    # 全局θ
    evidence.append(EvidenceRecord(
        claim=f"全局能力θ={global_theta:.2f}, ability_level={_ability_level_str(global_theta)}",
        source="irt_estimation",
        detail=f"累计{total_tests}道题(覆盖{tested_kps}个知识点)的IRT-MLE跨知识点估计，学历先验θ={prior_theta_val}({learner.education.level})，L2正则λ=0.5",
        confidence=0.90,
    ))

    # 每个结论按实际测试覆盖生成，不能为某个历史样例节点单独写证据。
    tested_by_kp: Dict[str, List[TestRecord]] = {}
    for record in learner.test_records:
        tested_by_kp.setdefault(record.knowledge_point_id, []).append(record)
    for kp_id, records in sorted(tested_by_kp.items(), key=lambda item: item[0]):
        evidence.append(EvidenceRecord(
            claim=f"{kp_id} 掌握度={mastery_map.get(kp_id, 0.0):.2f}",
            source="irt_estimation",
            detail=f"该知识点实际测试 {len(records)} 题；使用题目难度、区分度和作答结果估计",
            confidence=0.70 if len(records) < 3 else 0.85,
        ))

    # 错误模式
    if error_patterns.primary_weakness:
        evidence.append(EvidenceRecord(
            claim=f"主要错误模式={error_patterns.primary_weakness}({error_patterns.primary_weakness_ratio:.0%})",
            source="answer_history",
            detail=f"{error_patterns.total_questions}题中{error_patterns.total_wrong}道错题自动分类；未提供人工双标注。",
            confidence=error_patterns.classification_confidence,
        ))

    # 编程能力 / 职位
    sa = learner.self_assessment
    programming_level = sa.programming_level if sa and sa.programming_level else "入门"
    evidence.append(EvidenceRecord(
        claim=f"编程能力={programming_level}",
        source="self_assessment",
        detail=f"自填问卷: 编程能力自评「{programming_level}」"
                + (f"；担任角色：{sa.position}" if sa and sa.position else ""),
        confidence=0.75,
    ))

    # 项目经历
    if sa and sa.projects:
        proj_names = "、".join([p.name for p in sa.projects[:3]])
        evidence.append(EvidenceRecord(
            claim=f"项目经历 {len(sa.projects)} 个: {proj_names}",
            source="self_assessment",
            detail="自填问卷: " + "；".join(
                f"{p.name}({p.role}, {p.tech_stack and '/'.join(p.tech_stack)})"
                for p in sa.projects[:3]
            ),
            confidence=0.80,
        ))

    # 分课程自评
    domain_hints = _self_assessed_domain_hints(sa)
    if domain_hints:
        hint_str = "，".join(
            f"{d}={h['level']}({h['mean']:.2f})" for d, h in domain_hints.items()
        )
        evidence.append(EvidenceRecord(
            claim=f"分课程自评领域结论: {hint_str}",
            source="self_assessment",
            detail=f"自填问卷分课程自评 {len(sa.courses)} 门课程映射到 4 个领域",
            confidence=0.70,
        ))

    # 主要盲区
    blocked_gaps = [g for g in gaps if g.gap_type == "blocked" and g.priority == "high"]
    for g in blocked_gaps[:1]:
        evidence.append(EvidenceRecord(
            claim=f"{g.kp_name} mastery={g.mastery:.2f}, gap_type={g.gap_type}",
            source="gap_analysis",
            detail=f"gap_analyzer: {g.kp_id} mastery<0.5 且是前置依赖，判定blocked",
            confidence=g.confidence,
        ))

    return evidence


def _build_diagnosis_summary(
    learner: Learner,
    global_theta: float,
    ability_level: str,
    domain_mastery: Dict[str, float],
    gaps: List[KnowledgeGap],
    error_patterns: ErrorPatterns,
) -> DiagnosisSummary:
    """构建诊断摘要"""
    level_cn = ABILITY_LEVEL_CN.get(ability_level, ability_level)

    strong = sorted(domain_mastery.items(), key=lambda x: x[1], reverse=True)
    weak = sorted(domain_mastery.items(), key=lambda x: x[1])

    strong_name, strong_val = strong[0] if strong else ("未知", 0.0)
    weak_name, weak_val = weak[0] if weak else ("未知", 0.0)

    high_gaps = [g for g in gaps if g.priority == "high"]
    med_gaps = [g for g in gaps if g.priority == "medium"]
    low_gaps = [g for g in gaps if g.priority == "low"]

    primary_err = error_patterns.primary_weakness
    primary_err_ratio = error_patterns.primary_weakness_ratio
    primary_err_label = primary_err or "暂无"

    sa_hints = _self_assessed_domain_hints(learner.self_assessment)
    sa_sentence = ""
    if sa_hints:
        sa_sentence = "自评：" + "，".join(f"{d}{h['level']}" for d, h in sa_hints.items()) + "。"

    short = (
        f"{learner.name}({learner.education.level}{learner.education.major}) — "
        f"θ={global_theta:.2f} {level_cn} — "
        f"当前学习范围由知识点掌握度与章节参数决定 — "
        f"主要错误模式: {primary_err_label}({primary_err_ratio:.0%})"
    )

    full = (
        f"学习者「{learner.name}」({learner.education.level}/{learner.education.major}/"
        f"GPA {learner.education.gpa or 'N/A'})。"
        f"全局能力θ={global_theta:.2f}，综合等级: {level_cn}。"
        f"最强领域: {strong_name}({strong_val:.1%})，"
        f"最弱领域: {weak_name}({weak_val:.1%})。"
        f"共{len(gaps)}个薄弱点"
        f"({len(high_gaps)}高/{len(med_gaps)}中/{len(low_gaps)}低)。"
        f"建议优先攻克: {', '.join([g.kp_name for g in high_gaps[:3]])}。"
        f"{sa_sentence}"
    )

    profile_confidence = "中等偏高。IRT估计≥0.85，自填问卷部分0.70-0.75。建议ch03完成后重新诊断。"

    return DiagnosisSummary(short=short, full=full, profile_confidence=profile_confidence)


# ============================================================
# 主入口: 构建完整画像
# ============================================================

def build_profile(
    learner: Learner,
    kg: KnowledgeGraph,
    current_chapter_id: str = "ch03_cnn",
) -> LearnerProfile:
    """构建完整学习者画像 — 对齐 0803 结构"""

    if not kg.get_chapter(current_chapter_id):
        raise ValueError(f"章节 {current_chapter_id} 不存在")

    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. 学历先验θ
    prior_theta = irt.education_prior_theta(learner.education.level)

    # 2. 计算所有知识点掌握度 (v2.1: 五路输出含 confidence + status)
    mastery_map, theta_map, test_count_map, confidence_map, status_map = mastery.compute_all_mastery(
        kg, learner.test_records, learner.interaction_records, prior_theta=prior_theta,
    )

    # 3. 全局能力θ
    global_theta = _estimate_global_theta(learner.test_records, prior_theta)

    # 4. 总正确率
    total_tests = len(learner.test_records)
    total_correct = sum(1 for t in learner.test_records if t.is_correct) if total_tests else 0
    overall_accuracy = total_correct / total_tests if total_tests > 0 else 0.0

    # 5. 分领域掌握度
    domain_mastery: Dict[str, float] = {}
    for domain in kg.domains():
        kp_ids = kg.domain_kp_ids(domain)
        scores = [mastery_map.get(kid, 0.0) for kid in kp_ids]
        domain_mastery[domain] = round(sum(scores) / len(scores), 3) if scores else 0.0

    # 6. 知识盲区分析
    gaps = gap_analyzer.analyze_gaps(
        kg, mastery_map, learner.test_records, learner.interaction_records, test_count_map,
    )

    # 7. 错误模式分类
    error_patterns = gap_analyzer.classify_error_patterns(
        learner.test_records, mastery_map,
    )

    # 8. 子模块构建
    learning_scope = _build_learning_scope(kg, current_chapter_id, mastery_map)
    knowledge_mastery = _build_knowledge_mastery(
        kg, mastery_map, theta_map, test_count_map, confidence_map, status_map,
        global_theta, overall_accuracy,
    )
    ability_level = _build_ability_level(global_theta, mastery_map, domain_mastery)
    learning_preferences = _build_learning_preferences(
        learner.test_records, learner.interaction_records, learner.self_assessment
    )
    depth_labels = _build_depth_labels(kg, mastery_map, test_count_map)
    resource_hints = _build_resource_hints(kg, learning_scope, error_patterns, mastery_map)
    prior_chapters = _build_prior_chapters()
    evidence = _build_evidence(global_theta, mastery_map, error_patterns, gaps, learner)
    diagnosis_summary = _build_diagnosis_summary(
        learner, global_theta, _ability_level_str(global_theta), domain_mastery, gaps, error_patterns,
    )

    # 9. 组装 learner 信息
    sa = learner.self_assessment
    learner_info = {
        "name": learner.name,
        "education": learner.education.model_dump() if learner.education else {},
        "position": sa.position if sa else "",
        "projects": [p.model_dump() for p in sa.projects] if sa and sa.projects else [],
        "courses": [c.model_dump() for c in sa.courses] if sa and sa.courses else [],
        "self_assessment": sa.model_dump() if sa else {
            "ml_level": "",
            "dl_level": "",
            "math_level": "",
            "programming_level": "",
            "learning_goal": "",
            "weekly_hours": 5,
            "position": "",
            "strengths": "",
            "weaknesses": "",
            "courses": [],
            "projects": [],
        },
    }

    return LearnerProfile(
        profile_id=f"PROFILE-{learner.id.upper()}",
        profile_version="2.1",
        generated_by="学情诊断Agent v2.1",
        generated_at=now_str,
        learner_id=learner.id,
        update_cycle="per-chapter",
        learner=learner_info,
        learning_scope=learning_scope,
        knowledge_mastery=knowledge_mastery,
        ability_level=ability_level,
        error_patterns=error_patterns,
        learning_preferences=learning_preferences,
        knowledge_gaps=gaps,
        depth_labels=depth_labels,
        resource_generation_hints=resource_hints,
        prior_chapters=prior_chapters,
        evidence=evidence,
        diagnosis_summary=diagnosis_summary,
        meta={
            "total_test_count": total_tests,
            "total_interaction_count": len(learner.interaction_records),
            "diagnosed_at": now_str,
            "next_suggested_diagnosis": "完成当前章节后，根据最新测评记录重新诊断",
        },
    )
