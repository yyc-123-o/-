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


# 五维领域自评 → 领域级结论
_COURSE_LEVEL_SCORE = {"未学过": 0.0, "入门": 0.35, "基础": 0.60, "熟练": 0.80, "精通": 1.00}


def _self_assessed_domain_hints(sa) -> Dict[str, dict]:
    """把五维领域自评映射为领域级结论

    输入: sa.domain_assessments (数学基础/机器学习基础/深度学习/优化算法/实践应用)
    输出: {领域名: {mean, level, n_courses}}
    """
    if not sa or not sa.domain_assessments:
        return {}

    hints: Dict[str, dict] = {}
    for da in sa.domain_assessments:
        if not da.courses:
            continue
        scores = [_COURSE_LEVEL_SCORE.get(c.level, 0.0) for c in da.courses]
        if not scores:
            continue
        mean = sum(scores) / len(scores)
        level = "强" if mean >= 0.70 else "中" if mean >= 0.40 else "弱"
        hints[da.domain] = {"mean": round(mean, 2), "level": level, "n_courses": len(scores)}
    return hints


def _extract_programming_level(sa) -> str:
    """从五维自评中提取编程能力（实践领域的 Python 编程水平）"""
    if not sa or not sa.domain_assessments:
        return "入门"
    for da in sa.domain_assessments:
        if da.domain in ("实践应用", "实践"):
            for c in da.courses:
                if "Python" in c.name or "编程" in c.name:
                    return c.level
            if da.courses:
                scores = [_COURSE_LEVEL_SCORE.get(c.level, 0.0) for c in da.courses]
                avg = sum(scores) / len(scores)
                if avg >= 0.80:
                    return "熟练"
                elif avg >= 0.60:
                    return "基础"
                elif avg >= 0.35:
                    return "入门"
                return "未学过"
    return "入门"


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

def _build_learning_scope(kg: KnowledgeGraph, current_chapter_id: str = "ch03_cnn") -> LearningScope:
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

    return LearningScope(
        scope_type="chapter",
        chapter_id=ch.chapter_id,
        chapter_name=ch.chapter_name,
        chapter_order=ch.chapter_order,
        primary_kp_id=ch.primary_kp_id,
        primary_kp_name=primary_kp.name if primary_kp else "",
        target_depth="进阶",
        estimated_hours=ch.estimated_hours,
        resource_generation_target=f"为该章节生成3类资源（讲义/实操指南/测试题），均按进阶层输出",
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
        tested = test_count_map.get(kp.id, 0) > 0
        points[kp.id] = KpMasteryPoint(
            name=kp.name,
            domain=kp.domain,
            mastery=(round(mastery_map[kp.id], 4) if tested else None),
            status=status_map.get(kp.id, "unexplored") if tested else "unexplored",
            theta_kp=round(theta_map.get(kp.id, 0.0), 2) if tested else 0.0,
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

    # 自填问卷驱动的偏好 (项目/编程能力)
    sa = self_assessment
    projects = sa.projects if sa and sa.projects else []
    programming_level = _extract_programming_level(sa)
    domain_hints = _self_assessed_domain_hints(sa)
    strengths_note = "，".join(f"{d}={h['level']}" for d, h in domain_hints.items()) if domain_hints else ""

    primary_motivation = sa.learning_goal if sa and sa.learning_goal else "提升AI能力"
    secondary_motivation = ""
    project_driven = len(projects) > 0
    target_project = " → ".join([p.name for p in projects[:3]]) if projects else ""

    return LearningPreferences(
        format=FormatPreference(
            content_order=["概念直觉理解", "数学推导", "代码实战", "面试考点"],
            code_language="Python",
            framework="PyTorch",
            framework_level=programming_level,
            framework_confidence=0.75,
            confidence_note=strengths_note if strengths_note else "自填问卷未填写课程自评",
        ),
        style=StylePreference(
            visual_learner=True,
            prefers_step_by_step=True,
            prefers_comparison_tables=True,
            prefers_diagrams=True,
            prefers_math_formulas=True,
        ),
        pace=PacePreference(
            weekly_hours=10,
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


def _build_depth_labels(kg: KnowledgeGraph, mastery_map: Dict[str, float]) -> List[DepthLabel]:
    """根据掌握度自动分配深度标签"""
    labels: List[DepthLabel] = []
    for kp in kg.points:
        m = mastery_map.get(kp.id, 0.0)
        if m >= 0.75:
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
    chapter_ids = [learning_scope.primary_kp_id, *learning_scope.co_requisite_kp_ids]
    chapter_points = [kg.get(kid) for kid in chapter_ids if kg.get(kid)]
    tested = [mastery_map[kp.id] for kp in chapter_points if kp.id in mastery_map]
    mean = sum(tested) / len(tested) if tested else 0.0
    target_depth = "skip" if mean >= 0.75 else "review" if mean >= 0.60 else "advanced" if mean >= 0.40 else "entry"
    errors = [item.category for item in error_patterns.items if item.count]
    must_include = [f"{kp.name}：{kp.description or '核心概念、典型例题与自测'}" for kp in chapter_points]
    return ResourceGenerationHints(
        scope="chapter",
        scope_note=f"资源范围为章节 {learning_scope.chapter_id}，主知识点 {learning_scope.primary_kp_id}",
        target_chapter_id=learning_scope.chapter_id,
        target_chapter_name=learning_scope.chapter_name,
        target_depth=target_depth,
        depth_rationale=f"章节已测知识点均值={mean:.2f}，依据当前掌握度分配",
        lecture_notes=LectureNotesHints(
            must_include=must_include,
            comparison_tables=["章节内知识点概念与适用条件对比"],
            error_pattern_attention="；".join(errors) if errors else "暂无已观测错误模式，使用形成性练习验证理解",
            estimated_pages="按知识点数量生成",
        ),
        practical_guide=PracticalGuideHints(
            must_include=[f"围绕{kp.name}设计最小可运行练习" for kp in chapter_points],
            code_style="分步骤、可运行、标注输入输出",
            dataset="由资源平台按章节元数据选择",
            framework="根据学习者问卷与已有记录选择",
            estimated_cells="按练习数量生成",
        ),
        test_questions=TestQuestionsHints(
            total=max(5, len(chapter_points) * 2),
            distribution={"概念理解": len(chapter_points), "应用练习": len(chapter_points)},
            difficulty={"adaptive": {"target_depth": target_depth}},
            error_pattern_mitigations=[f"针对{error}增加可解释反馈" for error in errors],
            must_cover=[kp.id for kp in chapter_points],
            estimated_time_minutes=max(15, len(chapter_points) * 8),
        ),
    )

    if False:
        return ResourceGenerationHints(
            scope="chapter",
            scope_note="以下提示针对完整章节 ch03_cnn（卷积神经网络CNN/进阶层），资源生成Agent需据此生成该章的全部3类资源，而非仅针对某个单一知识点",
            target_chapter_id="ch03_cnn",
            target_chapter_name="卷积神经网络（CNN）",
            target_depth="进阶",
            depth_rationale=depth_rationale,
            lecture_notes=LectureNotesHints(
                must_include=[
                    "卷积运算的数学定义（互相关 vs 卷积的区别）",
                    "CNN各层详解：卷积层（kernel/filter/stride/padding）、池化层（max/avg/global）、全连接层",
                    "感受野（Receptive Field）的定义、计算公式与直观理解",
                    "参数共享与局部连接 — CNN vs MLP 的参数量对比表",
                    "特征图可视化：浅层检测边缘/纹理，深层检测语义",
                    "BatchNorm原理",
                    "Dropout在CNN中的特殊用法",
                    "1×1卷积的三种用途：降维/升维/跨通道信息融合",
                    "常见训练技巧：数据标准化、学习率warmup、梯度裁剪",
                ],
                avoid=[
                    "纯代码堆砌而无原理铺垫",
                    "跳过'为什么CNN适合图像'的论证（回应错误模式'逻辑跳跃'）",
                ],
                comparison_tables=[
                    "CNN vs MLP (参数量/平移不变性/计算复杂度)",
                    "Average Pooling vs Max Pooling vs Global Pooling",
                    "Valid Padding vs Same Padding (输出尺寸对比)",
                    "BatchNorm vs LayerNorm vs InstanceNorm",
                    "各激活函数在CNN中的适用场景 (ReLU/LeakyReLU/GELU)",
                ],
                error_pattern_attention="特别注意区分'卷积'与'互相关'操作、区分BatchNorm的training/eval模式，这两个是高频概念混淆点",
                estimated_pages="12-15页（含图）",
            ),
            practical_guide=PracticalGuideHints(
                must_include=[
                    "PyTorch nn.Conv2d / nn.MaxPool2d / nn.BatchNorm2d 的逐参数详解",
                    "从零构建一个LeNet-5风格CNN（CIFAR-10数据集），完整可运行",
                    "每一层输入输出shape用注释标注",
                    "训练循环：含loss曲线/accuracy曲线的实时可视化代码",
                    "常见Bug调试指南：维度不匹配、out of memory、NaN loss",
                    "使用torchsummary或手写代码打印每层参数量",
                    "特征图可视化：注册hook提取中间层输出并绘图",
                ],
                code_style="Jupyter Notebook分段式，每段不超过30行，Markdown + Code Cell交替，函数/类有完整docstring",
                dataset="CIFAR-10（32×32×3, 10类, 5万训练+1万测试）",
                framework="PyTorch 2.x",
                estimated_cells="15-20 cells",
            ),
            test_questions=TestQuestionsHints(
                total=10,
                distribution={
                    "概念理解（选择题/判断题）": 3,
                    "计算推导（输出尺寸/参数量/感受野）": 3,
                    "代码填空（PyTorch CNN层定义）": 2,
                    "综合分析（给定场景选架构并论证）": 2,
                },
                difficulty={
                    "easy": {"count": 3, "target_accuracy": ">80%"},
                    "medium": {"count": 4, "target_accuracy": "60-80%"},
                    "hard": {"count": 3, "target_accuracy": "40-60%"},
                },
                target_overall_accuracy_range=[0.60, 0.85],
                error_pattern_mitigations=[
                    "概念理解题：设置2个以上易混淆干扰项（回应'概念混淆'弱点）",
                    "计算推导题：要求写出中间步骤（回应'逻辑跳跃'弱点）",
                    "代码填空题：在kernel_size/stride/padding处留空",
                    "综合分析题：题干中用**加粗**突出约束条件（回应'忽略条件'弱点）",
                ],
                must_cover=[
                    "卷积核参数计算（in_channels × out_channels × kH × kW）",
                    "输出尺寸公式 ⌊(W−F+2P)/S⌋+1",
                    "1×1卷积的作用与计算",
                    "BatchNorm的training/eval行为差异",
                    "感受野递推公式",
                    "参数量最大的层（全连接层）",
                ],
                estimated_time_minutes=45,
            ),
        )
    else:
        # 通用章节提示
        return ResourceGenerationHints(
            scope="chapter",
            scope_note=f"针对章节 {ch_id} 的通用资源生成提示",
            target_chapter_id=ch_id,
            target_chapter_name=learning_scope.chapter_name,
            target_depth=learning_scope.target_depth,
            depth_rationale="基于学习者画像自动分配",
            lecture_notes=LectureNotesHints(),
            practical_guide=PracticalGuideHints(),
            test_questions=TestQuestionsHints(),
        )


def _build_prior_chapters(kg: KnowledgeGraph, learner: Learner) -> List[PriorChapter]:
    """从学习者真实记录聚合前序章节；没有记录的章节不输出历史。"""
    result: List[PriorChapter] = []
    for chapter in kg.chapters:
        if chapter.chapter_order >= 3:
            continue
        kp_ids = {chapter.primary_kp_id, *chapter.co_requisite_kp_ids, *chapter.predecessor_kp_ids}
        records = [t for t in learner.test_records if t.knowledge_point_id in kp_ids]
        interactions = [i for i in learner.interaction_records if i.knowledge_point_id in kp_ids]
        if not records and not interactions:
            continue
        correct = sum(1 for t in records if t.is_correct)
        accuracy = correct / len(records) if records else 0.0
        latest = max((t.timestamp for t in records), default=None)
        result.append(PriorChapter(
            chapter_id=chapter.chapter_id,
            chapter_name=chapter.chapter_name,
            accuracy=round(accuracy, 3),
            time_spent_hours=round(sum(t.time_spent for t in records) / 3600 + sum(i.duration for i in interactions) / 3600, 2),
            depth_assigned="review" if accuracy >= 0.6 else "entry",
            kps_covered=sorted({t.knowledge_point_id for t in records} | {i.knowledge_point_id for i in interactions}),
            error_patterns_observed=sorted({t.error_pattern for t in records if not t.is_correct and t.error_pattern}),
            completed_at=latest.strftime("%Y-%m-%dT%H:%M:%SZ") if latest else None,
            conclusion="已有真实记录，按当前表现安排复习" if records else "仅有交互记录，尚无测试结论",
        ))
    return result


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

    # 错误模式
    if error_patterns.primary_weakness:
        evidence.append(EvidenceRecord(
            claim=f"主要错误模式={error_patterns.primary_weakness}({error_patterns.primary_weakness_ratio:.0%})",
            source="answer_history",
            detail=f"{error_patterns.total_questions}题中{error_patterns.total_wrong}道错题自动分类，来源为答题记录中的错误模式字段或默认分类",
            confidence=error_patterns.classification_confidence,
        ))

    # 编程能力
    sa = learner.self_assessment
    programming_level = _extract_programming_level(sa)
    evidence.append(EvidenceRecord(
        claim=f"编程能力={programming_level}",
        source="self_assessment",
        detail=f"自填问卷: 实践领域 Python 编程自评「{programming_level}」",
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

    # 五维领域自评
    domain_hints = _self_assessed_domain_hints(sa)
    if domain_hints:
        hint_str = "，".join(
            f"{d}={h['level']}({h['mean']:.2f})" for d, h in domain_hints.items()
        )
        total_courses = sum(len(da.courses) for da in sa.domain_assessments) if sa and sa.domain_assessments else 0
        evidence.append(EvidenceRecord(
            claim=f"五维领域自评结论: {hint_str}",
            source="self_assessment",
            detail=f"自填问卷五维领域自评，共 {len(sa.domain_assessments)} 个领域 {total_courses} 门课程",
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
    chapter_name: str,
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

    sa_hints = _self_assessed_domain_hints(learner.self_assessment)
    sa_sentence = ""
    if sa_hints:
        sa_sentence = "自评：" + "，".join(f"{d}{h['level']}" for d, h in sa_hints.items()) + "。"

    short = (
        f"{learner.name}({learner.education.level}{learner.education.major}) — "
        f"θ={global_theta:.2f} {level_cn} — "
        f"当前学习{chapter_name} — "
        f"主要错误模式: {primary_err or '暂无记录'}({primary_err_ratio:.0%})"
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

    profile_confidence = f"基于{error_patterns.total_questions}道测试题、{len(learner.interaction_records)}条交互记录和问卷信息；数据越充分置信度越高。"

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
    learning_scope = _build_learning_scope(kg, current_chapter_id)
    knowledge_mastery = _build_knowledge_mastery(
        kg, mastery_map, theta_map, test_count_map, confidence_map, status_map,
        global_theta, overall_accuracy,
    )
    ability_level = _build_ability_level(global_theta, mastery_map, domain_mastery)
    learning_preferences = _build_learning_preferences(
        learner.test_records, learner.interaction_records, learner.self_assessment
    )
    depth_labels = _build_depth_labels(kg, mastery_map)
    resource_hints = _build_resource_hints(kg, learning_scope, error_patterns, mastery_map)
    prior_chapters = _build_prior_chapters(kg, learner)
    evidence = _build_evidence(global_theta, mastery_map, error_patterns, gaps, learner)
    diagnosis_summary = _build_diagnosis_summary(
        learner, global_theta, _ability_level_str(global_theta), domain_mastery, gaps, error_patterns, learning_scope.chapter_name,
    )

    # 9. 组装 learner 信息
    sa = learner.self_assessment
    learner_info = {
        "name": learner.name,
        "education": learner.education.model_dump() if learner.education else {},
        "projects": [p.model_dump() for p in sa.projects] if sa and sa.projects else [],
        "domain_assessments": [d.model_dump() for d in sa.domain_assessments] if sa and sa.domain_assessments else [],
        "self_assessment": sa.model_dump() if sa else {
            "learning_goal": "",
            "weekly_hours": 5,
            "domain_assessments": [],
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
            "next_suggested_diagnosis": "ch03_cnn完成后（预计2026-08-08）",
        },
    )
