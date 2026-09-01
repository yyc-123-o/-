<script setup lang="ts">
import { computed, ref } from "vue";
import { ArrowRight, BarChart3, CheckCircle2, CircleAlert, FileCheck2 } from "lucide-vue-next";
import { useRouter } from "vue-router";
import { assessmentApi } from "@/api/assessment";
import { useLearningPathStore } from "@/stores/learningPath";

const router = useRouter();
const path = useLearningPathStore();
const score = ref(0.8);
const submitted = ref(false);
const feedback = ref<any>(null);
const node = computed(() => path.currentNode);
async function submit() {
  if (!path.run?.run_id || !node.value) return;
  try {
    feedback.value = await assessmentApi.submit(path.run.run_id, {
      assessment_id: `web-assessment-${Date.now()}`,
      concept_id: node.value.concept_id,
      score: score.value,
      responses: {},
      response_time_ms: 90_000,
      hint_count: 0,
      attempt_count: 1,
      passing_score: 0.6,
    });
    if (feedback.value?.status) path.setRun(feedback.value);
    submitted.value = true;
  } catch (error) {
    feedback.value = {
      failure: {
        message: error instanceof Error ? error.message : "测评提交失败",
      },
    };
  }
}
</script>

<template>
  <div class="page-stack">
    <div class="page-intro"><div><span class="eyebrow">ASSESSMENT FEEDBACK</span><h2>用一次测评验证你的掌握度</h2><p>测评结果会更新当前知识点的状态，并影响下一步学习建议。</p></div><span class="status-pill status-pill-warning">结果会写入画像</span></div>
    <section v-if="!node" class="panel"><div class="state-block"><div class="state-icon">○</div><strong>还没有可测评的知识点</strong><p>先生成学习路径并进入一个当前节点。</p><button class="button button-primary" @click="router.push('/learning-path')">前往学习路径</button></div></section>
    <template v-else>
      <section class="assessment-banner"><div class="assessment-banner-icon"><FileCheck2 :size="24" /></div><div><span class="eyebrow">CURRENT NODE</span><h2>{{ node.title || node.name || node.concept_id }}</h2><p>完成学习后，用自评结果或题目作答提交一次掌握度更新。</p></div></section>
      <div class="content-grid content-grid-main"><section class="panel assessment-form"><div class="panel-heading"><div><span class="eyebrow">CHECK YOUR UNDERSTANDING</span><h2>本次测评</h2></div><BarChart3 :size="20" class="icon-blue" /></div><label class="range-field"><span>你认为自己掌握了多少？ <b>{{ Math.round(score * 100) }}%</b></span><input v-model.number="score" type="range" min="0" max="1" step="0.05" /></label><div class="assessment-hints"><div><CheckCircle2 :size="17" /><span>通过线：60%</span></div><div><CircleAlert :size="17" /><span>低于通过线会推荐复习</span></div></div><button class="button button-primary button-large" :disabled="submitted" @click="submit">{{ submitted ? "测评已提交" : "提交测评并更新掌握度" }} <ArrowRight :size="17" /></button></section><section class="panel feedback-preview"><div class="panel-heading"><div><span class="eyebrow">LIVE FEEDBACK</span><h2>结果预览</h2></div></div><div v-if="!submitted" class="feedback-placeholder"><BarChart3 :size="30" /><p>提交后这里会显示 BKT 更新前后对比、错误类型和下一步建议。</p></div><div v-else class="feedback-result"><div class="result-score">{{ Math.round(score * 100) }}<small>%</small></div><strong>{{ score >= 0.6 ? "当前知识点已达到通过线" : "建议回到资源页复习" }}</strong><p>{{ score >= 0.6 ? "系统会解锁后续节点，并重新规划下一步学习内容。" : "系统会保留这次反馈，推荐补充讲解和针对性练习。" }}</p><button class="text-link" @click="router.push('/profile')">查看掌握度变化 <ArrowRight :size="15" /></button></div></section></div>
    </template>
  </div>
</template>
