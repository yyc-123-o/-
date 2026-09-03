<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ArrowRight, Clock3, LockKeyhole, Network, Play, RefreshCw, Sparkles } from "lucide-vue-next";
import { useRouter } from "vue-router";
import LearningPathMap from "@/components/LearningPathMap.vue";
import KnowledgeNode from "@/components/KnowledgeNode.vue";
import StateBlocks from "@/components/StateBlocks.vue";
import { useLearningPathStore } from "@/stores/learningPath";
import { useLearnerStore } from "@/stores/learner";
import { renderInlineMath } from "@/utils/math";

const router = useRouter();
const path = useLearningPathStore();
const learner = useLearnerStore();
const selectedId = ref("");
const selectedNode = computed(() => path.nodes.find((item) => item.concept_id === selectedId.value) || path.currentNode);
const reasonLabels: Record<string, string> = {
  mastery_missing: "该知识点还缺少测评证据",
  mastery_low_confidence: "当前掌握度置信度较低",
  ready_for_intro: "按当前掌握度从基础讲解开始",
  ready_for_intermediate: "当前掌握度支持中阶讲解",
  ready_for_advanced: "当前掌握度支持进阶讲解",
  mastery_skip_threshold_met: "该知识点已达到跳过阈值",
  hard_prerequisite_unassessed: "需要先完成未测评的先修知识",
  hard_prerequisite_below_threshold: "需要先补齐掌握度不足的先修知识",
  hard_prerequisite_low_confidence: "需要先补齐置信度不足的先修知识",
  ability_incomplete: "能力画像证据尚不完整，采用保守难度",
  ability_low_confidence: "能力画像置信度较低，采用保守难度",
  target_focus: "与当前学习目标直接相关",
  mastery_gap: "掌握度缺口较大，优先补齐",
  error_risk: "存在相关错因记录，需要针对性练习",
  prerequisite_ready: "必要先修条件已满足",
  foundational_order: "按课程先修顺序安排",
  next_in_path: "路径中的下一项学习内容",
};
const personalizationReason = computed(() => {
  const reasons = path.currentNode?.reason_codes || [];
  return reasons.map((reason) => reasonLabels[reason] || reason).join("；");
});
onMounted(() => { if ((learner.snapshot || learner.profile) && !path.run) path.generate(); });
async function selectNode(id: string) { selectedId.value = id; if (path.run && path.nodes.find((n) => n.concept_id === id)?.status === "available") await path.startNode(id); }
</script>

<template>
  <div class="page-stack">
    <div class="page-intro"><div><span class="eyebrow">PERSONALIZED PATH</span><h2>你的个性化学习路径</h2><p>每个节点都有学习深度、预计时间和先修关系，路径会随着掌握度变化重新规划。</p></div><button class="button button-primary" :disabled="path.loading" @click="path.generate"><RefreshCw :size="17" /> {{ path.loading ? "生成中…" : "重新规划" }}</button></div>
    <section v-if="path.error" class="inline-error">{{ path.error }} <button class="text-link" @click="path.generate">重试</button></section>
    <section v-if="!path.run && !path.loading" class="panel"><StateBlocks type="empty" title="还没有学习路径" message="先完成诊断并生成学习画像，系统会依据知识图谱创建你的路径。" /><button class="button button-primary" @click="router.push('/diagnosis')">进入学情诊断 <ArrowRight :size="17" /></button></section>
    <template v-else>
      <section class="path-banner"><div class="path-banner-icon"><Network :size="24" /></div><div><span class="eyebrow">CURRENT RECOMMENDATION</span><h2>{{ path.currentNode?.title || path.currentNode?.name || "正在规划你的下一步" }}</h2><p v-html="renderInlineMath(path.currentNode?.summary || '系统正在根据你的掌握度和先修条件选择当前推荐节点。')" /><small v-if="personalizationReason" class="path-reason">个性化依据：{{ personalizationReason }}</small></div><span class="status-pill status-pill-success">{{ path.run?.status || "规划中" }}</span></section>
      <section v-if="path.recommendations.length" class="panel recommendation-panel"><div class="panel-heading"><div><span class="eyebrow">THIS WEEK</span><h2>本周推荐队列</h2><p>根据你的目标、掌握度和可投入时间动态排序。</p></div><Sparkles :size="20" class="icon-purple" /></div><div class="recommendation-list"><button v-for="item in path.recommendations" :key="item.concept_id" class="recommendation-item" @click="selectedId = item.concept_id"><span class="recommendation-rank">{{ item.rank }}</span><span class="recommendation-copy"><strong>{{ path.nodes.find((node) => node.concept_id === item.concept_id)?.title || item.concept_id }}</strong><small>{{ item.reason_codes.map((reason) => reasonLabels[reason] || reason).join("；") }}</small></span><span class="recommendation-time"><Clock3 :size="14" /> {{ item.estimated_minutes }} 分钟</span></button></div></section>
      <section v-if="path.run?.adaptation_trace?.length" class="panel adaptation-trace"><div class="panel-heading"><div><span class="eyebrow">ADAPTATION TRACE</span><h3>反馈后的调整</h3><p>系统根据最近一次测评重新计算了掌握度和推荐队列。</p></div></div><p v-for="item in path.run.adaptation_trace" :key="item" class="muted-text">{{ item }}</p></section>
      <div class="content-grid content-grid-main"><section class="panel path-panel"><div class="panel-heading"><div><span class="eyebrow">KNOWLEDGE GRAPH</span><h2>课程知识路径</h2></div><span class="path-legend"><i class="legend-current" />当前推荐 <i class="legend-done" />已掌握 <i class="legend-locked" />先修阻塞</span></div><LearningPathMap :nodes="path.nodes" @select="selectNode" /><StateBlocks v-if="!path.nodes.length" type="loading" message="正在载入课程节点。" /></section><aside class="page-stack"><section class="panel node-detail"><div class="panel-heading"><div><span class="eyebrow">NODE DETAIL</span><h3>节点详情</h3></div></div><template v-if="selectedNode"><KnowledgeNode :node="selectedNode" @select="selectNode" /><div class="detail-row"><span>学习深度</span><b>{{ selectedNode.depth || "intermediate" }}</b></div><div class="detail-row"><span>预计用时</span><b>{{ selectedNode.estimated_minutes || 20 }} 分钟</b></div><div class="detail-row"><span>掌握度</span><b>{{ typeof selectedNode.mastery_score === "number" ? `${Math.round(selectedNode.mastery_score * 100)}%` : "待评估" }}</b></div><div v-if="selectedNode.prerequisite_ids?.length" class="prerequisite-note"><LockKeyhole :size="15" /> 先修节点：{{ selectedNode.prerequisite_ids.join("、") }}</div><button class="button button-primary button-full" :disabled="selectedNode.status === 'blocked'" @click="router.push('/resources')"><Play :size="16" /> 进入学习资源</button></template><StateBlocks v-else message="选择一个知识节点查看详情。" /></section></aside></div>
    </template>
  </div>
</template>
