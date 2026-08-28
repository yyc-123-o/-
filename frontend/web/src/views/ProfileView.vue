<script setup lang="ts">
import { computed } from "vue";
import { ArrowRight, BrainCircuit, ShieldCheck, Target, TrendingUp } from "lucide-vue-next";
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
const domainValues = computed(() => Object.fromEntries(Object.entries(profile.value?.knowledge_mastery?.domain_summary || {}).map(([key, value]) => [key, value.mean_mastery])));
const abilities = computed(() => Object.entries(profile.value?.ability_level?.sub_dimensions || {}));
const abilityLabels: Record<string, string> = { theoretical_understanding: "理论理解", coding_ability: "代码能力", mathematical_foundation: "数学基础", problem_solving: "问题解决" };
</script>

<template>
  <div class="page-stack">
    <div class="page-intro"><div><span class="eyebrow">LEARNER PROFILE</span><h2>你的学习画像</h2><p>画像会随着诊断、学习和测评不断更新，它不是标签，而是下一步学习的依据。</p></div><button class="button button-primary" @click="router.push('/learning-path')">查看个性化路径 <ArrowRight :size="17" /></button></div>
    <div v-if="!profile"><section class="panel"><StateBlocks type="empty" title="还没有学习画像" message="完成学情诊断后，这里会展示掌握度、能力维度和学习偏好。" /><button class="button button-primary" @click="router.push('/diagnosis')">开始诊断</button></section></div>
    <template v-else>
      <div class="profile-overview-grid"><section class="panel profile-score-panel"><div class="panel-heading"><div><span class="eyebrow">OVERALL MASTERY</span><h2>总体掌握度</h2></div><ShieldCheck :size="20" class="icon-success" /></div><div class="profile-score-body"><ProgressRing :value="learner.mastery" :size="142" /><div><strong>{{ profile.ability_level?.overall || "intermediate" }}</strong><span>当前能力等级</span><p>画像置信度来自测试记录、自评信息和学习行为的综合证据。</p></div></div></section><AIInsightCard :body="profile.diagnosis_summary?.full || `当前已经识别 ${points.length} 个知识点，建议优先处理薄弱环节。`" suggestion="下一步进入学习路径，系统会按先修关系安排内容。" action="生成学习路径" @action="router.push('/learning-path')" /></div>
      <div class="content-grid content-grid-main"><section class="panel"><div class="panel-heading"><div><span class="eyebrow">ABILITY DIMENSIONS</span><h2>能力维度</h2></div><BrainCircuit :size="20" class="icon-purple" /></div><div class="ability-list"><div v-for="[key, item] in abilities" :key="key" class="ability-row"><div><strong>{{ abilityLabels[key] || key }}</strong><small>{{ item.level }}</small></div><div class="progress-track"><span :style="{ width: `${item.score * 100}%` }" /></div><b>{{ Math.round(item.score * 100) }}%</b></div></div></section><section class="panel"><div class="panel-heading"><div><span class="eyebrow">DOMAIN MASTERY</span><h2>领域掌握度</h2></div><TrendingUp :size="20" class="icon-success" /></div><MasteryChart :values="domainValues" /></section></div>
      <div class="content-grid content-grid-main"><section class="panel"><div class="panel-heading"><div><span class="eyebrow">KNOWLEDGE POINTS</span><h2>知识点掌握详情</h2></div><span class="status-pill">{{ points.length }} 个已识别</span></div><div class="mastery-cards"><article v-for="point in points.slice(0, 12)" :key="point.name" class="mastery-item"><div><strong>{{ point.name }}</strong><small>{{ point.domain }} · 置信度 {{ Math.round(point.confidence * 100) }}%</small></div><div class="mini-progress"><span :style="{ width: `${point.mastery * 100}%` }" /></div><b>{{ Math.round(point.mastery * 100) }}%</b></article></div></section><section class="panel goal-panel"><div class="panel-heading"><div><span class="eyebrow">GOAL & PREFERENCE</span><h2>学习目标与偏好</h2></div><Target :size="20" class="icon-blue" /></div><div class="goal-box"><strong>{{ profile.learner.self_assessment?.learning_goal || "掌握核心课程" }}</strong><span>每周约 {{ profile.learner.self_assessment?.weekly_hours || 5 }} 小时</span></div><div class="tag-list"><span v-for="item in ['分步讲解', '示例优先', '练习巩固', '知识图谱']" :key="item" class="tag">{{ item }}</span></div></section></div>
    </template>
  </div>
</template>
