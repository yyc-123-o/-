<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ArrowLeft, ArrowRight, CheckCircle2, CircleHelp, Gauge, RotateCcw } from "lucide-vue-next";
import { useRouter } from "vue-router";
import { useDiagnosisStore } from "@/stores/diagnosis";
import { useLearnerStore } from "@/stores/learner";
import StateBlocks from "@/components/StateBlocks.vue";

const router = useRouter();
const diagnosis = useDiagnosisStore();
const learner = useLearnerStore();
const selectedAnswer = ref<number | null>(null);
const questionStartedAt = ref(Date.now());
const question = computed(() => diagnosis.session?.next_question);
const displayedTheta = computed(() => (
  diagnosis.session?.finished
    ? diagnosis.session.final_theta
    : diagnosis.session?.current_theta
));
const thetaProgress = computed(() => Math.min(
  100,
  Math.max(10, (((displayedTheta.value ?? 0) + 2) / 4) * 100),
));
const coveredKps = computed(() => diagnosis.session?.covered_kp || 0);
const totalKps = computed(() => diagnosis.session?.total_kp || 0);
const coveragePercent = computed(() => totalKps.value ? Math.round((coveredKps.value / totalKps.value) * 100) : 0);
const estimatorLabel = computed(() => {
  const method = diagnosis.session?.estimator_method;
  if (method === "adaptivetesting-EAP") return "EAP 贝叶斯估计";
  if (method === "grid-EAP") return "EAP 贝叶斯估计（网格积分）";
  if (method === "project-IRT-MLE-fallback") return "IRT-MLE 回退估计";
  return "能力估计准备中";
});
const calibrationLabel = computed(() => diagnosis.session?.item_calibration_status === "calibrated" ? "已标定" : "待真实数据标定");

watch(() => question.value?.question_id, (questionId) => {
  if (questionId) questionStartedAt.value = Date.now();
}, { immediate: true });
onMounted(() => { void diagnosis.resumeAdaptive(); });

async function start() {
  try { await diagnosis.startAdaptive(); } catch (error) { diagnosis.error = error instanceof Error ? error.message : "测试启动失败"; }
}
async function answer() {
  if (!question.value || selectedAnswer.value === null) return;
  const id = question.value.question_id;
  const value = selectedAnswer.value;
  selectedAnswer.value = null;
  try { await diagnosis.answer(id, value, questionStartedAt.value); } catch (error) { diagnosis.error = error instanceof Error ? error.message : "提交答案失败"; }
}
async function finish() {
  try { await diagnosis.finishAdaptive(); router.push("/profile"); } catch (error) { diagnosis.error = error instanceof Error ? error.message : "画像生成失败"; }
}
</script>

<template>
  <div class="page-stack">
    <div class="page-intro"><div><span class="eyebrow">STEP 02 · ADAPTIVE ASSESSMENT</span><h2>用几道题校准你的知识水平</h2><p>题目会根据你的回答动态调整，帮助系统更准确地判断下一步学习起点。</p></div><span class="status-pill status-pill-purple"><Gauge :size="14" /> {{ diagnosis.status }}</span></div>
    <div v-if="!learner.selectedLearnerId" class="panel"><StateBlocks type="empty" title="还没有选择学习者" message="先完成基础信息，或从学情诊断概览载入已有学习者。" /><button class="button button-primary" @click="router.push('/diagnosis')">返回诊断概览</button></div>
    <template v-else>
      <section class="assessment-hero panel"><div><span class="eyebrow">ADAPTIVE ROUTE</span><h2>先覆盖知识点，再按信息量选题</h2><p>第一轮优先覆盖未测知识点；达到覆盖目标后，系统选择最能降低标准误的题目，不是机械地逐步加难。</p><div v-if="diagnosis.session" class="assessment-progress"><span>知识点覆盖 {{ coveredKps }}/{{ totalKps || "—" }}</span><div class="progress-track"><span :style="{ width: `${coveragePercent}%` }" /></div><b>{{ coveragePercent }}%</b></div></div><div class="assessment-facts"><div><strong>{{ diagnosis.session?.question_count || 0 }}</strong><span>已回答题目</span></div><div><strong>{{ coveredKps }}</strong><span>已覆盖知识点</span></div></div></section>
      <div class="content-grid content-grid-main">
        <section class="panel">
          <div class="panel-heading"><div><span class="eyebrow">CURRENT QUESTION</span><h2>{{ question ? "当前题目" : "准备开始" }}</h2></div><span class="status-pill">{{ diagnosis.session?.current_domain || "等待测试" }}</span></div>
          <div v-if="!diagnosis.session" class="start-test-block"><CircleHelp :size="32" /><h3>开始一次自适应测试</h3><p>大约需要 5 到 8 分钟，可以随时停下，之后继续。</p><button class="button button-primary" :disabled="diagnosis.submitting" @click="start">开始自适应测试 <ArrowRight :size="17" /></button></div>
          <div v-else-if="diagnosis.session.finished" class="finish-block"><CheckCircle2 :size="36" class="text-success" /><h3>测试已完成</h3><p>{{ diagnosis.session.stop_reason || "已经收集到足够的答题信号。" }}</p><button class="button button-primary" @click="finish">生成学习画像 <ArrowRight :size="17" /></button></div>
          <div v-else-if="question" class="question-card"><div class="question-meta">第 {{ diagnosis.session.question_count + 1 }} 题 · {{ diagnosis.session.current_tier || "当前难度" }}</div><h3>{{ question.question_text || "请根据你的理解选择答案" }}</h3><p v-if="diagnosis.session.selection_reason" class="question-selection-reason">本题原因：{{ diagnosis.session.selection_reason }}</p><div class="option-list"><label v-for="(option, index) in question.options || []" :key="option" class="option-item" :class="{ selected: selectedAnswer === index }"><input v-model="selectedAnswer" type="radio" :value="index" /><span class="option-key">{{ String.fromCharCode(65 + index) }}</span><span>{{ option }}</span></label></div><button class="button button-primary button-full" :disabled="selectedAnswer === null" @click="answer">提交答案 <ArrowRight :size="17" /></button></div>
          <StateBlocks v-else type="loading" message="正在准备下一道题目。" />
        </section>
        <aside class="page-stack">
          <section class="panel signal-panel"><div class="panel-heading"><div><span class="eyebrow">LEARNING SIGNAL</span><h3>实时诊断状态</h3></div><RotateCcw :size="17" class="icon-muted" /></div><div class="signal-metric-grid"><div><strong>{{ displayedTheta?.toFixed(2) || "—" }}</strong><span>{{ diagnosis.session?.finished ? "最终能力 θ" : "当前能力 θ" }}</span></div><div><strong>{{ diagnosis.session?.standard_error?.toFixed(2) || "—" }}</strong><span>后验标准误</span></div></div><div class="signal-track"><span :style="{ width: `${thetaProgress}%` }" /></div><div class="signal-facts"><span>估计方法 <b>{{ estimatorLabel }}</b></span><span>题目参数 <b>{{ calibrationLabel }}</b></span><span>当前领域 <b>{{ diagnosis.session?.current_domain || "—" }}</b></span><span>测试状态 <b>{{ diagnosis.session?.finished ? "已完成" : diagnosis.session ? "进行中" : "未开始" }}</b></span></div></section>
          <section class="panel answer-history"><div class="panel-heading"><div><span class="eyebrow">ANSWER HISTORY</span><h3>答题记录</h3></div><span>{{ diagnosis.adaptiveAnswers.length }} 题</span></div><div v-if="diagnosis.adaptiveAnswers.length" class="history-items"><div v-for="(item, index) in diagnosis.adaptiveAnswers.slice().reverse()" :key="`${item.concept}-${index}`"><span :class="item.correct ? 'answer-correct' : 'answer-wrong'">{{ item.correct ? "正确" : "需要复习" }}</span><span>{{ item.concept }}</span></div></div><StateBlocks v-else message="开始测试后，这里会显示你的答题信号。" /></section>
        </aside>
      </div>
      <div v-if="diagnosis.error" class="inline-error">{{ diagnosis.error }}</div>
      <div class="page-actions"><button class="button button-quiet" @click="router.push('/diagnosis/basic')"><ArrowLeft :size="17" /> 返回基础信息</button><button class="button button-secondary" :disabled="!diagnosis.session?.finished" @click="finish">结束并生成画像 <ArrowRight :size="17" /></button></div>
    </template>
  </div>
</template>
