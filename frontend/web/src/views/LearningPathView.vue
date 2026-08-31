<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ArrowRight, LockKeyhole, Network, Play, RefreshCw } from "lucide-vue-next";
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
onMounted(() => { if (learner.snapshot && !path.run) path.generate(); });
async function selectNode(id: string) { selectedId.value = id; if (path.run && path.nodes.find((n) => n.concept_id === id)?.status === "available") await path.startNode(id); }
</script>

<template>
  <div class="page-stack">
    <div class="page-intro"><div><span class="eyebrow">PERSONALIZED PATH</span><h2>你的个性化学习路径</h2><p>每个节点都有学习深度、预计时间和先修关系，路径会随着掌握度变化重新规划。</p></div><button class="button button-primary" :disabled="path.loading" @click="path.generate"><RefreshCw :size="17" /> {{ path.loading ? "生成中…" : "重新规划" }}</button></div>
    <section v-if="path.error" class="inline-error">{{ path.error }} <button class="text-link" @click="path.generate">重试</button></section>
    <section v-if="!path.run && !path.loading" class="panel"><StateBlocks type="empty" title="还没有学习路径" message="先完成诊断并生成学习画像，系统会依据知识图谱创建你的路径。" /><button class="button button-primary" @click="router.push('/diagnosis')">进入学情诊断 <ArrowRight :size="17" /></button></section>
    <template v-else>
      <section class="path-banner"><div class="path-banner-icon"><Network :size="24" /></div><div><span class="eyebrow">CURRENT RECOMMENDATION</span><h2>{{ path.currentNode?.title || path.currentNode?.name || "正在规划你的下一步" }}</h2><p v-html="renderInlineMath(path.currentNode?.summary || '系统正在根据你的掌握度和先修条件选择当前推荐节点。')" /></div><span class="status-pill status-pill-success">{{ path.run?.status || "规划中" }}</span></section>
      <div class="content-grid content-grid-main"><section class="panel path-panel"><div class="panel-heading"><div><span class="eyebrow">KNOWLEDGE GRAPH</span><h2>课程知识路径</h2></div><span class="path-legend"><i class="legend-current" />当前推荐 <i class="legend-done" />已掌握 <i class="legend-locked" />先修阻塞</span></div><LearningPathMap :nodes="path.nodes" @select="selectNode" /><StateBlocks v-if="!path.nodes.length" type="loading" message="正在载入课程节点。" /></section><aside class="page-stack"><section class="panel node-detail"><div class="panel-heading"><div><span class="eyebrow">NODE DETAIL</span><h3>节点详情</h3></div></div><template v-if="selectedNode"><KnowledgeNode :node="selectedNode" @select="selectNode" /><div class="detail-row"><span>学习深度</span><b>{{ selectedNode.depth || "intermediate" }}</b></div><div class="detail-row"><span>预计用时</span><b>{{ selectedNode.estimated_minutes || 20 }} 分钟</b></div><div class="detail-row"><span>掌握度</span><b>{{ typeof selectedNode.mastery_score === "number" ? `${Math.round(selectedNode.mastery_score * 100)}%` : "待评估" }}</b></div><div v-if="selectedNode.prerequisite_ids?.length" class="prerequisite-note"><LockKeyhole :size="15" /> 先修节点：{{ selectedNode.prerequisite_ids.join("、") }}</div><button class="button button-primary button-full" :disabled="selectedNode.status === 'blocked'" @click="router.push('/resources')"><Play :size="16" /> 进入学习资源</button></template><StateBlocks v-else message="选择一个知识节点查看详情。" /></section></aside></div>
    </template>
  </div>
</template>
