"""学习者画像构建 — 聚合为 0803 对齐的完整 LearnerProfile

学情诊断Agent的核心输出模块 (v2.1):
输入: Learner + KnowledgeGraph
输出: 0803 结构 LearnerProfile (14个顶层字段)
"""

from __future__ import annotations
from datetime import datetime
from typing import Dict, List, Optional

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
# 0825 最终版：统一三档自评（未学过/基本了解/熟练掌握），兼容旧版五档字符串（上传数据/示例仍可解析）
_COURSE_LEVEL_SCORE = {
    # 新版三档
    "未学过": 0.0,
    "基本了解": 0.45,
    "熟练掌握": 0.9,
    # 旧版五档（兼容保留，避免旧JSON/mock数据失败）
    "入门": 0.35,
    "基础": 0.60,
    "熟练": 0.80,
    "精通": 1.00,
}


def _self_assessed_domain_hints(sa) -> Dict[str, dict]:
    """把五维领域自评映射为领域级结论

    输入: sa.domain_assessments (数学基础/机器学习基础/深度学习/优化算法/实践应用)
    输出: {领域名: {mean, level, n_courses}}
    0825 更新: 兼容两种模式（模式1知识点细化/模式2整体自评合成），过滤_synthetic标记课程仅保留1次权重
    """
    if not sa or not sa.domain_assessments:
        return {}

    hints: Dict[str, dict] = {}
    for da in sa.domain_assessments:
        if not da.courses:
            continue
        # 模式2(guided_questions)下 courses 里只有 1 条 _synthetic 整体自评；
        # 模式1(knowledge_points)下有多条真实 kp 自评，按数量正常平均即可
        scores = [_COURSE_LEVEL_SCORE.get(c.level, 0.0) for c in da.courses]
        if not scores:
            continue
        mean = sum(scores) / len(scores)
        level = "强" if mean >= 0.70 else "中" if mean >= 0.40 else "弱"
        hints[da.domain] = {"mean": round(mean, 2), "level": level, "n_courses": len(scores)}
    return hints


def _self_assessed_kp_priors(sa) -> Dict[str, dict]:
    """【0825新增】模式1（knowledge_points）下，利用细化到kp_id的自评生成知识点级先验掌握度

    输入: sa.domain_assessments（其中部分 course.kp_id 绑定到了教学点）
    输出: {kp_id: {"mastery": float, "level": str, "name": str, "confidence": float}}
    """
    priors: Dict[str, dict] = {}
    if not sa or not sa.domain_assessments:
        return priors
    # 同 kp_id 可能出现多次（多个知识点名映射到同一个kp_id，例如"矩阵乘法"和"特征值"都属于kp_004）
    # 聚合方式：按 kp_id 分组取均值，置信度随条目数递增
    grouped: Dict[str, List[dict]] = {}
    for da in sa.domain_assessments:
        for c in da.courses:
            if not c.kp_id:
                continue
            s = _COURSE_LEVEL_SCORE.get(c.level, 0.0)
            grouped.setdefault(c.kp_id, []).append({"mastery": s, "level": c.level, "name": c.name})
    for kp_id, items in grouped.items():
        if not items:
            continue
        avg_m = sum(x["mastery"] for x in items) / len(items)
        # 自评置信度：条目越多越可信，最高0.65；最少1条时0.35（比完全未探索的0.20高一些）
        conf = min(0.35 + 0.05 * len(items), 0.65)
        # 选第一条出现的name作为代表名（都隶属于同一kp_id，语义相近）
        priors[kp_id] = {
            "mastery": round(avg_m, 4),
            "level": items[0]["level"],
            "name": items[0]["name"],
            "n_items": len(items),
            "confidence": round(conf, 2),
        }
    return priors


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

def _build_learning_scope(kg: KnowledgeGraph, current_chapter_id: str = "ch03_cnn", mastery_map: Dict[str, float] = None) -> LearningScope:
    """构建章节级学习范围"""
    ch = kg.get_chapter(current_chapter_id)
    if not ch:
        raise ValueError(f"章节 {current_chapter_id} 不存在")

    primary_kp = kg.get(ch.primary_kp_id)
    successors = kg.get_chapter_successors(current_chapter_id)

    # 动态确定目标深度：基于主知识点掌握度
    primary_mastery = (mastery_map or {}).get(ch.primary_kp_id, 0.0)
    if primary_mastery >= 0.75:
        target_depth = "回顾"
    elif primary_mastery >= 0.40:
        target_depth = "进阶"
    else:
        target_depth = "入门"

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
        path_note="学习路径一次性生成，学习过程中路径不变，只更新画像。若当前章节正确率<60%，下一章节自动降为入门层。",
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
    kp_priors: Optional[Dict[str, dict]] = None,
) -> KnowledgeMastery:
    """构建知识点掌握度矩阵
    0825 更新: 新增 kp_priors 参数 — 模式1自评细化到kp_id的先验掌握度，
    用于未测评节点（test_count=0）时输出自评推断值而不是 None，提升画像信息量。
    """
    kp_priors = kp_priors or {}

    # 分领域汇总
    domain_summary: Dict[str, DomainSummaryItem] = {}
    domain_scores: Dict[str, List[float]] = {}
    domain_counts: Dict[str, int] = {}
    for kp in kg.points:
        # 计算每个 kp 的展示用 mastery（IRT结果 or 自评先验 or 0）
        tc = test_count_map.get(kp.id, 0)
        if tc > 0:
            show_m = mastery_map.get(kp.id, 0.0)
        elif kp.id in kp_priors:
            show_m = kp_priors[kp.id]["mastery"]
        else:
            show_m = mastery_map.get(kp.id, 0.0)
        domain_scores.setdefault(kp.domain, []).append(show_m)
        domain_counts[kp.domain] = domain_counts.get(kp.domain, 0) + 1
    for domain, scores in domain_scores.items():
        domain_summary[domain] = DomainSummaryItem(
            mean_mastery=round(sum(scores) / len(scores), 3) if scores else 0.0,
            kps_covered=domain_counts.get(domain, 0),
        )

    # 各知识点
    points: Dict[str, KpMasteryPoint] = {}
    # 为了status_distribution正确，也要更新status展示值
    display_status_map = dict(status_map)

    for kp in kg.points:
        tc = test_count_map.get(kp.id, 0)
        st = status_map.get(kp.id, "unexplored")
        prior = kp_priors.get(kp.id)
        # 未测评但有自评先验：展示自评mastery，并根据mastery给出status，置信度使用自评置信度
        if tc == 0 and prior is not None:
            p_m = prior["mastery"]
            p_conf = prior["confidence"]
            p_st = (
                "mastered" if p_m >= 0.75
                else "familiar" if p_m >= 0.60
                else "partial" if p_m >= 0.40
                else "weak" if p_m >= 0.25
                else "not_learned"
            )
            display_status_map[kp.id] = p_st
            # theta_kp 也根据自评mastery反推一个近似值（IRT sigmoid逆函数大致映射）
            # 近似: mastery≈0.5→theta≈0; mastery≈0.2→theta≈-0.8; mastery≈0.8→theta≈+0.8
            approx_theta = round((p_m - 0.5) * 2.0, 2)
            points[kp.id] = KpMasteryPoint(
                name=kp.name,
                domain=kp.domain,
                mastery=round(p_m, 4),
                status=p_st,
                theta_kp=approx_theta,
                test_count=0,
                confidence=p_conf,
            )
        elif tc == 0:
            # P0-5: 完全未测评节点（无自评）输出 mastery=None, status="unexplored"
            points[kp.id] = KpMasteryPoint(
                name=kp.name,
                domain=kp.domain,
                mastery=None,
                status="unexplored",
                theta_kp=round(theta_map.get(kp.id, 0.0), 2),
                test_count=0,
                confidence=confidence_map.get(kp.id, 0.20),
            )
        else:
            points[kp.id] = KpMasteryPoint(
                name=kp.name,
                domain=kp.domain,
                mastery=round(mastery_map.get(kp.id, 0.0), 4),
                status=st,
                theta_kp=round(theta_map.get(kp.id, 0.0), 2),
                test_count=tc,
                confidence=confidence_map.get(kp.id, 0.0),
            )

    return KnowledgeMastery(
        global_theta=round(global_theta, 2),
        ability_level=_ability_level_str(global_theta),
        overall_accuracy=round(overall_accuracy, 3),
        confidence_note=(
            f"全局θ基于{sum(test_count_map.values())}题MLE估计，学历先验已纳入，L2正则λ=0.5。"
            + (f"模式1自评先验覆盖{len(kp_priors)}个知识点（test_count=0节点以自评显示，置信度0.35~0.65）。" if kp_priors else "")
        ),
        domain_summary=domain_summary,
        points=points,
        status_distribution=_compute_status_distribution(display_status_map),
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
    weekly_hours = int(getattr(sa, "weekly_hours", 10) or 10)

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


def _build_depth_labels(kg: KnowledgeGraph, mastery_map: Dict[str, float], test_count_map: Dict[str, int] = None) -> List[DepthLabel]:
    """根据掌握度自动分配深度标签"""
    test_count_map = test_count_map or {}
    labels: List[DepthLabel] = []
    for kp in kg.points:
        tc = test_count_map.get(kp.id, 0)
        m = mastery_map.get(kp.id, 0.0)
        if tc == 0:
            labels.append(DepthLabel(kp_id=kp.id, kp_name=kp.name, depth="entry", rationale="未测评，默认入门讲授"))
            continue
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
    depth_labels: List[DepthLabel],
    error_patterns: ErrorPatterns,
    mastery_map: Dict[str, float],
    knowledge_gaps: List[KnowledgeGap],
) -> ResourceGenerationHints:
    """构建章节级资源生成提示 — 动态生成，无硬编码章节特例

    依据 learning_scope.primary_kp_id、当前章节知识点集合、depth_labels、
    knowledge_gaps、error_patterns 和学习偏好动态生成资源提示。
    每个章节均生成同一结构的 lecture_notes / practical_guide / test_questions。
    """
    ch = kg.get_chapter(learning_scope.chapter_id)
    ch_id = learning_scope.chapter_id

    # 资源提示需要覆盖完整章节范围（主知识点 + 前驱 + 共修）。
    chapter_kp_ids: List[str] = []
    if ch:
        chapter_kp_ids = list(
            {ch.primary_kp_id, *ch.predecessor_kp_ids, *ch.co_requisite_kp_ids}
        )
    chapter_kps = [kg.get(kid) for kid in chapter_kp_ids if kg.get(kid)]
    chapter_kps = [kp for kp in chapter_kps if kp is not None]

    # 从 depth_labels 获取主知识点的深度
    primary_depth = "entry"
    primary_rationale = ""
    for dl in depth_labels:
        if dl.kp_id == learning_scope.primary_kp_id:
            primary_depth = dl.depth
            primary_rationale = dl.rationale
            break

    # depth 映射为中文
    DEPTH_CN = {"skip": "跳过", "review": "回顾", "entry": "入门", "advanced": "进阶"}
    target_depth_cn = DEPTH_CN.get(primary_depth, "入门")

    # 计算 ML 基础均值用于 depth_rationale
    ml_domains = ["数学基础", "机器学习基础"]
    ml_kps = [kp for kp in kg.points if kp.domain in ml_domains]
    ml_mean_val = sum(mastery_map.get(kp.id, 0.0) for kp in ml_kps) / max(1, len(ml_kps))

    depth_rationale = (
        f"主知识点「{learning_scope.primary_kp_name}」深度={target_depth_cn}（{primary_rationale}）。"
        f"学习者ML基础均值{ml_mean_val:.2f}，"
        f"{'有能力接受原理级讲解' if ml_mean_val > 0.45 else '建议从基础讲起'}。"
    )

    # 该章节的盲区
    chapter_gaps = [g for g in knowledge_gaps if g.kp_id in chapter_kp_ids]
    gap_kp_names = [g.kp_name for g in chapter_gaps[:5]]

    # 错误模式相关
    primary_err = error_patterns.primary_weakness if error_patterns.primary_weakness else ""
    error_mitigations: List[str] = []
    if primary_err:
        error_mitigations.append(f"概念理解题：设置2个以上易混淆干扰项（回应'{primary_err}'弱点）")
    if "计算错误" in [i.category for i in error_patterns.items]:
        error_mitigations.append("计算推导题：要求写出中间步骤")
    if "逻辑跳跃" in [i.category for i in error_patterns.items]:
        error_mitigations.append("综合分析题：要求列出推理步骤，不可跳步")
    if "忽略条件" in [i.category for i in error_patterns.items]:
        error_mitigations.append("题干中用加粗突出约束条件")

    # 讲义 must_include：从章节知识点描述动态生成
    lecture_must: List[str] = []
    for kp in chapter_kps[:6]:
        lecture_must.append(f"{kp.name}：{kp.description or '核心概念与原理'}")
    if gap_kp_names:
        lecture_must.append(f"重点关注薄弱知识点：{', '.join(gap_kp_names)}")

    lecture_avoid: List[str] = []
    if primary_err:
        lecture_avoid.append(f"避免纯代码堆砌而无原理铺垫（回应'{primary_err}'弱点）")

    # 对比表：基于同领域知识点
    comparison_tables: List[str] = []
    domains_in_chapter = set(kp.domain for kp in chapter_kps)
    for d in domains_in_chapter:
        d_kps = [kp for kp in chapter_kps if kp.domain == d]
        if len(d_kps) >= 2:
            comparison_tables.append(f"{d}领域内各知识点的对比（{', '.join(k.name for k in d_kps[:4])}）")

    # 实操指南
    practical_must: List[str] = []
    for kp in chapter_kps[:4]:
        practical_must.append(f"{kp.name}的代码实现与运行验证")
    practical_must.append("训练循环含loss/accuracy曲线可视化代码")
    practical_must.append("常见Bug调试指南")

    # 测试题
    n_kps = len(chapter_kps)
    total_questions = max(8, min(12, n_kps * 2))
    n_easy = max(2, total_questions // 4)
    n_hard = max(2, total_questions // 4)
    n_medium = total_questions - n_easy - n_hard

    test_must_cover: List[str] = []
    for kp in chapter_kps[:5]:
        test_must_cover.append(f"{kp.name}相关概念与计算")

    return ResourceGenerationHints(
        scope="chapter",
        scope_note=f"以下提示针对完整章节 {ch_id}（{learning_scope.chapter_name}/{target_depth_cn}层），"
                   f"资源生成Agent需据此生成该章的全部3类资源",
        target_chapter_id=ch_id,
        target_chapter_name=learning_scope.chapter_name,
        target_depth=target_depth_cn,
        depth_rationale=depth_rationale,
        lecture_notes=LectureNotesHints(
            must_include=lecture_must,
            avoid=lecture_avoid,
            comparison_tables=comparison_tables,
            error_pattern_attention=f"注意针对'{primary_err}'错误模式设计对比讲解" if primary_err else "",
            estimated_pages=f"{max(8, n_kps * 2)}-{max(12, n_kps * 3)}页（含图）",
        ),
        practical_guide=PracticalGuideHints(
            must_include=practical_must,
            code_style="Jupyter Notebook分段式，每段不超过30行，Markdown + Code交替，函数/类有完整docstring",
            dataset="根据章节内容选择合适的数据集",
            framework="PyTorch 2.x",
            estimated_cells=f"{max(10, n_kps * 2)}-{max(16, n_kps * 3)} cells",
        ),
        test_questions=TestQuestionsHints(
            total=total_questions,
            distribution={
                "概念理解（选择题/判断题）": max(2, total_questions // 3),
                "计算推导": max(2, total_questions // 4),
                "代码填空": max(1, total_questions // 4),
                "综合分析": max(1, total_questions // 5),
            },
            difficulty={
                "easy": {"count": n_easy, "target_accuracy": ">80%"},
                "medium": {"count": n_medium, "target_accuracy": "60-80%"},
                "hard": {"count": n_hard, "target_accuracy": "40-60%"},
            },
            target_overall_accuracy_range=[0.60, 0.85],
            error_pattern_mitigations=error_mitigations if error_mitigations else ["根据学习者错误模式调整题目设计"],
            must_cover=test_must_cover,
            estimated_time_minutes=max(30, total_questions * 4),
        ),
    )


def _build_prior_chapters(
    learner: Learner,
    kg: KnowledgeGraph,
    current_chapter_id: str,
) -> List[PriorChapter]:
    """构建前序章节表现 — 基于真实测试记录和交互记录计算

    无测试记录的章节不生成历史条目。
    accuracy / time_spent / error_patterns 均由当前学习者数据聚合获得。
    """
    # 确定当前章节在路径中的位置
    current_ch = kg.get_chapter(current_chapter_id)
    if not current_ch:
        return []

    prior_chapters: List[PriorChapter] = []
    for ch in kg.chapters:
        if ch.chapter_order >= current_ch.chapter_order:
            break

        # 仅以章节自身的主知识点和共需知识点归属学习记录。
        # predecessor_kp_ids 是路径约束，不能据此推断学生学过本章。
        chapter_kp_ids = list({ch.primary_kp_id, *ch.co_requisite_kp_ids})

        # 筛选属于该章节知识点的测试记录
        chapter_tests = [
            t for t in learner.test_records
            if t.knowledge_point_id in chapter_kp_ids
        ]
        # 筛选交互记录
        chapter_interactions = [
            i for i in learner.interaction_records
            if i.knowledge_point_id in chapter_kp_ids
        ]

        # 无记录则跳过该章节
        if not chapter_tests and not chapter_interactions:
            continue

        # 计算准确率
        if chapter_tests:
            correct = sum(1 for t in chapter_tests if t.is_correct)
            accuracy = round(correct / len(chapter_tests), 3)
        else:
            accuracy = 0.0

        # 计算用时（小时）
        total_time_seconds = sum(t.time_spent for t in chapter_tests)
        total_time_seconds += sum(i.duration for i in chapter_interactions)
        time_spent_hours = round(total_time_seconds / 3600.0, 2)

        # 聚合错误模式
        error_cats: List[str] = []
        for t in chapter_tests:
            if not t.is_correct and t.error_pattern:
                if t.error_pattern not in error_cats:
                    error_cats.append(t.error_pattern)

        # 覆盖的知识点
        tested_kps = list(set(t.knowledge_point_id for t in chapter_tests))

        # 历史记录只证明发生过学习活动；未接入章节完成事件，不能声明章节已完成。
        completed_at = None

        # 深度判定
        if accuracy >= 0.75:
            depth_assigned = "review"
            conclusion = f"准确率{accuracy:.0%}，掌握良好，已做回顾性验证"
        elif accuracy > 0.50:
            depth_assigned = "advanced"
            conclusion = f"准确率{accuracy:.0%}，基本掌握，需巩固提升"
        else:
            depth_assigned = "entry"
            conclusion = f"准确率{accuracy:.0%}，掌握不足，建议重新学习"

        prior_chapters.append(PriorChapter(
            chapter_id=ch.chapter_id,
            chapter_name=ch.chapter_name,
            accuracy=accuracy,
            time_spent_hours=time_spent_hours,
            depth_assigned=depth_assigned,
            kps_covered=tested_kps,
            error_patterns_observed=error_cats,
            completed_at=completed_at,
            conclusion=conclusion,
        ))

    return prior_chapters


def _build_evidence(
    global_theta: float,
    mastery_map: Dict[str, float],
    error_patterns: ErrorPatterns,
    gaps: List[KnowledgeGap],
    learner: Learner,
    kp_priors: Optional[Dict[str, dict]] = None,
) -> List[EvidenceRecord]:
    """构建证据溯源
    0825 更新: 新增 kp_priors 参数，补充模式1/模式2自评来源的证据记录
    """
    evidence: List[EvidenceRecord] = []
    kp_priors = kp_priors or {}

    # 动态统计数据
    total_tests = error_patterns.total_questions
    tested_kps = len(set(t.knowledge_point_id for t in learner.test_records)) if learner.test_records else 0
    prior_theta_val = irt.education_prior_theta(learner.education.level)

    # 全局θ
    evidence.append(EvidenceRecord(
        claim=f"全局能力θ={global_theta:.2f}, ability_level={_ability_level_str(global_theta)}",
        source="irt_estimation",
        detail=f"累计{total_tests}道题(覆盖{tested_kps}个知识点)的IRT-MLE跨知识点估计，学历先验θ={prior_theta_val}({learner.education.level})，L2正则λ=0.5",
        confidence=0.90 if total_tests >= 5 else 0.70,
    ))

    # 0825 新增：模式1 知识点细化自评先验覆盖说明
    if kp_priors:
        # 按领域分组展示覆盖数
        dom_cover: Dict[str, int] = {}
        for kp_id, info in kp_priors.items():
            # 通过kp_id推断领域（取name第一个字段作为代表，简化处理）
            # 更稳妥的方式：以 kp_id 聚合，简单记录覆盖量
            dom_cover["合计"] = dom_cover.get("合计", 0) + 1
        strongest_id, strongest = max(kp_priors.items(), key=lambda x: x[1]["mastery"])
        weakest_id, weakest = min(kp_priors.items(), key=lambda x: x[1]["mastery"])
        evidence.append(EvidenceRecord(
            claim=f"模式1细化自评覆盖{len(kp_priors)}个教学点（未测节点以自评值展示），最高「{strongest['name']}={strongest['level']}」，最低「{weakest['name']}={weakest['level']}」",
            source="self_assessment",
            detail=f"自填问卷：数学基础/深度学习/优化算法 三领域采用知识点掌握度选择模式（模式1），"
                   f"细化到{len(kp_priors)}个kp_id，同kp_id下多条自评取均值，置信度0.35~0.65（条目不相关）。"
                   f"最高自评kp={strongest_id} mastery≈{strongest['mastery']:.2f}，最弱kp={weakest_id} mastery≈{weakest['mastery']:.2f}",
            confidence=0.60,
        ))

    # 0825 新增：模式2 引导问答覆盖记录（ML基础/实践应用）
    sa = learner.self_assessment
    if sa and sa.domain_assessments:
        guided_domains = []
        for da in sa.domain_assessments:
            if getattr(da, "mode", None) == "guided_questions" and da.guided_answers:
                answered = sum(1 for v in da.guided_answers.values() if v and str(v).strip())
                guided_domains.append((da.domain, answered, len(da.guided_answers)))
        if guided_domains:
            summary = "，".join(f"{d}：{a}/{t}题已作答" for d, a, t in guided_domains)
            evidence.append(EvidenceRecord(
                claim=f"模式2引导问答已收集：{summary}",
                source="self_assessment_and_interaction",
                detail=f"自填问卷：机器学习基础/实践应用 两领域采用文字引导模式（模式2），"
                       f"每领域配套4道引导问题，鼓励学习者开放式作答。"
                       f"详细问答原文保存在 learner.self_assessment.domain_assessments[*].guided_answers 与 note 字段中。",
                confidence=0.55,  # 文字回答主观度稍高，置信度低于知识点选择
            ))

    # 错误模式 — 基于真实答题记录自动分类
    if error_patterns.primary_weakness:
        evidence.append(EvidenceRecord(
            claim=f"主要错误模式={error_patterns.primary_weakness}({error_patterns.primary_weakness_ratio:.0%})",
            source="answer_history",
            detail=f"{error_patterns.total_questions}题中{error_patterns.total_wrong}道错题自动分类，分类置信度={error_patterns.classification_confidence}",
            confidence=error_patterns.classification_confidence,
        ))

    # 编程能力
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
            detail=f"自填问卷五维领域自评，共 {len(sa.domain_assessments)} 个领域 {total_courses} 门课程。"
                   f"模式1（知识点细化）和模式2（引导问答）领域的得分逻辑已在 detail 中分别说明。",
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

    sa_hints = _self_assessed_domain_hints(learner.self_assessment)
    sa_sentence = ""
    if sa_hints:
        sa_sentence = "自评：" + "，".join(f"{d}{h['level']}" for d, h in sa_hints.items()) + "。"

    short = (
        f"{learner.name}({learner.education.level}{learner.education.major}) — "
        f"θ={global_theta:.2f} {level_cn} — "
        f"最强领域: {strong_name}({strong_val:.0%})，最弱领域: {weak_name}({weak_val:.0%}) — "
        f"主要错误模式: {primary_err}({primary_err_ratio:.0%})"
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

    profile_confidence = f"中等。IRT估计基于{sum(1 for t in learner.test_records) if learner.test_records else 0}条测试记录，自填问卷部分0.70-0.75。建议完成当前章节学习后重新诊断。"

    return DiagnosisSummary(short=short, full=full, profile_confidence=profile_confidence)


# ============================================================
# 主入口: 构建完整画像
# ============================================================

def build_profile(
    learner: Learner,
    kg: KnowledgeGraph,
    current_chapter_id: str = "ch03_cnn",
) -> LearnerProfile:
    """构建完整学习者画像 — 对齐 0803 结构
    0825 更新: 
    - 加入知识点级自评先验（模式1 knowledge_points 的kp_id映射）
    - 未测评节点(test_count=0)如有自评先验则以自评mastery显示，status/unexplored判定也相应放宽
    - evidence 中新增模式1/模式2来源说明
    """

    if not kg.get_chapter(current_chapter_id):
        raise ValueError(f"章节 {current_chapter_id} 不存在")

    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    sa = learner.self_assessment

    # 1. 学历先验θ
    prior_theta = irt.education_prior_theta(learner.education.level)

    # 1b. 【0825 新增】模式1的知识点级自评先验：从自填问卷domain_assessments中提取kp_id→mastery映射
    kp_priors = _self_assessed_kp_priors(sa)

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

    # 5. 分领域掌握度（0825更新：对test_count=0但有kp_priors覆盖的节点取自评mastery参与领域均值）
    domain_mastery: Dict[str, float] = {}
    for domain in kg.domains():
        kp_ids = kg.domain_kp_ids(domain)
        domain_scores = []
        for kid in kp_ids:
            tc = test_count_map.get(kid, 0)
            if tc > 0:
                domain_scores.append(mastery_map.get(kid, 0.0))
            elif kid in kp_priors:
                domain_scores.append(kp_priors[kid]["mastery"])
            else:
                domain_scores.append(mastery_map.get(kid, 0.0))
        domain_mastery[domain] = round(sum(domain_scores) / len(domain_scores), 3) if domain_scores else 0.0

    # 6. 知识盲区分析
    gaps = gap_analyzer.analyze_gaps(
        kg, mastery_map, learner.test_records, learner.interaction_records, test_count_map,
    )

    # 7. 错误模式分类
    error_patterns = gap_analyzer.classify_error_patterns(
        learner.test_records, mastery_map,
    )

    # 8. 子模块构建 (0825更新：kp_priors 传递给 knowledge_mastery + evidence)
    depth_labels = _build_depth_labels(kg, mastery_map, test_count_map)
    learning_scope = _build_learning_scope(kg, current_chapter_id, mastery_map)
    knowledge_mastery = _build_knowledge_mastery(
        kg, mastery_map, theta_map, test_count_map, confidence_map, status_map,
        global_theta, overall_accuracy,
        kp_priors=kp_priors,
    )
    ability_level = _build_ability_level(global_theta, mastery_map, domain_mastery)
    learning_preferences = _build_learning_preferences(
        learner.test_records, learner.interaction_records, learner.self_assessment
    )
    resource_hints = _build_resource_hints(kg, learning_scope, depth_labels, error_patterns, mastery_map, gaps)
    prior_chapters = _build_prior_chapters(learner, kg, current_chapter_id)
    evidence = _build_evidence(global_theta, mastery_map, error_patterns, gaps, learner, kp_priors=kp_priors)
    diagnosis_summary = _build_diagnosis_summary(
        learner, global_theta, _ability_level_str(global_theta), domain_mastery, gaps, error_patterns,
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

    # 获取图谱版本信息
    kg_version = getattr(kg, 'KG_VERSION', 'unknown')
    mapping_version = getattr(kg, 'MAPPING_VERSION', 'unknown')

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
            "next_suggested_diagnosis": f"完成{learning_scope.chapter_name}学习后重新诊断",
            "kg_version": kg_version,
            "mapping_version": mapping_version,
        },
    )
