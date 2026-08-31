<script setup lang="ts">
import { computed, ref } from "vue";
import { ArrowRight, BookOpenCheck, BrainCircuit, CalendarClock, CheckCircle2, ChevronRight, CircleAlert, Filter, RefreshCcw, Save, ShieldCheck, Sparkles, Target, TrendingUp } from "lucide-vue-next";
import { useRouter } from "vue-router";
import ProgressRing from "@/components/ProgressRing.vue";
import MasteryChart from "@/components/MasteryChart.vue";
import AIInsightCard from "@/components/AIInsightCard.vue";
import StateBlocks from "@/components/StateBlocks.vue";
import { useLearnerStore } from "@/stores/learner";
import { useLearningPathStore } from "@/stores/learningPath";
import type { MasteryPoint } from "@/types/learner";

type LearningSort = "weak" | "recent" | "all";
type LearningRow = MasteryPoint & { delta: number | null; isNew: boolean };
const router = useRouter();
const learner = useLearnerStore();
const path = useLearningPathStore();
const learningSort = ref<LearningSort>("weak");
const showAllLearning = ref(false);
const profile = computed(() => learner.profile);
const points = computed(() => Object.values(profile.value?.knowledge_mastery?.points || {}));
const knowledgeMastery = computed(() => profile.value?.knowledge_mastery);
const learningSnapshot = computed(() => learner.snapshot);
const previousSnapshot = computed(() => learner.previousSnapshot);
const learningMastery = computed(() => (learningSnapshot.value?.knowledge_mastery || []).filter((item) => item.assessment_status === "assessed" && typeof item.mastery_score === "number"));
const previousByConcept = computed(() => new Map((previousSnapshot.value?.knowledge_mastery || []).map((item) => [item.concept_id, item])));
const learningRows = computed<LearningRow[]>(() => learningMastery.value.map((item) => {
  const previous = previousByConcept.value.get(item.concept_id);
  return { ...item, delta: previous && typeof previous.mastery_score === "number" ? (item.mastery_score || 0) - previous.mastery_score : null, isNew: !previous };
}));
const learningChanges = computed(() => learningRows.value.filter((item) => item.delta !== null && Math.abs(item.delta || 0) >= .005));
const improvedRows = computed(() => learningChanges.value.filter((item) => (item.delta || 0) > 0));
const declinedRows = computed(() => learningChanges.value.filter((item) => (item.delta || 0) < 0));
const latestLearningUpdate = computed(() => learningMastery.value.reduce<string | null>((latest, item) => item.observed_at && (!latest || item.observed_at > latest) ? item.observed_at : latest, learningSnapshot.value?.generated_at || null));
const learningAverage = computed(() => learningMastery.value.length ? learningMastery.value.reduce((total, item) => total + (item.mastery_score || 0), 0) / learningMastery.value.length : null);
const learningAbilityEntries = computed(() => Object.entries(learningSnapshot.value?.abilities || {}));
const sortedLearningRows = computed(() => {
  const rows = [...learningRows.value];
  if (learningSort.value === "recent") return rows.sort((a, b) => String(b.observed_at || "").localeCompare(String(a.observed_at || "")));
  if (learningSort.value === "all") return rows.sort((a, b) => conceptTitle(a.concept_id).localeCompare(conceptTitle(b.concept_id), "zh-CN"));
  return rows.sort((a, b) => (a.mastery_score || 0) - (b.mastery_score || 0) || a.confidence - b.confidence);
});
const visibleLearningRows = computed(() => showAllLearning.value ? sortedLearningRows.value : sortedLearningRows.value.slice(0, 8));
const reviewRows = computed(() => {
  const overdue = learningRows.value.filter((item) => item.observed_at && (Date.now() - new Date(item.observed_at).getTime()) / 86400000 >= 7);
  return (overdue.length ? overdue : [...learningRows.value].sort((a, b) => (a.mastery_score || 0) - (b.mastery_score || 0) || a.confidence - b.confidence)).slice(0, 3);
});
const recentLearningRows = computed(() => learningRows.value.filter((item) => item.observed_at && new Date(item.observed_at).getTime() >= Date.now() - 7 * 86400000));
const stability = computed(() => {
  const avg = learningRows.value.length ? learningRows.value.reduce((total, item) => total + item.confidence, 0) / learningRows.value.length : 0;
  if (learningRows.value.length >= 8 && avg >= .65) return { label: "证据稳定", tone: "stable", text: "已有多次、跨知识点的测评证据，当前结论可用于调整学习节奏。" };
  if (learningRows.value.length >= 3 && avg >= .35) return { label: "初步可用", tone: "limited", text: "已有部分小测证据；能力等级仍以阶段复诊为准，不会因单次答题跳变。" };
  return { label: "证据仍少", tone: "early", text: "当前结论主要来自少量小测，建议完成本章后再复测一次以提高可靠性。" };
});
const nextAction = computed(() => {
  const node = path.currentNode;
  const item = (node?.concept_id && learningRows.value.find((row) => row.concept_id === node.concept_id)) || [...learningRows.value].sort((a, b) => (a.mastery_score || 0) - (b.mastery_score || 0) || a.confidence - b.confidence)[0];
  if (!item) return null;
  const error = (learningSnapshot.value?.error_patterns || []).find((pattern) => pattern.concept_ids.includes(item.concept_id));
  return { ...item, title: node?.title || node?.name || conceptTitle(item.concept_id), errorText: error ? errorLabel(error.code) : "当前掌握度或证据强度仍需要巩固", hasReadyResource: Boolean(path.run && node) };
});
const domainSummary = computed(() => knowledgeMastery.value?.domain_summary || {});
const domainValues = computed(() => Object.fromEntries(Object.entries(domainSummary.value).filter(([, value]) => typeof value.mean_mastery === "number").map(([key, value]) => [key, value.mean_mastery as number])));
const abilities = computed(() => Object.entries(profile.value?.ability_level?.sub_dimensions || {}));
const abilityLabels: Record<string, string> = { theoretical_understanding: "理论理解", coding_ability: "代码能力", mathematical_foundation: "数学基础", problem_solving: "问题解决" };
const outcomeReport = computed(() => learner.outcomeReport);
const notableKpChanges = computed(() => (outcomeReport.value?.kp_changes || []).filter((change) => change.category !== "不变").sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).slice(0, 8));
async function onSaveBaseline() { await learner.saveBaseline(); }
async function onVerifyOutcome() { await learner.verifyOutcome(); }
function goToNextAction() { router.push(nextAction.value?.hasReadyResource ? "/resources" : "/learning-path"); }
function pct(value?: number | null) { return typeof value === "number" ? `${Math.round(value * 100)}%` : "-"; }
function pctDelta(delta?: number | null) { return delta === null || delta === undefined ? "首次记录" : `${delta > 0 ? "+" : ""}${Math.round(delta * 100)}%`; }
function deltaClass(delta?: number | null) { return !delta ? "delta-flat" : delta > 0 ? "delta-up" : "delta-down"; }
function num(value?: number, digits = 2) { return typeof value === "number" ? value.toFixed(digits) : "-"; }
function evidenceLabel(level?: string) { return ({ preliminary: "初步证据", limited: "证据有限", stable: "证据稳定", self_report: "逐点自评", none: "尚未测评" } as Record<string, string>)[level || "none"] || "尚未测评"; }
function errorLabel(code: string) { return ({ concept_confusion: "概念辨析容易混淆", logic_gap: "推理步骤存在缺口", calculation_error: "计算过程需要复盘", missed_condition: "题目条件容易遗漏" } as Record<string, string>)[code] || "需要通过复测确认掌握情况"; }
function conceptTitle(conceptId: string) {
  const names: Record<string, string> = { scalar: "标量", vector: "向量", matrix: "矩阵", tensor: "张量", "matrix-operations": "矩阵运算", "matrix-multiplication": "矩阵乘法", norm: "范数", determinant: "行列式", "chain-rule": "链式法则", "derivative-gradient": "导数与梯度", "probability-distribution": "概率分布", "bayes-theorem": "贝叶斯定理", "random-variable": "随机变量", overfitting: "过拟合", underfitting: "欠拟合", "cross-validation": "交叉验证", "random-forest": "随机森林", "linear-regression": "线性回归", "logistic-regression": "逻辑回归", "feature-label": "特征与标签", "hyperparameter-tuning": "超参数调优", convolution: "卷积运算", pooling: "池化", embedding: "嵌入表示", "gradient-descent": "梯度下降", relu: "ReLU", adam: "Adam", backpropagation: "反向传播", "learning-rate": "学习率", regularization: "正则化", attention: "注意力机制", transformer: "Transformer", tokenization: "分词", prompting: "提示工程", "retrieval-augmented-generation": "检索增强生成", "hybrid-retrieval": "混合检索", reranking: "重排序" };
  const key = conceptId.split(".").at(-1) || conceptId;
  return names[key] || key.replaceAll("-", " ");
}
function verdictTone(verdict: string) { return verdict.includes("显著") ? "is-up" : verdict.includes("退步") ? "is-down" : verdict.includes("一般") ? "" : "is-flat"; }
function categoryPill(category: string) { return category.includes("显著") ? "status-pill status-pill-success" : category.includes("提升") ? "status-pill" : category.includes("下降") ? "status-pill status-pill-danger" : "status-pill status-pill-warning"; }
</script>

<template>
  <div class="page-stack">
    <div class="page-intro"><div><span class="eyebrow">LEARNER PROFILE</span><h2>你的学习画像</h2><p>每次小测更新的是可追溯的学习证据，而不是一次答题定下的标签。</p></div><button class="button button-primary" @click="router.push('/learning-path')">查看个性化路径 <ArrowRight :size="17" /></button></div>
    <div v-if="!profile && !learningSnapshot"><section class="panel"><StateBlocks type="empty" title="还没有学习画像" message="完成学情诊断后，这里会展示掌握度、能力维度和学习偏好。" /><button class="button button-primary" @click="router.push('/diagnosis')">开始诊断</button></section></div>
    <template v-else>
      <section v-if="learningSnapshot" class="panel learning-profile-panel">
        <div class="panel-heading"><div><span class="eyebrow">LIVE LEARNING PROFILE</span><h2>学习后画像</h2><p>小测结果会与前一版快照对比，帮助你判断改变来自哪里。</p></div><span class="status-pill" :class="`profile-stability-${stability.tone}`"><CheckCircle2 :size="13" /> {{ stability.label }}</span></div>
        <div class="learning-profile-summary"><div><strong>{{ learningMastery.length }}</strong><span>累计已测知识点</span></div><div><strong>{{ pct(learningAverage) }}</strong><span>当前已测均值</span></div><div><strong>{{ latestLearningUpdate ? new Date(latestLearningUpdate).toLocaleString('zh-CN', { hour12: false }) : '等待小测' }}</strong><span>最近更新</span></div></div>
        <div class="learning-change-strip"><div><span>本次提升</span><b class="delta-up">{{ improvedRows.length }} 个</b></div><div><span>需要巩固</span><b :class="declinedRows.length ? 'delta-down' : 'delta-flat'">{{ declinedRows.length }} 个</b></div><div><span>首次记录</span><b>{{ learningRows.filter((item) => item.isNew).length }} 个</b></div><p>{{ learningChanges.length ? '前后变化只比较相邻两次学习快照；首次测到的知识点会单独标记。' : '下一次完成小测后，这里会显示与本次快照的逐点变化。' }}</p></div>
        <div v-if="nextAction" class="next-action-card"><div class="next-action-icon"><Sparkles :size="19" /></div><div><span class="eyebrow">NEXT BEST ACTION</span><h3>下一步：{{ nextAction.title }}</h3><p>掌握度 {{ pct(nextAction.mastery_score) }}，置信度 {{ pct(nextAction.confidence) }}。{{ nextAction.errorText }}。</p></div><button class="button button-primary" @click="goToNextAction">{{ nextAction.hasReadyResource ? '继续学习' : '查看路径' }} <ChevronRight :size="16" /></button></div>
        <div class="learning-toolbar"><div class="segmented-control" aria-label="知识点排序"><button v-for="item in [{ key: 'weak', label: '薄弱优先' }, { key: 'recent', label: '最近更新' }, { key: 'all', label: '全部名称' }]" :key="item.key" :class="{ active: learningSort === item.key }" @click="learningSort = item.key as LearningSort"><Filter v-if="item.key === 'weak'" :size="13" />{{ item.label }}</button></div><span>{{ sortedLearningRows.length }} 个已测知识点</span></div>
        <div v-if="visibleLearningRows.length" class="learning-profile-grid"><article v-for="item in visibleLearningRows" :key="item.concept_id" class="mastery-item"><div><strong>{{ conceptTitle(item.concept_id) }}</strong><small>{{ evidenceLabel(item.confidence >= .65 ? 'stable' : item.confidence >= .35 ? 'limited' : 'preliminary') }} · 置信度 {{ pct(item.confidence) }}</small></div><div class="mini-progress"><span :style="{ width: `${(item.mastery_score || 0) * 100}%` }" /></div><div class="mastery-value"><b>{{ pct(item.mastery_score) }}</b><small :class="deltaClass(item.delta)">{{ pctDelta(item.delta) }}</small></div></article></div>
        <button v-if="sortedLearningRows.length > 8" class="button button-secondary compact-button" @click="showAllLearning = !showAllLearning">{{ showAllLearning ? '收起知识点' : `查看全部 ${sortedLearningRows.length} 个知识点` }}</button>
        <div v-if="learningAbilityEntries.length" class="learning-ability-list"><span v-for="[key, value] in learningAbilityEntries" :key="key">{{ abilityLabels[key] || key }} {{ pct(value.score) }}</span></div><div class="evidence-note"><CircleAlert :size="16" /><p>{{ stability.text }}</p></div>
      </section>

      <div v-if="learningSnapshot" class="content-grid content-grid-main"><section class="panel"><div class="panel-heading"><div><span class="eyebrow">REVIEW QUEUE</span><h2>建议复习</h2><p>按遗忘风险和薄弱程度排序，复习后应再做一次短测确认。</p></div><CalendarClock :size="20" class="icon-purple" /></div><div class="review-list"><article v-for="item in reviewRows" :key="item.concept_id"><div><strong>{{ conceptTitle(item.concept_id) }}</strong><small>掌握度 {{ pct(item.mastery_score) }} · 置信度 {{ pct(item.confidence) }}</small></div><button class="icon-button" :title="`复习${conceptTitle(item.concept_id)}`" @click="router.push('/learning-path')"><ArrowRight :size="16" /></button></article></div><p class="muted-text">超过 7 天未复测的知识点优先进入复习队列；不足 7 天时优先提示掌握度或置信度最低的内容。</p></section><section class="panel"><div class="panel-heading"><div><span class="eyebrow">WEEKLY PLAN</span><h2>本周学习计划</h2><p>把画像转成可执行的小目标，而不是只记录分数。</p></div><BookOpenCheck :size="20" class="icon-success" /></div><div class="weekly-plan"><div><strong>{{ recentLearningRows.length }}</strong><span>本周已更新知识点</span></div><div><strong>{{ profile?.learner.self_assessment?.weekly_hours || learningSnapshot.preferences.pace_hours_per_week || 5 }}h</strong><span>每周可投入时间</span></div><p>优先完成「{{ nextAction?.title || '当前推荐知识点' }}」的讲解与练习，再对「{{ reviewRows[0] ? conceptTitle(reviewRows[0].concept_id) : '本章薄弱点' }}」进行一次间隔复测。</p></div></section></div>

      <template v-if="profile">
        <div class="profile-overview-grid"><section class="panel profile-score-panel"><div class="panel-heading"><div><span class="eyebrow">OVERALL MASTERY</span><h2>总体掌握度</h2></div><ShieldCheck :size="20" class="icon-success" /></div><div class="profile-score-body"><ProgressRing :value="learner.mastery" :size="142" /><div><strong>{{ profile.ability_level?.overall || 'beginner' }}</strong><span>当前能力等级</span><p>能力等级只在阶段复诊时更新；单次小测只更新对应知识点，避免无关维度随一次答题跳变。</p><div class="tag-list"><span class="tag">已测 {{ knowledgeMastery?.tested_kps || 0 }}/{{ knowledgeMastery?.total_kps || points.length }} 个</span><span class="tag">证据覆盖 {{ pct(knowledgeMastery?.coverage_ratio) }}</span><span class="tag">综合置信度 {{ pct(knowledgeMastery?.overall_confidence) }}</span><span class="tag">theta {{ num(knowledgeMastery?.global_theta) }}</span></div></div></div></section><AIInsightCard :body="profile.diagnosis_summary?.full || `已取得 ${knowledgeMastery?.tested_kps || 0} 个知识点的测试证据，建议优先处理薄弱环节。`" suggestion="学习后画像会持续保留小测证据，阶段复诊再汇总为能力结论。" action="生成学习路径" @action="router.push('/learning-path')" /></div>
        <div class="content-grid content-grid-main"><section class="panel"><div class="panel-heading"><div><span class="eyebrow">ABILITY DIMENSIONS</span><h2>能力维度</h2></div><BrainCircuit :size="20" class="icon-purple" /></div><div class="ability-list"><div v-for="[key, item] in abilities" :key="key" class="ability-row"><div><strong>{{ abilityLabels[key] || key }}</strong><small>{{ item.level === 'insufficient_evidence' ? '证据不足' : item.level }} · 置信度 {{ pct(item.confidence) }}</small></div><template v-if="typeof item.score === 'number'"><div class="progress-track"><span :style="{ width: `${item.score * 100}%` }" /></div><b>{{ pct(item.score) }}</b></template><template v-else><div class="progress-track"><span style="width: 0" /></div><b>证据不足</b></template></div></div></section><section class="panel"><div class="panel-heading"><div><span class="eyebrow">DOMAIN MASTERY</span><h2>领域掌握度</h2></div><TrendingUp :size="20" class="icon-success" /></div><MasteryChart v-if="Object.keys(domainValues).length" :values="domainValues" /><p v-else class="muted-text">尚无可用于领域比较的知识点证据。</p><div class="domain-list"><div v-for="(item, name) in domainSummary" :key="name" class="domain-row"><span>{{ name }}</span><small>已覆盖 {{ item.kps_covered }}/{{ item.total_kps || 0 }} · 已测 {{ item.tested_kps || 0 }} · 置信度 {{ pct(item.evidence_confidence) }}</small></div></div></section></div>
        <div class="content-grid content-grid-main"><section class="panel"><div class="panel-heading"><div><span class="eyebrow">KNOWLEDGE POINTS</span><h2>诊断知识点详情</h2></div><span class="status-pill">已测 {{ knowledgeMastery?.tested_kps || 0 }}/{{ knowledgeMastery?.total_kps || points.length }}</span></div><div class="mastery-cards"><article v-for="point in points.slice(0, 12)" :key="point.name" class="mastery-item"><div><strong>{{ point.name }}</strong><small>{{ point.domain }} · {{ point.test_count ? `测试 ${point.test_count} 题` : point.mastery === null ? '尚未测评' : '逐点自评' }} · {{ evidenceLabel(point.evidence_level) }} · 置信度 {{ pct(point.confidence) }}</small></div><div class="mini-progress"><span :style="{ width: `${(point.mastery || 0) * 100}%` }" /></div><b>{{ pct(point.mastery) }}</b></article></div></section><section class="panel goal-panel"><div class="panel-heading"><div><span class="eyebrow">GOAL & PREFERENCE</span><h2>学习目标与偏好</h2></div><Target :size="20" class="icon-blue" /></div><div class="goal-box"><strong>{{ profile.learner.self_assessment?.learning_goal || '掌握核心课程' }}</strong><span>每周约 {{ profile.learner.self_assessment?.weekly_hours || 5 }} 小时</span></div><div class="tag-list"><span v-for="item in ['分步讲解', '示例优先', '练习巩固', '知识图谱']" :key="item" class="tag">{{ item }}</span></div></section></div>
        <section class="panel outcome-panel"><div class="panel-heading"><div><span class="eyebrow">OUTCOME VERIFICATION</span><h2>阶段成果检验</h2><p>保存基线后继续学习，再复诊对比整体能力变化。它与每次小测的即时更新互补。</p></div><RefreshCcw :size="20" class="icon-purple" /></div><div class="outcome-toolbar"><button class="button button-secondary" :disabled="learner.loading" @click="onSaveBaseline"><Save :size="16" /> 保存基线画像</button><button class="button button-primary" :disabled="learner.loading || !learner.baselineProfileId" @click="onVerifyOutcome"><RefreshCcw :size="16" /> 复诊并检验成果</button><span v-if="learner.baselineProfileId" class="status-pill status-pill-success"><CheckCircle2 :size="13" /> 基线已保存 · ...{{ learner.baselineProfileId.slice(-6) }}</span><span v-else class="status-pill status-pill-warning">尚未保存基线</span></div><StateBlocks v-if="learner.error" type="error" title="操作失败" :message="learner.error" /><template v-if="outcomeReport"><div class="outcome-verdict" :class="verdictTone(outcomeReport.overall_verdict)"><div><span class="eyebrow">OVERALL VERDICT · {{ outcomeReport.chapter_id }}</span><h3>{{ outcomeReport.overall_verdict }}</h3><p v-if="outcomeReport.recommendation">{{ outcomeReport.recommendation }}</p></div><TrendingUp :size="26" class="icon-success" /></div><div class="outcome-columns"><div class="outcome-sub"><h4>领域掌握度变化</h4><div v-for="change in outcomeReport.domain_changes" :key="change.domain" class="outcome-row"><div><strong>{{ change.domain }}</strong><small>{{ pct(change.before) }} → {{ pct(change.after) }}</small></div><div class="mini-progress"><span :style="{ width: pct(change.after) }" /></div><b :class="deltaClass(change.delta)">{{ pctDelta(change.delta) }}</b></div></div><div class="outcome-sub"><h4>知识点显著变化</h4><div v-if="notableKpChanges.length"><div v-for="change in notableKpChanges" :key="change.kp_id" class="outcome-row outcome-row-kp"><div><strong>{{ change.name }}</strong><small>{{ change.domain }} · {{ pct(change.before) }} → {{ pct(change.after) }}</small></div><span :class="categoryPill(change.category)">{{ change.category }}</span></div></div><p v-else class="muted-text">本轮没有知识点出现显著变化。</p></div></div></template><div v-else-if="!learner.error" class="outcome-hint"><p>保存当前画像作为基线，完成一段学习后复诊，查看长期能力是否真实提升。</p></div></section>
      </template>
    </template>
  </div>
</template>
