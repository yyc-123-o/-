<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ArrowRight, ClipboardCheck, FileText, Gauge, Sparkles, Upload } from "lucide-vue-next";
import { useRouter } from "vue-router";
import DiagnosisStepper from "@/components/DiagnosisStepper.vue";
import ProfileSummary from "@/components/ProfileSummary.vue";
import AIInsightCard from "@/components/AIInsightCard.vue";
import StateBlocks from "@/components/StateBlocks.vue";
import { useDiagnosisStore } from "@/stores/diagnosis";
import { useLearnerStore } from "@/stores/learner";
import { api } from "@/api/client";
import type { LearnerSnapshot } from "@/types/learner";

const router = useRouter();
const diagnosis = useDiagnosisStore();
const learner = useLearnerStore();
const selectedId = ref(learner.selectedLearnerId);
const demoInput = ref<HTMLInputElement | null>(null);
const demoImporting = ref(false);
const demoImportError = ref("");
onMounted(() => diagnosis.loadLearners());
function jump(stage: number) {
  if (stage === 1) router.push("/diagnosis/basic");
  else if (stage === 2) router.push("/diagnosis/assessment");
  else router.push("/profile");
}
async function loadSelected() {
  await learner.selectLearner(selectedId.value);
}

function openDemoImport() {
  demoImportError.value = "";
  demoInput.value?.click();
}

async function importDemoProfile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  demoImporting.value = true;
  demoImportError.value = "";
  try {
    const raw = JSON.parse(await file.text()) as Record<string, unknown>;
    const result = await api.post<{ snapshot: LearnerSnapshot }>("/api/v1/profiles/adapt", raw);
    learner.setDemoProfile(raw, result.data.snapshot);
    await router.push("/learning-path");
  } catch (error) {
    demoImportError.value = error instanceof Error ? error.message : "画像导入失败";
  } finally {
    demoImporting.value = false;
  }
}
</script>

<template>
  <div class="page-stack">
    <section class="diagnosis-hero">
      <div><span class="eyebrow">AI LEARNING DIAGNOSIS</span><h2>开始构建你的学习画像</h2><p>通过几个简单问题和自适应测试，知径会理解你的知识基础、学习目标和学习偏好，生成可执行的个性化学习建议。</p><div class="hero-meta"><span><b>约 8 分钟</b> 完成初始诊断</span><span><b>3 个阶段</b> 逐步完善画像</span><span><b>可随时保存</b> 下次继续</span></div></div>
      <div class="diagnosis-visual"><div class="orbit orbit-a" /><div class="orbit orbit-b" /><span class="floating-node node-center">知</span><span class="floating-node node-one">数</span><span class="floating-node node-two">AI</span><span class="floating-node node-three">路</span></div>
    </section>
    <DiagnosisStepper :current="diagnosis.activeStage" :completed="diagnosis.completedStages" @select="jump" />
    <div class="content-grid content-grid-main">
      <section class="panel">
        <div class="panel-heading"><div><span class="eyebrow">YOUR NEXT STEP</span><h2>选择当前诊断任务</h2><p>从最适合你的阶段开始，所有进度都会自动保存。</p></div><span class="status-pill status-pill-warning">{{ diagnosis.status }}</span></div>
        <div class="diagnosis-task-grid">
          <button class="diagnosis-task" @click="router.push('/diagnosis/basic')"><span class="task-icon task-blue"><FileText :size="20" /></span><span><b>基础信息</b><small>学习背景、专业方向、学习目标</small></span><ArrowRight :size="17" /></button>
          <button class="diagnosis-task" @click="router.push('/diagnosis/assessment')"><span class="task-icon task-purple"><Gauge :size="20" /></span><span><b>知识水平</b><small>自评与自适应测试相结合</small></span><ArrowRight :size="17" /></button>
          <button class="diagnosis-task" @click="router.push('/profile')"><span class="task-icon task-green"><ClipboardCheck :size="20" /></span><span><b>学习画像</b><small>掌握度、能力维度与薄弱点</small></span><ArrowRight :size="17" /></button>
        </div>
        <div class="learner-selector"><label>查看已有学习者画像<select v-model="selectedId" :disabled="diagnosis.learnersLoading"><option value="">请选择学习者</option><option v-for="item in learner.learners" :key="item.id" :value="item.id">{{ item.name }} · {{ item.major }}</option></select></label><button class="button button-secondary" :disabled="!selectedId || learner.loading" @click="loadSelected">{{ learner.loading ? "加载中…" : "载入画像" }}</button><input ref="demoInput" type="file" accept="application/json,.json" hidden @change="importDemoProfile" /><button class="button button-quiet" :disabled="demoImporting" @click="openDemoImport"><Upload :size="16" /> {{ demoImporting ? "导入中…" : "导入画像 JSON" }}</button></div>
        <div v-if="demoImportError" class="inline-error">{{ demoImportError }}</div>
        <StateBlocks v-if="learner.error" type="error" title="画像加载失败" :message="learner.error" action="重新加载" @retry="diagnosis.loadLearners" />
      </section>
      <AIInsightCard title="你的 AI 学习顾问" :body="learner.profile ? `我已经看到 ${learner.profile.learner.name} 的部分学习信号。下一步建议完成自适应测试，让路径规划更准确。` : '我会根据你的回答调整诊断节奏，并解释每一步结果。先完成基础信息，我们就可以开始。'" suggestion="先完成自评，再开始自适应测试。" action="开始自适应测试" @action="router.push('/diagnosis/assessment')" />
    </div>
    <ProfileSummary :profile="learner.profile" />
    <section class="panel"><div class="panel-heading"><div><span class="eyebrow">PROCESS</span><h2>从诊断到学习</h2></div><Sparkles :size="20" class="icon-purple" /></div><div class="process-strip"><div><b>01</b><span>采集学习信号</span></div><div><b>02</b><span>识别知识盲区</span></div><div><b>03</b><span>生成学习路径</span></div><div><b>04</b><span>根据测评持续更新</span></div></div></section>
  </div>
</template>
