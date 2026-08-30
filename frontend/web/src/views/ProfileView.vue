<script setup lang="ts">
import { computed } from "vue";
import { ArrowRight, BrainCircuit, CheckCircle2, RefreshCcw, Save, ShieldCheck, Target, TrendingUp } from "lucide-vue-next";
import { useRouter } from "vue-router";
import ProgressRing from "@/components/ProgressRing.vue";
import MasteryChart from "@/components/MasteryChart.vue";
import AIInsightCard from "@/components/AIInsightCard.vue";
import StateBlocks from "@/components/StateBlocks.vue";
import { useLearnerStore } from "@/stores/learner";

const router = useRouter();
const learner = useLearnerStore();
const profile = computed(() => learner.profile);
const points = computed(() => Object.values(profile.value?.knowledge_mastery?.points || {}));
const knowledgeMastery = computed(() => profile.value?.knowledge_mastery);
const learningSnapshot = computed(() => learner.snapshot);
const learningMastery = computed(() =>
  (learningSnapshot.value?.knowledge_mastery || [])
    .filter((item) => item.assessment_status === "assessed" && typeof item.mastery_score === "number")
    .sort((a, b) => String(b.observed_at || "").localeCompare(String(a.observed_at || ""))),
);
const latestLearningUpdate = computed(() => learningMastery.value[0]?.observed_at || learningSnapshot.value?.generated_at || null);
const learningAverage = computed(() => {
  const values = learningMastery.value.map((item) => item.mastery_score as number);
  return values.length ? values.reduce((total, value) => total + value, 0) / values.length : null;
});
const learningAbilityEntries = computed(() => Object.entries(learningSnapshot.value?.abilities || {}));
const domainSummary = computed(() => knowledgeMastery.value?.domain_summary || {});
const domainValues = computed(() => Object.fromEntries(
  Object.entries(domainSummary.value)
    .filter(([, value]) => typeof value.mean_mastery === "number")
    .map(([key, value]) => [key, value.mean_mastery as number]),
));
const abilities = computed(() => Object.entries(profile.value?.ability_level?.sub_dimensions || {}));
const abilityLabels: Record<string, string> = { theoretical_understanding: "理论理解", coding_ability: "代码能力", mathematical_foundation: "数学基础", problem_solving: "问题解决" };

// ===== 学习成果检验（保存基线 → 继续学习 → 复诊对比）=====
const outcomeReport = computed(() => learner.outcomeReport);
const notableKpChanges = computed(() =>
  (outcomeReport.value?.kp_changes || [])
    .filter((change) => change.category !== "不变")
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
    .slice(0, 8),
);

async function onSaveBaseline() {
  await learner.saveBaseline();
}
async function onVerifyOutcome() {
  await learner.verifyOutcome();
}

function verdictTone(verdict: string) {
  if (verdict.includes("显著")) return "is-up";
  if (verdict.includes("退步")) return "is-down";
  if (verdict.includes("一般")) return "";
  return "is-flat";
}
function deltaClass(delta?: number) {
  if (delta === undefined || delta === null || delta === 0) return "delta-flat";
  return delta > 0 ? "delta-up" : "delta-down";
}
function deltaText(delta?: number) {
  if (delta === undefined || delta === null) return "—";
  return `${delta > 0 ? "▲ +" : delta < 0 ? "▼ " : "± "}${Math.abs(delta).toFixed(2)}`;
}
function pctDelta(delta?: number) {
  if (delta === undefined || delta === null) return "—";
  return `${delta > 0 ? "▲ +" : delta < 0 ? "▼ " : "± "}${Math.round(Math.abs(delta) * 100)}%`;
}
function num(value?: number, digits = 2) {
  return typeof value === "number" ? value.toFixed(digits) : "—";
}
function pct(value?: number | null) {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "—";
}
function evidenceLabel(level?: string) {
  return ({ preliminary: "初步证据", limited: "证据有限", stable: "证据稳定", self_report: "逐点自评", none: "尚未测评" } as Record<string, string>)[level || "none"] || "尚未测评";
}
function categoryPill(category: string) {
  if (category.includes("显著")) return "status-pill status-pill-success";
  if (category.includes("提升")) return "status-pill";
  if (category.includes("下降")) return "status-pill status-pill-danger";
  return "status-pill status-pill-warning";
}

function conceptTitle(conceptId: string) {
  const names: Record<string, string> = {
    scalar: "标量", vector: "向量", matrix: "矩阵", tensor: "张量",
    "matrix-operations": "矩阵运算", "matrix-multiplication": "矩阵乘法",
    convolution: "卷积运算", pooling: "池化", embedding: "嵌入表示",
    "gradient-descent": "梯度下降", relu: "ReLU", adam: "Adam",
  };
  const key = conceptId.split(".").at(-1) || conceptId;
  return names[key] || key.replaceAll("-", " ");
}
</script>

<template>
  <div class="page-stack">
    <div class="page-intro"><div><span class="eyebrow">LEARNER PROFILE</span><h2>你的学习画像</h2><p>画像会随着诊断、学习和测评不断更新，它不是标签，而是下一步学习的依据。</p></div><button class="button button-primary" @click="router.push('/learning-path')">查看个性化路径 <ArrowRight :size="17" /></button></div>
    <div v-if="!profile && !learningSnapshot"><section class="panel"><StateBlocks type="empty" title="还没有学习画像" message="完成学情诊断后，这里会展示掌握度、能力维度和学习偏好。" /><button class="button button-primary" @click="router.push('/diagnosis')">开始诊断</button></section></div>
    <template v-else>
      <section v-if="learningSnapshot" class="panel learning-profile-panel">
        <div class="panel-heading"><div><span class="eyebrow">LIVE LEARNING PROFILE</span><h2>学习后画像</h2><p>这里显示课程小测实时更新的掌握度，与初始诊断画像分开保留。</p></div><span class="status-pill status-pill-success"><CheckCircle2 :size="13" /> 已同步</span></div>
        <div class="learning-profile-summary"><div><strong>{{ learningMastery.length }}</strong><span>已更新知识点</span></div><div><strong>{{ pct(learningAverage) }}</strong><span>当前已测均值</span></div><div><strong>{{ latestLearningUpdate ? new Date(latestLearningUpdate).toLocaleString("zh-CN", { hour12: false }) : "等待小测" }}</strong><span>最近更新</span></div></div>
        <div v-if="learningMastery.length" class="learning-profile-grid"><article v-for="item in learningMastery.slice(0, 8)" :key="item.concept_id" class="mastery-item"><div><strong>{{ conceptTitle(item.concept_id) }}</strong><small>{{ item.concept_id }} · 置信度 {{ pct(item.confidence) }}</small></div><div class="mini-progress"><span :style="{ width: `${(item.mastery_score || 0) * 100}%` }" /></div><b>{{ pct(item.mastery_score) }}</b></article></div>
        <div v-if="learningAbilityEntries.length" class="learning-ability-list"><span v-for="[key, value] in learningAbilityEntries" :key="key">{{ abilityLabels[key] || key }} {{ pct(value.score) }}</span></div>
        <p v-else class="muted-text">完成课程小测后，本节知识点的掌握度会显示在这里。</p>
      </section>
      <template v-if="profile">
      <div class="profile-overview-grid"><section class="panel profile-score-panel"><div class="panel-heading"><div><span class="eyebrow">OVERALL MASTERY</span><h2>总体掌握度</h2></div><ShieldCheck :size="20" class="icon-success" /></div><div class="profile-score-body"><ProgressRing :value="learner.mastery" :size="142" /><div><strong>{{ profile.ability_level?.overall || "beginner" }}</strong><span>当前能力等级</span><p>只汇总已测试或逐点自评的知识点；未探索节点不会被当作掌握度。</p><div class="tag-list"><span class="tag">已测 {{ knowledgeMastery?.tested_kps || 0 }}/{{ knowledgeMastery?.total_kps || points.length }} 个</span><span class="tag">证据覆盖 {{ pct(knowledgeMastery?.coverage_ratio) }}</span><span class="tag">综合置信度 {{ pct(knowledgeMastery?.overall_confidence) }}</span><span class="tag">θ {{ num(knowledgeMastery?.global_theta) }}<template v-if="knowledgeMastery?.standard_error !== null && knowledgeMastery?.standard_error !== undefined"> · 标准误 {{ num(knowledgeMastery.standard_error, 3) }}</template></span></div></div></div></section><AIInsightCard :body="profile.diagnosis_summary?.full || `已取得 ${knowledgeMastery?.tested_kps || 0} 个知识点的测试证据，建议优先处理薄弱环节。`" suggestion="下一步进入学习路径，系统会按先修关系安排内容。" action="生成学习路径" @action="router.push('/learning-path')" /></div>
      <div class="content-grid content-grid-main"><section class="panel"><div class="panel-heading"><div><span class="eyebrow">ABILITY DIMENSIONS</span><h2>能力维度</h2></div><BrainCircuit :size="20" class="icon-purple" /></div><div class="ability-list"><div v-for="[key, item] in abilities" :key="key" class="ability-row"><div><strong>{{ abilityLabels[key] || key }}</strong><small>{{ item.level === 'insufficient_evidence' ? '证据不足' : item.level }} · 置信度 {{ pct(item.confidence) }}</small></div><template v-if="typeof item.score === 'number'"><div class="progress-track"><span :style="{ width: `${item.score * 100}%` }" /></div><b>{{ pct(item.score) }}</b></template><template v-else><div class="progress-track"><span style="width: 0" /></div><b>证据不足</b></template></div></div></section><section class="panel"><div class="panel-heading"><div><span class="eyebrow">DOMAIN MASTERY</span><h2>领域掌握度</h2></div><TrendingUp :size="20" class="icon-success" /></div><MasteryChart v-if="Object.keys(domainValues).length" :values="domainValues" /><p v-else class="muted-text">尚无可用于领域比较的知识点证据。</p><div class="domain-list"><div v-for="(item, name) in domainSummary" :key="name" class="domain-row"><span>{{ name }}</span><small>已覆盖 {{ item.kps_covered }}/{{ item.total_kps || 0 }} · 已测 {{ item.tested_kps || 0 }} · 置信度 {{ pct(item.evidence_confidence) }}</small></div></div></section></div>
      <div class="content-grid content-grid-main"><section class="panel"><div class="panel-heading"><div><span class="eyebrow">KNOWLEDGE POINTS</span><h2>知识点掌握详情</h2></div><span class="status-pill">已测 {{ knowledgeMastery?.tested_kps || 0 }}/{{ knowledgeMastery?.total_kps || points.length }}</span></div><div class="mastery-cards"><article v-for="point in points.slice(0, 12)" :key="point.name" class="mastery-item"><div><strong>{{ point.name }}</strong><small>{{ point.domain }} · {{ point.test_count ? `测试 ${point.test_count} 题` : point.mastery === null ? '尚未测评' : '逐点自评' }} · {{ evidenceLabel(point.evidence_level) }} · 置信度 {{ pct(point.confidence) }}<template v-if="point.standard_error !== null && point.standard_error !== undefined"> · 标准误 {{ num(point.standard_error, 2) }}</template></small></div><div class="mini-progress"><span :style="{ width: `${(point.mastery || 0) * 100}%` }" /></div><b>{{ pct(point.mastery) }}</b></article></div></section><section class="panel goal-panel"><div class="panel-heading"><div><span class="eyebrow">GOAL & PREFERENCE</span><h2>学习目标与偏好</h2></div><Target :size="20" class="icon-blue" /></div><div class="goal-box"><strong>{{ profile.learner.self_assessment?.learning_goal || "掌握核心课程" }}</strong><span>每周约 {{ profile.learner.self_assessment?.weekly_hours || 5 }} 小时</span></div><div class="tag-list"><span v-for="item in ['分步讲解', '示例优先', '练习巩固', '知识图谱']" :key="item" class="tag">{{ item }}</span></div></section></div>
      <section class="panel outcome-panel">
        <div class="panel-heading"><div><span class="eyebrow">OUTCOME VERIFICATION</span><h2>学习成果检验</h2><p>把当前画像存为基线；完成一段学习后复诊，对比前后画像，检验能力是否真实提升。</p></div><RefreshCcw :size="20" class="icon-purple" /></div>
        <div class="outcome-toolbar">
          <button class="button button-secondary" :disabled="learner.loading" @click="onSaveBaseline"><Save :size="16" /> 保存基线画像</button>
          <button class="button button-primary" :disabled="learner.loading || !learner.baselineProfileId" @click="onVerifyOutcome"><RefreshCcw :size="16" /> 复诊并检验成果</button>
          <span v-if="learner.baselineProfileId" class="status-pill status-pill-success"><CheckCircle2 :size="13" /> 基线已保存 · …{{ learner.baselineProfileId.slice(-6) }}</span>
          <span v-else class="status-pill status-pill-warning">尚未保存基线</span>
        </div>
        <StateBlocks v-if="learner.error" type="error" title="操作失败" :message="learner.error" />
        <template v-if="outcomeReport">
          <div class="outcome-verdict" :class="verdictTone(outcomeReport.overall_verdict)"><div><span class="eyebrow">OVERALL VERDICT · {{ outcomeReport.chapter_id }}</span><h3>{{ outcomeReport.overall_verdict }}</h3><p v-if="outcomeReport.recommendation">{{ outcomeReport.recommendation }}</p></div><TrendingUp v-if="!verdictTone(outcomeReport.overall_verdict).includes('down')" :size="26" class="icon-success" /><TrendingUp v-else :size="26" style="transform: rotate(180deg);" class="icon-muted" /></div>
          <div class="outcome-metrics">
            <div class="outcome-metric"><span>能力值 θ</span><b>{{ num(outcomeReport.theta?.before) }} → {{ num(outcomeReport.theta?.after) }}</b><i :class="deltaClass(outcomeReport.theta?.delta)">{{ deltaText(outcomeReport.theta?.delta) }}</i></div>
            <div class="outcome-metric"><span>答题正确率</span><b>{{ pct(outcomeReport.accuracy?.before) }} → {{ pct(outcomeReport.accuracy?.after) }}</b><i :class="deltaClass(outcomeReport.accuracy?.delta)">{{ pctDelta(outcomeReport.accuracy?.delta) }}</i></div>
            <div class="outcome-metric"><span>能力等级</span><b>{{ outcomeReport.ability_level?.before || "—" }} → {{ outcomeReport.ability_level?.after || "—" }}</b><i class="delta-flat">复诊评估</i></div>
          </div>
          <div class="outcome-columns">
            <div class="outcome-sub"><h4>领域掌握度变化</h4><div v-for="change in outcomeReport.domain_changes" :key="change.domain" class="outcome-row"><div><strong>{{ change.domain }}</strong><small>{{ pct(change.before) }} → {{ pct(change.after) }}</small></div><div class="mini-progress"><span :style="{ width: pct(change.after) }" /></div><b :class="deltaClass(change.delta)">{{ deltaText(change.delta) }}</b></div></div>
            <div class="outcome-sub"><h4>知识点显著变化</h4><div v-if="notableKpChanges.length"><div v-for="change in notableKpChanges" :key="change.kp_id" class="outcome-row outcome-row-kp"><div><strong>{{ change.name }}</strong><small>{{ change.domain }} · {{ pct(change.before) }} → {{ pct(change.after) }}</small></div><span :class="categoryPill(change.category)">{{ change.category }}</span></div></div><p v-else class="muted-text">本轮没有知识点出现显著变化。</p></div>
          </div>
          <div class="outcome-gaps">
            <div class="gap-group"><h4>已解决盲区 · {{ outcomeReport.gaps_resolved.length }}</h4><div class="tag-list"><span v-for="gap in outcomeReport.gaps_resolved" :key="gap.kp_id" class="tag tag-green">{{ gap.name }}</span><span v-if="!outcomeReport.gaps_resolved.length" class="muted-text">暂无</span></div></div>
            <div class="gap-group"><h4>仍需关注 · {{ outcomeReport.gaps_remaining.length }}</h4><div class="tag-list"><span v-for="gap in outcomeReport.gaps_remaining" :key="gap.kp_id" class="tag tag-amber">{{ gap.name }}</span><span v-if="!outcomeReport.gaps_remaining.length" class="muted-text">暂无</span></div></div>
            <div class="gap-group"><h4>新增盲区 · {{ outcomeReport.gaps_new.length }}</h4><div class="tag-list"><span v-for="gap in outcomeReport.gaps_new" :key="gap.kp_id" class="tag tag-red">{{ gap.name }}</span><span v-if="!outcomeReport.gaps_new.length" class="muted-text">暂无</span></div></div>
          </div>
        </template>
        <div v-else-if="!learner.error" class="outcome-hint"><p>流程：① 点击「保存基线画像」记录当前水平 → ② 继续课程学习并完成测评 → ③ 回到这里点击「复诊并检验成果」，查看能力提升报告。</p></div>
      </section>
      </template>
    </template>
  </div>
</template>
