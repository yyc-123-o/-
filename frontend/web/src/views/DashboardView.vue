<script setup lang="ts">
import { computed } from "vue";
import { Activity, BookOpenCheck, BrainCircuit, ChevronRight, Flame, Target } from "lucide-vue-next";
import { useRouter } from "vue-router";
import StatCard from "@/components/StatCard.vue";
import ProgressRing from "@/components/ProgressRing.vue";
import TaskCard from "@/components/TaskCard.vue";
import AIInsightCard from "@/components/AIInsightCard.vue";
import StateBlocks from "@/components/StateBlocks.vue";
import { useLearnerStore } from "@/stores/learner";
import { useLearningPathStore } from "@/stores/learningPath";

const router = useRouter();
const learner = useLearnerStore();
const path = useLearningPathStore();
const domainSummary = computed(() => learner.profile?.knowledge_mastery?.domain_summary || {});
const mastery = computed(() => learner.mastery);
const weak = computed(() => learner.weakPoints.slice(0, 3));
</script>

<template>
  <div class="page-stack">
    <section class="welcome-hero">
      <div>
        <span class="eyebrow">PERSONALIZED LEARNING</span>
        <h2>从了解自己开始，找到适合你的学习路径。</h2>
        <p>知径会根据你的学习目标、知识掌握度和练习反馈，持续调整下一步学习内容。</p>
        <div class="hero-actions">
          <button class="button button-primary" @click="router.push(learner.profile ? '/learning-path' : '/diagnosis')">{{ learner.profile ? "继续学习" : "开始学情诊断" }} <ChevronRight :size="17" /></button>
          <span class="source-note">{{ learner.source === "real" ? "当前为真实画像数据" : "尚未载入画像" }}</span>
        </div>
      </div>
      <ProgressRing :value="mastery" label="总体掌握度" :size="142" />
    </section>
    <div class="stat-grid">
      <StatCard label="今日学习任务" value="2 个" hint="建议先完成当前节点" :icon="Target" tone="blue" />
      <StatCard label="连续学习" value="3 天" hint="保持你的学习节奏" :icon="Flame" tone="amber" />
      <StatCard label="薄弱知识点" :value="`${weak.length || 0} 个`" hint="低掌握或低置信度" :icon="BrainCircuit" tone="purple" />
      <StatCard label="已完成资源" value="8 个" hint="讲解、练习与测评" :icon="BookOpenCheck" tone="green" />
    </div>
    <div v-if="learner.error" class="inline-error">{{ learner.error }} <button class="text-link" @click="learner.loadLearners">重试</button></div>
    <div class="content-grid content-grid-main">
      <section class="panel">
        <div class="panel-heading"><div><span class="eyebrow">TODAY</span><h2>今日学习任务</h2></div><RouterLink to="/learning-path" class="text-link">查看路径 <ChevronRight :size="15" /></RouterLink></div>
        <div class="task-list">
          <TaskCard title="完成当前推荐知识点" description="根据你的画像，先巩固卷积神经网络基础。" duration="约 20 分钟" @open="router.push('/resources')" />
          <TaskCard title="完成一次小测验" description="用 5 道题验证今天的学习效果。" duration="约 8 分钟" @open="router.push('/assessment')" />
        </div>
      </section>
      <AIInsightCard :body="learner.profile ? `你当前的整体掌握度约为 ${Math.round(mastery * 100)}%，建议优先处理 ${weak[0]?.name || '薄弱知识点'}，再进入更高阶内容。` : '完成学情诊断后，我会结合你的目标和知识基础，给出更有针对性的下一步建议。'" suggestion="建议每天完成一个小任务，持续积累学习信号。" action="进入学情诊断" @action="router.push('/diagnosis')" />
    </div>
    <div class="content-grid content-grid-main">
      <section class="panel">
        <div class="panel-heading"><div><span class="eyebrow">MASTERY</span><h2>当前掌握度</h2></div><RouterLink to="/profile" class="text-link">查看完整画像 <ChevronRight :size="15" /></RouterLink></div>
        <div v-if="Object.keys(domainSummary).length" class="domain-list">
          <div v-for="(item, name) in domainSummary" :key="name" class="domain-row"><span>{{ name }}</span><div class="progress-track"><span :style="{ width: `${(item.mean_mastery || 0) * 100}%` }" /></div><b>{{ typeof item.mean_mastery === 'number' ? `${Math.round(item.mean_mastery * 100)}%` : '—' }}</b></div>
        </div>
        <StateBlocks v-else message="选择学习者或完成诊断后，这里会显示你的掌握度分布。" />
      </section>
      <section class="panel">
        <div class="panel-heading"><div><span class="eyebrow">RECENT</span><h2>最近学习记录</h2></div><RouterLink to="/history" class="text-link">全部记录 <ChevronRight :size="15" /></RouterLink></div>
        <div class="activity-list">
          <div class="activity-row"><span class="activity-dot blue" /><div><strong>查看学习画像</strong><small>今天 · 了解当前掌握度与薄弱点</small></div></div>
          <div class="activity-row"><span class="activity-dot green" /><div><strong>完成章节诊断</strong><small>昨天 · 已更新学习建议</small></div></div>
          <div class="activity-row"><span class="activity-dot purple" /><div><strong>浏览 CNN 知识讲解</strong><small>8 月 26 日 · 学习资源</small></div></div>
        </div>
      </section>
    </div>
    <section class="panel compact-panel"><div class="panel-heading"><div><span class="eyebrow">LEARNING LOOP</span><h2>你的学习闭环</h2></div><Activity :size="20" class="icon-muted" /></div><div class="loop-strip"><span>诊断</span><i>→</i><span>画像</span><i>→</i><span>规划</span><i>→</i><span>学习</span><i>→</i><span>测评</span><i>→</i><span>更新</span></div></section>
  </div>
</template>
