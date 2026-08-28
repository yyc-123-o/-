<script setup lang="ts">
import { computed, ref } from "vue";
import { ArrowLeft, ArrowRight, CheckCircle2, CircleHelp, Gauge, RotateCcw } from "lucide-vue-next";
import { useRouter } from "vue-router";
import { useDiagnosisStore } from "@/stores/diagnosis";
import { useLearnerStore } from "@/stores/learner";
import StateBlocks from "@/components/StateBlocks.vue";

const router = useRouter();
const diagnosis = useDiagnosisStore();
const learner = useLearnerStore();
const selectedAnswer = ref<number | null>(null);
const question = computed(() => diagnosis.session?.next_question);

async function start() {
  try { await diagnosis.startAdaptive(); } catch (error) { diagnosis.error = error instanceof Error ? error.message : "测试启动失败"; }
}
async function answer() {
  if (!question.value || selectedAnswer.value === null) return;
  const id = question.value.question_id;
  const value = selectedAnswer.value;
  selectedAnswer.value = null;
  try { await diagnosis.answer(id, value); } catch (error) { diagnosis.error = error instanceof Error ? error.message : "提交答案失败"; }
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
      <section class="assessment-hero panel"><div><span class="eyebrow">ADAPTIVE ROUTE</span><h2>先建立覆盖，再逐步提高难度</h2><p>当前会优先覆盖关键知识点。每次回答都会成为学习画像的新信号。</p></div><div class="assessment-counter"><strong>{{ diagnosis.session?.question_count || 0 }}</strong><span>已回答题目</span></div></section>
      <div class="content-grid content-grid-main">
        <section class="panel">
          <div class="panel-heading"><div><span class="eyebrow">CURRENT QUESTION</span><h2>{{ question ? "当前题目" : "准备开始" }}</h2></div><span class="status-pill">{{ diagnosis.session?.current_domain || "等待测试" }}</span></div>
          <div v-if="!diagnosis.session" class="start-test-block"><CircleHelp :size="32" /><h3>开始一次自适应测试</h3><p>大约需要 5 到 8 分钟，可以随时停下，之后继续。</p><button class="button button-primary" :disabled="diagnosis.submitting" @click="start">开始自适应测试 <ArrowRight :size="17" /></button></div>
          <div v-else-if="diagnosis.session.finished" class="finish-block"><CheckCircle2 :size="36" class="text-success" /><h3>测试已完成</h3><p>{{ diagnosis.session.stop_reason || "已经收集到足够的答题信号。" }}</p><button class="button button-primary" @click="finish">生成学习画像 <ArrowRight :size="17" /></button></div>
          <div v-else-if="question" class="question-card"><div class="question-meta">第 {{ diagnosis.session.question_count + 1 }} 题 · {{ diagnosis.session.current_tier || "当前难度" }}</div><h3>{{ question.question_text || "请根据你的理解选择答案" }}</h3><div class="option-list"><label v-for="(option, index) in question.options || []" :key="option" class="option-item" :class="{ selected: selectedAnswer === index }"><input v-model="selectedAnswer" type="radio" :value="index" /><span class="option-key">{{ String.fromCharCode(65 + index) }}</span><span>{{ option }}</span></label></div><button class="button button-primary button-full" :disabled="selectedAnswer === null" @click="answer">提交答案 <ArrowRight :size="17" /></button></div>
          <StateBlocks v-else type="loading" message="正在准备下一道题目。" />
        </section>
        <aside class="page-stack">
          <section class="panel signal-panel"><div class="panel-heading"><div><span class="eyebrow">LEARNING SIGNAL</span><h3>实时诊断状态</h3></div><RotateCcw :size="17" class="icon-muted" /></div><div class="signal-number">{{ diagnosis.session?.current_theta?.toFixed(2) || "—" }}</div><span class="signal-label">当前能力 θ</span><div class="signal-track"><span :style="{ width: `${Math.min(100, Math.max(10, ((diagnosis.session?.current_theta || 0) + 2) / 4 * 100))}%` }" /></div><div class="signal-facts"><span>当前领域 <b>{{ diagnosis.session?.current_domain || "—" }}</b></span><span>测试状态 <b>{{ diagnosis.session?.finished ? "已完成" : diagnosis.session ? "进行中" : "未开始" }}</b></span></div></section>
          <section class="panel answer-history"><div class="panel-heading"><div><span class="eyebrow">ANSWER HISTORY</span><h3>答题记录</h3></div><span>{{ diagnosis.adaptiveAnswers.length }} 题</span></div><div v-if="diagnosis.adaptiveAnswers.length" class="history-items"><div v-for="(item, index) in diagnosis.adaptiveAnswers.slice().reverse()" :key="`${item.concept}-${index}`"><span :class="item.correct ? 'answer-correct' : 'answer-wrong'">{{ item.correct ? "正确" : "需要复习" }}</span><span>{{ item.concept }}</span></div></div><StateBlocks v-else message="开始测试后，这里会显示你的答题信号。" /></section>
        </aside>
      </div>
      <div v-if="diagnosis.error" class="inline-error">{{ diagnosis.error }}</div>
      <div class="page-actions"><button class="button button-quiet" @click="router.push('/diagnosis/basic')"><ArrowLeft :size="17" /> 返回基础信息</button><button class="button button-secondary" :disabled="!diagnosis.session?.finished" @click="finish">结束并生成画像 <ArrowRight :size="17" /></button></div>
    </template>
  </div>
</template>
