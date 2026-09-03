<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  BookOpen,
  Check,
  ChevronRight,
  Info,
  Maximize2,
  Minus,
  Network,
  Plus,
  RotateCcw,
  Search,
  X,
} from "lucide-vue-next";
import { globalKnowledgeGraph, type LearningOverlayStatus, type SystemKnowledgeEdge, type SystemKnowledgeNode, type SystemNodeType, type SystemRelation } from "@/data/globalKnowledgeGraph";
import { useLearnerStore } from "@/stores/learner";
import { useLearningPathStore } from "@/stores/learningPath";
import { useLearningRecordsStore } from "@/stores/learningRecords";
import { formatMastery } from "@/utils/mastery";

type NodeTypeFilter = "all" | "subject" | "course" | "chapter" | "knowledge_point";

const route = useRoute();
const router = useRouter();
const learner = useLearnerStore();
const path = useLearningPathStore();
const records = useLearningRecordsStore();

const selectedSubjectId = ref(String(route.query.subjectId || "all"));
const selectedCourseId = ref(String(route.query.courseId || "all"));
const selectedNodeId = ref(String(route.query.nodeId || route.query.kp || "dl.cnn.convolution"));
const nodeTypeFilter = ref<NodeTypeFilter>("all");
const relationTypes = ref<SystemRelation[]>(readRelationTypes(route.query.relationTypes));
const masteryStates = ref<LearningOverlayStatus[]>(readMasteryStates(route.query.masteryStates));
const searchQuery = ref("");
const zoom = ref(Number(route.query.zoom || 1));
const pan = ref({ x: 0, y: 0 });
const dragging = ref(false);
const dragStart = ref({ x: 0, y: 0 });
const panStart = ref({ x: 0, y: 0 });
const showHelp = ref(false);
const showAddDialog = ref(false);
const addNotice = ref("");
const viewportRef = ref<HTMLElement>();
let searchTimer: number | undefined;
const showFilters = ref(true);
const showDetails = ref(true);

const graphWidth = 1080;
const graphHeight = 820;
const minZoom = 0.25;
const maxZoom = 2;

const objectiveNodes = computed(() => globalKnowledgeGraph.nodes);
const objectiveEdges = computed(() => globalKnowledgeGraph.edges);
const selectedNode = computed(() => objectiveNodes.value.find((node) => node.id === selectedNodeId.value) || null);
const selectedPrerequisites = computed(() =>
  selectedNode.value
    ? objectiveEdges.value
      .filter((edge) => edge.relation === "prerequisite" && edge.targetId === selectedNode.value?.id)
      .map((edge) => objectiveNodes.value.find((node) => node.id === edge.sourceId))
      .filter((node): node is SystemKnowledgeNode => Boolean(node))
    : [],
);
const selectedNextNodes = computed(() =>
  selectedNode.value
    ? objectiveEdges.value
      .filter((edge) => edge.relation === "prerequisite" && edge.sourceId === selectedNode.value?.id)
      .map((edge) => objectiveNodes.value.find((node) => node.id === edge.targetId))
      .filter((node): node is SystemKnowledgeNode => Boolean(node))
      .slice(0, 4)
    : [],
);
const selectedOverlay = computed(() => selectedNode.value ? overlayForNode(selectedNode.value) : null);
const visibleCourses = computed(() => {
  if (selectedSubjectId.value === "all") return globalKnowledgeGraph.courses;
  return globalKnowledgeGraph.courses.filter((course) => course.id === "all" || course.subjectId === selectedSubjectId.value);
});
const filteredNodes = computed(() => {
  const query = searchQuery.value.trim().toLowerCase();
  return objectiveNodes.value.filter((node) => {
    const overlay = overlayForNode(node);
    const matchesSubject = selectedSubjectId.value === "all" || node.subjectId === selectedSubjectId.value || node.id === selectedSubjectId.value;
    const matchesCourse = selectedCourseId.value === "all" || node.courseId === selectedCourseId.value || node.id === selectedCourseId.value;
    const matchesType = nodeTypeFilter.value === "all" || node.type === nodeTypeFilter.value;
    const matchesState = node.type !== "knowledge_point" || masteryStates.value.includes(overlay.learningStatus);
    const searchable = [node.name, node.description, ...node.tags, ...node.aliases].join(" ").toLowerCase();
    return matchesSubject && matchesCourse && matchesType && matchesState && (!query || searchable.includes(query));
  });
});
const filteredNodeIds = computed(() => new Set(filteredNodes.value.map((node) => node.id)));
const filteredEdges = computed(() =>
  objectiveEdges.value.filter((edge) =>
    filteredNodeIds.value.has(edge.sourceId)
    && filteredNodeIds.value.has(edge.targetId)
    && relationTypes.value.includes(edge.relation),
  ),
);
const searchResults = computed(() => {
  const query = searchQuery.value.trim().toLowerCase();
  if (!query) return [];
  return filteredNodes.value
    .filter((node) => [node.name, node.description, ...node.tags, ...node.aliases].join(" ").toLowerCase().includes(query))
    .slice(0, 6);
});
const graphStats = computed(() => {
  const knowledge = filteredNodes.value.filter((node) => node.type === "knowledge_point");
  return {
    subjects: new Set(filteredNodes.value.map((node) => node.subjectId)).size,
    courses: filteredNodes.value.filter((node) => node.type === "course").length,
    knowledge: knowledge.length,
    edges: filteredEdges.value.length,
    mastered: knowledge.filter((node) => overlayForNode(node).learningStatus === "mastered").length,
  };
});
const selectedInPath = computed(() => Boolean(selectedNode.value && path.nodes.some((node) => node.concept_id === selectedNode.value?.id)));
const selectedCourseName = computed(() => globalKnowledgeGraph.courses.find((course) => course.id === selectedNode.value?.courseId)?.name || "课程知识");

function readRelationTypes(value: unknown): SystemRelation[] {
  const all: SystemRelation[] = ["prerequisite", "contains", "related", "applies_to"];
  const raw = typeof value === "string" ? value.split(",") : [];
  const next = raw.filter((item): item is SystemRelation => all.includes(item as SystemRelation));
  return next.length ? next : all;
}

function readMasteryStates(value: unknown): LearningOverlayStatus[] {
  const all: LearningOverlayStatus[] = ["not_started", "in_progress", "completed_unassessed", "mastered", "review_recommended"];
  const raw = typeof value === "string" ? value.split(",") : [];
  const next = raw.filter((item): item is LearningOverlayStatus => all.includes(item as LearningOverlayStatus));
  return next.length ? next : all;
}

function overlayForNode(node: SystemKnowledgeNode) {
  if (node.type !== "knowledge_point") {
    return {
      learningStatus: "not_started" as LearningOverlayStatus,
      masteryScore: null as number | null,
      completionRate: 0,
      lastLearnedAt: "",
      lastAssessedAt: "",
      isInLearningPath: false,
    };
  }
  const pathNode = path.nodes.find((item) => item.concept_id === node.id);
  const currentProgress = path.run?.learning_progress?.concept_id === node.id ? path.run.learning_progress : null;
  const mastery = typeof pathNode?.mastery_score === "number"
    ? pathNode.mastery_score
    : learner.snapshot?.knowledge_mastery.find((item) => item.concept_id === node.id)?.mastery_score
      ?? learner.profile?.knowledge_mastery?.points?.[node.id]?.mastery
      ?? null;
  const record = records.records.find((item) => item.knowledgeNodeId === node.id);
  let learningStatus: LearningOverlayStatus = "not_started";
  if (typeof mastery === "number" && mastery >= 0.75) learningStatus = "mastered";
  else if (currentProgress?.lecture_completed || record?.type === "resource_completed") learningStatus = "completed_unassessed";
  else if (currentProgress?.lecture_progress || pathNode?.status === "in_progress") learningStatus = "in_progress";
  else if (typeof mastery === "number" && mastery < 0.6) learningStatus = "review_recommended";
  return {
    learningStatus,
    masteryScore: typeof mastery === "number" ? mastery : null,
    completionRate: currentProgress?.lecture_completed ? 1 : currentProgress?.lecture_progress || 0,
    lastLearnedAt: record?.occurredAt || learner.snapshot?.knowledge_mastery.find((item) => item.concept_id === node.id)?.observed_at || "",
    lastAssessedAt: records.records.find((item) => item.knowledgeNodeId === node.id && item.type === "assessment_completed")?.occurredAt || "",
    isInLearningPath: Boolean(pathNode),
  };
}

function relationLabel(type: SystemRelation) {
  return { prerequisite: "先修关系", contains: "包含关系", related: "相关关系", applies_to: "应用关系" }[type];
}

function statusLabel(status: LearningOverlayStatus) {
  return { not_started: "未学习", in_progress: "学习中", completed_unassessed: "已完成待测评", mastered: "已掌握", review_recommended: "建议复习" }[status];
}

function nodeTypeLabel(type: SystemNodeType) {
  return { subject: "学科", course: "课程", chapter: "章节", knowledge_point: "知识点" }[type];
}

function nodeClass(node: SystemKnowledgeNode) {
  return [`node-${node.type}`, `status-${overlayForNode(node).learningStatus}`, { selected: node.id === selectedNodeId.value, dimmed: !filteredNodeIds.value.has(node.id) }];
}

function edgeClass(edge: SystemKnowledgeEdge) {
  const selected = selectedNodeId.value && (edge.sourceId === selectedNodeId.value || edge.targetId === selectedNodeId.value);
  return [`edge-${edge.relation}`, { selected }];
}

function edgePath(edge: SystemKnowledgeEdge) {
  const source = objectiveNodes.value.find((node) => node.id === edge.sourceId);
  const target = objectiveNodes.value.find((node) => node.id === edge.targetId);
  if (!source || !target) return "";
  const curve = Math.max(40, Math.abs(target.position.x - source.position.x) * 0.34);
  return `M ${source.position.x} ${source.position.y} C ${source.position.x + curve} ${source.position.y}, ${target.position.x - curve} ${target.position.y}, ${target.position.x} ${target.position.y}`;
}

function miniEdgePath(edge: SystemKnowledgeEdge) {
  const source = objectiveNodes.value.find((node) => node.id === edge.sourceId);
  const target = objectiveNodes.value.find((node) => node.id === edge.targetId);
  if (!source || !target) return "";
  const scaleX = 180 / graphWidth;
  const scaleY = 110 / graphHeight;
  const sx = source.position.x * scaleX;
  const sy = source.position.y * scaleY;
  const tx = target.position.x * scaleX;
  const ty = target.position.y * scaleY;
  const curve = Math.max(8, Math.abs(tx - sx) * 0.34);
  return `M ${sx} ${sy} C ${sx + curve} ${sy}, ${tx - curve} ${ty}, ${tx} ${ty}`;
}

function selectNode(id: string) {
  selectedNodeId.value = id;
  showDetails.value = true;
  const node = objectiveNodes.value.find((item) => item.id === id);
  if (node?.subjectId) selectedSubjectId.value = node.subjectId;
  if (node?.courseId) selectedCourseId.value = node.courseId;
  focusNode(id);
  syncUrl();
}

function focusNode(id: string) {
  const box = viewportRef.value?.getBoundingClientRect();
  const node = objectiveNodes.value.find((item) => item.id === id);
  if (!box || !node) return;
  pan.value = {
    x: box.width / 2 - node.position.x * zoom.value,
    y: box.height / 2 - node.position.y * zoom.value,
  };
}

function fitCanvas() {
  const box = viewportRef.value?.getBoundingClientRect();
  if (!box || !filteredNodes.value.length) return;
  const xs = filteredNodes.value.map((node) => node.position.x);
  const ys = filteredNodes.value.map((node) => node.position.y);
  const minX = Math.min(...xs) - 90;
  const maxX = Math.max(...xs) + 90;
  const minY = Math.min(...ys) - 52;
  const maxY = Math.max(...ys) + 52;
  const contentWidth = Math.max(1, maxX - minX);
  const contentHeight = Math.max(1, maxY - minY);
  const next = Math.min(1.25, Math.max(minZoom, Math.min((box.width - 64) / contentWidth, (box.height - 64) / contentHeight)));
  zoom.value = Number(next.toFixed(2));
  pan.value = {
    x: box.width / 2 - ((minX + maxX) / 2) * next,
    y: box.height / 2 - ((minY + maxY) / 2) * next,
  };
  syncUrl();
}

function changeZoom(delta: number) {
  const box = viewportRef.value?.getBoundingClientRect();
  const next = Math.min(maxZoom, Math.max(minZoom, Number((zoom.value + delta).toFixed(2))));
  if (box && next !== zoom.value) {
    const cx = box.width / 2;
    const cy = box.height / 2;
    const ratio = next / zoom.value;
    pan.value = {
      x: cx - (cx - pan.value.x) * ratio,
      y: cy - (cy - pan.value.y) * ratio,
    };
  }
  zoom.value = next;
  syncUrl();
}

function resetLayout() {
  zoom.value = 1;
  const box = viewportRef.value?.getBoundingClientRect();
  pan.value = box
    ? { x: box.width / 2 - graphWidth / 2, y: box.height / 2 - graphHeight / 2 }
    : { x: 0, y: 0 };
  syncUrl();
}

function toggleRelation(type: SystemRelation) {
  relationTypes.value = relationTypes.value.includes(type)
    ? relationTypes.value.filter((item) => item !== type)
    : [...relationTypes.value, type];
  syncUrl();
}

function toggleState(status: LearningOverlayStatus) {
  masteryStates.value = masteryStates.value.includes(status)
    ? masteryStates.value.filter((item) => item !== status)
    : [...masteryStates.value, status];
  syncUrl();
}

function selectSubject(id: string) {
  selectedSubjectId.value = id;
  if (id !== "all" && !visibleCourses.value.some((course) => course.id === selectedCourseId.value)) {
    selectedCourseId.value = "all";
  }
  fitCanvas();
  syncUrl();
}

function selectCourse(id: string) {
  selectedCourseId.value = id;
  if (id !== "all") {
    const course = globalKnowledgeGraph.courses.find((item) => item.id === id);
    if (course?.subjectId) selectedSubjectId.value = course.subjectId;
  }
  fitCanvas();
  syncUrl();
}

function openKnowledgeBase(kind?: "lecture" | "example" | "practice" | "assessment") {
  if (!selectedNode.value) return;
  void router.push({
    path: "/resources",
    query: {
      courseId: selectedNode.value.courseId || globalKnowledgeGraph.courses[1]?.id,
      chapterId: selectedNode.value.chapterId || undefined,
      knowledgeId: selectedNode.value.id,
      kp: selectedNode.value.id,
      tab: "catalog",
      resourceType: kind || undefined,
      resourceTab: kind || undefined,
      detail: "1",
    },
    hash: "#knowledge-base",
  });
}

function addToPath() {
  if (!selectedNode.value) return;
  if (selectedInPath.value) {
    void router.push({ path: "/learning-path", query: { kp: selectedNode.value.id } });
    return;
  }
  showAddDialog.value = true;
}

async function confirmAddToPath() {
  if (!selectedNode.value) return;
  if (!path.run) await path.generate();
  if (path.run) {
    await path.startNode(selectedNode.value.id);
    addNotice.value = `已将「${selectedNode.value.name}」加入你的学习路径。`;
  } else {
    addNotice.value = "请先完成学情诊断，系统才能写入个人学习路径。";
  }
  showAddDialog.value = false;
}

function onPointerDown(event: PointerEvent) {
  if ((event.target as HTMLElement).closest(".kg-node")) return;
  dragging.value = true;
  dragStart.value = { x: event.clientX, y: event.clientY };
  panStart.value = { ...pan.value };
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
}

function onPointerMove(event: PointerEvent) {
  if (!dragging.value) return;
  pan.value = {
    x: panStart.value.x + event.clientX - dragStart.value.x,
    y: panStart.value.y + event.clientY - dragStart.value.y,
  };
}

function onWheel(event: WheelEvent) {
  event.preventDefault();
  changeZoom(event.deltaY > 0 ? -0.08 : 0.08);
}

function onMiniMapClick(event: MouseEvent) {
  const box = viewportRef.value?.getBoundingClientRect();
  const mini = (event.currentTarget as HTMLElement).getBoundingClientRect();
  if (!box) return;
  const x = ((event.clientX - mini.left) / mini.width) * graphWidth;
  const y = ((event.clientY - mini.top) / mini.height) * graphHeight;
  pan.value = { x: box.width / 2 - x * zoom.value, y: box.height / 2 - y * zoom.value };
}

function openFullscreen() {
  void viewportRef.value?.requestFullscreen?.();
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    showHelp.value = false;
    showAddDialog.value = false;
    if (document.fullscreenElement) void document.exitFullscreen();
  }
}

function syncUrl() {
  void router.replace({
    query: {
      ...route.query,
      subjectId: selectedSubjectId.value,
      courseId: selectedCourseId.value,
      nodeId: selectedNodeId.value,
      relationTypes: relationTypes.value.join(","),
      masteryStates: masteryStates.value.join(","),
      zoom: String(zoom.value),
    },
  });
}

function shortDate(value?: string) {
  if (!value) return "暂无";
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit" }).format(new Date(value));
}

watch(searchQuery, () => {
  if (searchTimer) window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(syncUrl, 250);
});

watch(() => route.query.nodeId, (value) => {
  if (typeof value === "string" && value !== selectedNodeId.value) selectedNodeId.value = value;
});

onMounted(() => {
  window.addEventListener("keydown", onKeydown);
  fitCanvas();
});

onUnmounted(() => {
  window.removeEventListener("keydown", onKeydown);
  if (searchTimer) window.clearTimeout(searchTimer);
});
</script>

<template>
  <div class="kg-page">
    <header class="kg-title">
      <h2>知识图谱</h2>
      <p>探索系统知识结构，理解课程、知识点与先修关系。</p>
    </header>

    <section class="kg-overview panel">
      <div class="kg-overview-title">全局知识概览</div>
      <select :value="selectedSubjectId" aria-label="选择学科" @change="selectSubject(($event.target as HTMLSelectElement).value)">
        <option v-for="subject in globalKnowledgeGraph.subjects" :key="subject.id" :value="subject.id">{{ subject.name }}</option>
      </select>
      <select :value="selectedCourseId" aria-label="选择课程" @change="selectCourse(($event.target as HTMLSelectElement).value)">
        <option v-for="course in visibleCourses" :key="course.id" :value="course.id">{{ course.name }}</option>
      </select>
      <div class="kg-stats">
        <span><b>{{ graphStats.subjects }}</b>学科</span>
        <span><b>{{ graphStats.courses }}</b>课程</span>
        <span><b>{{ graphStats.knowledge }}</b>知识点</span>
        <span><b>{{ graphStats.edges }}</b>关系</span>
        <span><b>{{ graphStats.mastered }}</b>已掌握</span>
      </div>
      <div class="kg-overview-actions">
        <button class="button button-secondary" type="button" @click="showHelp = true"><Info :size="17" />图谱说明</button>
        <button class="button button-primary" type="button" @click="fitCanvas"><Maximize2 :size="17" />适应画布</button>
      </div>
    </section>

    <section class="kg-workspace panel" :class="{ 'filters-collapsed': !showFilters, 'details-collapsed': !showDetails }">
      <aside v-if="showFilters" class="kg-filter">
        <label class="kg-search">
          <Search :size="16" />
          <input v-model="searchQuery" type="search" placeholder="搜索知识点、课程或学科" @keyup.enter="searchResults[0] && selectNode(searchResults[0].id)" />
        </label>
        <div v-if="searchResults.length" class="kg-search-results">
          <button v-for="item in searchResults" :key="item.id" type="button" @click="selectNode(item.id)">
            <b>{{ item.name }}</b><span>{{ nodeTypeLabel(item.type) }}</span>
          </button>
        </div>

        <section class="kg-filter-section">
          <h3>知识范围</h3>
          <button v-for="subject in globalKnowledgeGraph.subjects" :key="subject.id" type="button" :class="{ active: selectedSubjectId === subject.id }" @click="selectSubject(subject.id)">
            <Network :size="15" />{{ subject.name }}
          </button>
        </section>

        <section class="kg-filter-section">
          <h3>节点层级</h3>
          <select v-model="nodeTypeFilter" aria-label="节点层级">
            <option value="all">全部层级</option>
            <option value="subject">学科</option>
            <option value="course">课程</option>
            <option value="chapter">章节</option>
            <option value="knowledge_point">知识点</option>
          </select>
        </section>

        <section class="kg-filter-section">
          <h3>关系类型</h3>
          <label v-for="type in (['prerequisite', 'contains', 'related', 'applies_to'] as SystemRelation[])" :key="type" class="kg-toggle">
            <span :class="`edge-sample edge-${type}`" />
            <span>{{ relationLabel(type) }}</span>
            <input type="checkbox" :checked="relationTypes.includes(type)" @change="toggleRelation(type)" />
          </label>
        </section>

        <section class="kg-filter-section">
          <h3>我的掌握状态</h3>
          <label v-for="state in (['not_started', 'in_progress', 'completed_unassessed', 'mastered', 'review_recommended'] as LearningOverlayStatus[])" :key="state" class="kg-check">
            <i :class="`status-${state}`" />
            <span>{{ statusLabel(state) }}</span>
            <input type="checkbox" :checked="masteryStates.includes(state)" @change="toggleState(state)" />
          </label>
        </section>

        <section class="kg-filter-section kg-legend">
          <h3>图例说明</h3>
          <p><b>节点类型</b> 课程/学科为矩形，知识点为圆形节点。</p>
          <p><b>掌握状态</b> 节点外圈表示个人学习覆盖层，不改变知识结构。</p>
        </section>
      </aside>

      <main class="kg-canvas-shell">
        <div class="kg-canvas-toolbar">
          <span>{{ filteredNodes.length }} 节点 · {{ filteredEdges.length }} 关系</span>
          <div>
            <button type="button" aria-label="收起筛选栏" :aria-pressed="!showFilters" @click="showFilters = !showFilters"><Search :size="16" /></button>
            <button type="button" aria-label="缩小" :disabled="zoom <= minZoom" @click="changeZoom(-0.1)"><Minus :size="16" /></button>
            <b>{{ Math.round(zoom * 100) }}%</b>
            <button type="button" aria-label="放大" :disabled="zoom >= maxZoom" @click="changeZoom(0.1)"><Plus :size="16" /></button>
            <button type="button" aria-label="恢复默认布局" @click="resetLayout"><RotateCcw :size="16" /></button>
            <button type="button" aria-label="全屏" @click="openFullscreen"><Maximize2 :size="16" /></button>
            <button type="button" aria-label="收起详情栏" :aria-pressed="!showDetails" @click="showDetails = !showDetails"><Info :size="16" /></button>
          </div>
        </div>
        <div
          ref="viewportRef"
          class="kg-viewport"
          :class="{ dragging }"
          @pointerdown="onPointerDown"
          @pointermove="onPointerMove"
          @pointerup="dragging = false"
          @pointercancel="dragging = false"
          @wheel="onWheel"
        >
          <div class="kg-stage" :style="{ width: `${graphWidth}px`, height: `${graphHeight}px`, transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }">
            <svg class="kg-edges" :viewBox="`0 0 ${graphWidth} ${graphHeight}`" aria-hidden="true">
              <defs>
                <marker id="kg-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto">
                  <path d="M0 0 L10 5 L0 10z" fill="#96a8bd" />
                </marker>
              </defs>
              <path v-for="edge in filteredEdges" :key="edge.id" :class="edgeClass(edge)" :d="edgePath(edge)" marker-end="url(#kg-arrow)">
                <title>{{ relationLabel(edge.relation) }}：{{ edge.description }}</title>
              </path>
            </svg>
            <button
              v-for="node in filteredNodes"
              :key="node.id"
              type="button"
              class="kg-node"
              :class="nodeClass(node)"
              :style="{ left: `${node.position.x}px`, top: `${node.position.y}px` }"
              :aria-label="`${node.name}，${nodeTypeLabel(node.type)}，${statusLabel(overlayForNode(node).learningStatus)}`"
              @click.stop="selectNode(node.id)"
            >
              <span>{{ node.name }}</span>
              <small v-if="zoom > .72 || node.type !== 'knowledge_point'">{{ nodeTypeLabel(node.type) }} · {{ statusLabel(overlayForNode(node).learningStatus) }}</small>
            </button>
          </div>
          <button class="kg-minimap" type="button" aria-label="点击缩略图定位画布" @click="onMiniMapClick">
            <svg viewBox="0 0 180 110" aria-hidden="true">
              <path v-for="edge in filteredEdges" :key="`mini-${edge.id}`" :d="miniEdgePath(edge)" />
              <circle v-for="node in filteredNodes" :key="`mini-${node.id}`" :cx="node.position.x / graphWidth * 180" :cy="node.position.y / graphHeight * 110" r="2.3" :class="{ selected: node.id === selectedNodeId }" />
            </svg>
            <span>拖动画布 · 滚轮缩放</span>
          </button>
        </div>
      </main>

      <aside v-if="showDetails" class="kg-detail">
        <h3>知识点详情</h3>
        <template v-if="selectedNode">
          <h2>{{ selectedNode.name }}</h2>
          <div class="kg-tags">
            <span>{{ nodeTypeLabel(selectedNode.type) }}</span>
            <span v-for="tag in selectedNode.tags.slice(0, 2)" :key="tag">{{ tag }}</span>
          </div>
          <section class="kg-detail-section">
            <div class="kg-mastery-line">
              <span>我的掌握度</span>
              <b>{{ selectedOverlay?.masteryScore === null ? "待评估" : formatMastery(selectedOverlay?.masteryScore) }}</b>
            </div>
            <div class="kg-progress"><i :style="{ width: `${(selectedOverlay?.masteryScore || 0) * 100}%` }" /></div>
            <p>最近学习 <b>{{ shortDate(selectedOverlay?.lastLearnedAt) }}</b></p>
          </section>
          <section class="kg-detail-section">
            <h4>知识点说明</h4>
            <p>{{ selectedNode.description || "当前节点暂无详细说明。" }}</p>
          </section>
          <section class="kg-detail-section">
            <h4>先修知识</h4>
            <div class="kg-link-tags">
              <button v-for="node in selectedPrerequisites" :key="node.id" type="button" @click="selectNode(node.id)">{{ node.name }}</button>
              <span v-if="!selectedPrerequisites.length">无先修要求</span>
            </div>
          </section>
          <section class="kg-detail-section">
            <h4>后续知识</h4>
            <div class="kg-link-tags">
              <button v-for="node in selectedNextNodes" :key="node.id" type="button" @click="selectNode(node.id)">{{ node.name }}</button>
              <span v-if="!selectedNextNodes.length">暂无直接后续节点</span>
            </div>
          </section>
          <section class="kg-detail-section">
            <h4>所属课程</h4>
            <button class="kg-course-link" type="button" @click="selectCourse(selectedNode.courseId || 'all')">
              <ChevronRight :size="15" />{{ selectedCourseName }}
            </button>
          </section>
          <section class="kg-detail-section">
            <h4>资源概览</h4>
            <div class="kg-resource-grid">
              <button type="button" @click="openKnowledgeBase('lecture')">讲义 <b>{{ selectedNode.resourceCount || 0 }}</b></button>
              <button type="button" @click="openKnowledgeBase('example')">示例 <b>1</b></button>
              <button type="button" @click="openKnowledgeBase('practice')">练习 <b>{{ selectedNode.resourceCount || 0 }}</b></button>
              <button type="button" @click="openKnowledgeBase('assessment')">测评 <b>{{ selectedNode.assessmentCount || 0 }}</b></button>
            </div>
          </section>
          <p v-if="addNotice" class="kg-notice">{{ addNotice }}</p>
          <div class="kg-detail-actions">
            <button class="button button-secondary" type="button" @click="openKnowledgeBase()"><BookOpen :size="16" />在课程知识库中查看</button>
            <button class="button button-primary" type="button" @click="addToPath"><Plus v-if="!selectedInPath" :size="16" /><Check v-else :size="16" />{{ selectedInPath ? "在路径中查看" : "加入学习路径" }}</button>
          </div>
        </template>
      </aside>
    </section>

    <div v-if="showHelp" class="kg-dialog-backdrop" @click.self="showHelp = false">
      <section class="kg-dialog" role="dialog" aria-modal="true" aria-label="图谱说明">
        <button type="button" aria-label="关闭" @click="showHelp = false"><X :size="18" /></button>
        <h3>图谱说明</h3>
        <p>矩形表示学科、课程和章节，圆形表示知识点。实线箭头表示先修关系，虚线表示包含关系，点线表示相关或应用关系。知识点外圈表示你的学习状态，不会改变系统知识结构。</p>
      </section>
    </div>

    <div v-if="showAddDialog" class="kg-dialog-backdrop" @click.self="showAddDialog = false">
      <section class="kg-dialog" role="dialog" aria-modal="true" aria-label="加入学习路径确认">
        <button type="button" aria-label="关闭" @click="showAddDialog = false"><X :size="18" /></button>
        <h3>加入学习路径</h3>
        <p>确认将「{{ selectedNode?.name }}」加入个人学习路径。系统会保留原知识图谱结构，只更新你的个人路径状态。</p>
        <p>先修条件：{{ selectedPrerequisites.length ? selectedPrerequisites.map((node) => node.name).join("、") : "无" }}</p>
        <p>预计学习时间：{{ selectedNode?.estimatedMinutes || 30 }} 分钟</p>
        <button class="button button-primary button-full" type="button" @click="confirmAddToPath">交给系统推荐位置</button>
      </section>
    </div>
  </div>
</template>

<style scoped>
.kg-page {
  display: grid;
  gap: 16px;
  width: 100%;
  max-width: 100%;
  overflow-x: clip;
}
.kg-page,
.kg-page * { box-sizing: border-box; }
.kg-title h2 { margin: 0; color: #10233f; font-size: 30px; line-height: 1.2; }
.kg-title p { margin: 8px 0 0; color: #52657d; font-size: 15px; }
.kg-overview {
  display: grid;
  grid-template-columns: auto 160px 180px minmax(280px, 1fr) auto;
  gap: 16px;
  align-items: center;
  padding: 18px 22px;
}
.kg-overview-title { color: #10233f; font-size: 18px; font-weight: 850; white-space: nowrap; }
.kg-overview select,
.kg-filter select {
  height: 42px;
  min-width: 0;
  padding: 0 12px;
  color: #10233f;
  background: #fff;
  border: 1px solid #dce5f0;
  border-radius: 8px;
}
.kg-stats {
  display: grid;
  grid-template-columns: repeat(5, minmax(58px, 1fr));
  align-items: center;
}
.kg-stats span {
  display: grid;
  gap: 3px;
  color: #64748b;
  border-left: 1px solid #e8eef5;
  text-align: center;
  font-size: 12px;
}
.kg-stats b { color: #10233f; font-size: 20px; }
.kg-overview-actions { display: flex; gap: 10px; }
.kg-overview-actions .button { height: 44px; white-space: nowrap; }
.kg-workspace {
  display: grid;
  grid-template-columns: 228px minmax(0, 1fr) 360px;
  height: clamp(650px, calc(100vh - 250px), 760px);
  padding: 0;
  overflow: hidden;
}
.kg-workspace.filters-collapsed { grid-template-columns: minmax(0, 1fr) 360px; }
.kg-workspace.details-collapsed { grid-template-columns: 228px minmax(0, 1fr); }
.kg-workspace.filters-collapsed.details-collapsed { grid-template-columns: minmax(0, 1fr); }
.kg-filter,
.kg-detail {
  min-width: 0;
  padding: 20px;
  overflow-y: auto;
  overflow-x: hidden;
}
.kg-filter { border-right: 1px solid #e8eef5; }
.kg-detail { border-left: 1px solid #e8eef5; }
.kg-search {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  height: 42px;
  padding: 0 12px;
  border: 1px solid #dce5f0;
  border-radius: 8px;
}
.kg-search input {
  min-width: 0;
  border: 0;
  outline: 0;
}
.kg-search-results {
  display: grid;
  gap: 6px;
  margin-top: 8px;
}
.kg-search-results button,
.kg-filter-section button,
.kg-link-tags button {
  min-width: 0;
  color: #52657d;
  background: transparent;
  border: 0;
  border-radius: 8px;
}
.kg-search-results button {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  padding: 8px;
  text-align: left;
}
.kg-search-results button:hover,
.kg-filter-section button:hover,
.kg-filter-section button.active { color: #2f6feb; background: #eef4ff; }
.kg-search-results b,
.kg-search-results span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kg-filter-section {
  display: grid;
  gap: 8px;
  padding: 18px 0;
  border-bottom: 1px solid #e8eef5;
}
.kg-filter-section h3,
.kg-detail h3,
.kg-detail-section h4 { margin: 0 0 4px; color: #10233f; font-size: 14px; }
.kg-filter-section button {
  display: flex;
  gap: 8px;
  align-items: center;
  min-height: 34px;
  padding: 0 8px;
}
.kg-toggle,
.kg-check {
  display: grid;
  grid-template-columns: 46px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  min-height: 32px;
  color: #52657d;
  font-size: 13px;
}
.kg-check { grid-template-columns: 14px minmax(0, 1fr) auto; }
.kg-toggle input,
.kg-check input { accent-color: #2f6feb; }
.edge-sample {
  display: block;
  width: 42px;
  border-top: 2px solid #94a3b8;
}
.edge-sample.edge-contains { border-top-style: dashed; }
.edge-sample.edge-related { border-top-style: dotted; }
.edge-sample.edge-applies_to { border-top-style: dashed; border-color: #4f6f94; }
.kg-check i {
  width: 12px;
  height: 12px;
  border: 2px solid currentColor;
  border-radius: 50%;
}
.status-not_started { color: #94a3b8; }
.status-in_progress { color: #2f6feb; }
.status-completed_unassessed { color: #18a7a0; }
.status-mastered { color: #16a36a; }
.status-review_recommended { color: #d98b20; }
.kg-legend p {
  margin: 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.65;
}
.kg-canvas-shell {
  position: relative;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-width: 0;
  background:
    radial-gradient(circle at 60% 35%, rgba(47, 111, 235, .07), transparent 28%),
    linear-gradient(180deg, #fbfdff, #fff);
}
.kg-canvas-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  min-height: 56px;
  padding: 12px 18px;
  color: #64748b;
  border-bottom: 1px solid #e8eef5;
  font-size: 13px;
}
.kg-canvas-toolbar div {
  display: flex;
  align-items: center;
  gap: 0;
  border: 1px solid #dce5f0;
  border-radius: 8px;
  overflow: hidden;
}
.kg-canvas-toolbar button {
  display: grid;
  place-items: center;
  width: 38px;
  height: 34px;
  background: #fff;
  border: 0;
  border-left: 1px solid #e8eef5;
}
.kg-canvas-toolbar button:disabled { color: #c1ccd9; background: #f8fafc; cursor: not-allowed; }
.kg-canvas-toolbar button:first-child { border-left: 0; }
.kg-canvas-toolbar b { min-width: 62px; color: #52657d; text-align: center; }
.kg-viewport {
  position: relative;
  min-height: 0;
  overflow: hidden;
  cursor: grab;
  touch-action: none;
}
.kg-viewport.dragging { cursor: grabbing; }
.kg-stage {
  position: absolute;
  inset: 0 auto auto 0;
  transform-origin: 0 0;
}
.kg-edges {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: visible;
}
.kg-edges path {
  fill: none;
  stroke: #9aaaba;
  stroke-width: 1.6;
  opacity: .78;
}
.kg-edges .edge-contains {
  stroke: #c4cfdb;
  stroke-dasharray: 6 5;
}
.kg-edges .edge-related {
  stroke: #aebbc9;
  stroke-dasharray: 2 6;
}
.kg-edges .edge-applies_to {
  stroke: #67809d;
  stroke-dasharray: 8 4 2 4;
}
.kg-edges .selected {
  stroke: #2f6feb;
  stroke-width: 2.2;
  opacity: 1;
}
.kg-node {
  position: absolute;
  display: grid;
  place-items: center;
  gap: 3px;
  width: 92px;
  min-height: 58px;
  padding: 8px 10px;
  color: #10233f;
  background: #fff;
  border: 2px solid currentColor;
  border-radius: 999px;
  box-shadow: 0 4px 12px rgba(16, 35, 63, .06);
  text-align: center;
  transform: translate(-50%, -50%);
}
.kg-node span {
  display: -webkit-box;
  overflow: hidden;
  line-height: 1.25;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.kg-node small {
  color: #64748b;
  font-size: 10px;
}
.kg-node.node-subject,
.kg-node.node-course,
.kg-node.node-chapter {
  width: 150px;
  border-radius: 12px;
}
.kg-node.node-course {
  width: 190px;
  min-height: 64px;
  color: #2f6feb;
  background: #eef4ff;
}
.kg-node.node-subject {
  color: #10233f;
  background: #f8fbff;
  border-color: #c8d9f6;
}
.kg-node.node-chapter {
  color: #52657d;
  border-style: dashed;
}
.kg-node.selected {
  color: #2f6feb;
  background: #f3f7ff;
  box-shadow: 0 0 0 5px rgba(47, 111, 235, .13), 0 6px 16px rgba(47, 111, 235, .14);
  z-index: 3;
}
.kg-node.status-mastered { color: #16a36a; }
.kg-node.status-review_recommended { color: #d98b20; }
.kg-node.status-completed_unassessed { color: #18a7a0; }
.kg-node.status-in_progress { color: #2f6feb; }
.kg-node.status-not_started { color: #aab6c4; }
.kg-minimap {
  position: absolute;
  left: 18px;
  bottom: 18px;
  width: 160px;
  padding: 8px;
  background: rgba(255,255,255,.9);
  border: 1px solid #cfe0ff;
  border-radius: 8px;
}
.kg-minimap svg {
  width: 100%;
  height: 86px;
}
.kg-minimap path {
  fill: none;
  stroke: #d3dce7;
  stroke-width: 1;
}
.kg-minimap circle {
  fill: #9fb4c8;
}
.kg-minimap circle.selected {
  fill: #2f6feb;
}
.kg-minimap span {
  color: #64748b;
  font-size: 11px;
}
.kg-detail h2 {
  margin: 12px 0 10px;
  color: #10233f;
  font-size: 24px;
  line-height: 1.3;
}
.kg-tags,
.kg-link-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.kg-tags span,
.kg-link-tags button,
.kg-link-tags span {
  min-height: 30px;
  padding: 6px 10px;
  color: #2f6feb;
  background: #eef4ff;
  border: 1px solid #dbe7ff;
  border-radius: 8px;
  font-size: 12px;
}
.kg-detail-section {
  padding: 18px 0;
  border-bottom: 1px solid #e8eef5;
}
.kg-detail-section p {
  margin: 8px 0 0;
  color: #52657d;
  line-height: 1.75;
}
.kg-mastery-line {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  color: #52657d;
}
.kg-mastery-line b {
  color: #10233f;
  font-size: 18px;
}
.kg-progress {
  height: 7px;
  margin: 10px 0;
  overflow: hidden;
  background: #e9eef5;
  border-radius: 99px;
}
.kg-progress i {
  display: block;
  height: 100%;
  background: #2f6feb;
}
.kg-course-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #2f6feb;
  background: transparent;
  border: 0;
  font-weight: 800;
}
.kg-resource-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}
.kg-resource-grid button {
  min-height: 54px;
  color: #52657d;
  background: #fff;
  border: 1px solid #dce5f0;
  border-radius: 8px;
}
.kg-resource-grid b {
  display: block;
  margin-top: 4px;
  color: #10233f;
}
.kg-detail-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  padding-top: 18px;
}
.kg-detail-actions .button { justify-content: center; min-height: 48px; }
.kg-notice {
  padding: 10px 12px;
  color: #14715b;
  background: #e9fbf3;
  border: 1px solid #bfe8d5;
  border-radius: 8px;
}
.kg-dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 90;
  display: grid;
  place-items: center;
  background: rgba(16, 35, 63, .2);
}
.kg-dialog {
  position: relative;
  width: min(460px, calc(100vw - 32px));
  padding: 24px;
  background: #fff;
  border: 1px solid #dce5f0;
  border-radius: 16px;
  box-shadow: 0 18px 42px rgba(16, 35, 63, .18);
}
.kg-dialog > button {
  position: absolute;
  top: 14px;
  right: 14px;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  background: #fff;
  border: 1px solid #dce5f0;
  border-radius: 8px;
}
.kg-dialog h3 {
  margin: 0 0 12px;
  color: #10233f;
}
.kg-dialog p {
  color: #52657d;
  line-height: 1.75;
}
@media (max-width: 1439px) {
  .kg-overview {
    grid-template-columns: 1fr 150px 170px;
  }
  .kg-stats,
  .kg-overview-actions {
    grid-column: 1 / -1;
  }
  .kg-workspace {
    grid-template-columns: 216px minmax(0, 1fr) 340px;
  }
}
@media (max-width: 1199px) {
  .kg-workspace {
    grid-template-columns: 1fr;
    height: auto;
    min-height: 680px;
  }
  .kg-filter,
  .kg-detail {
    border: 0;
    border-bottom: 1px solid #e8eef5;
  }
  .kg-filter {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px 18px;
  }
  .kg-search,
  .kg-search-results {
    grid-column: 1 / -1;
  }
  .kg-filter-section {
    border-bottom: 0;
    padding: 8px 0;
  }
  .kg-canvas-shell {
    min-height: 640px;
  }
  .kg-detail-actions {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 760px) {
  .kg-overview,
  .kg-filter,
  .kg-stats {
    grid-template-columns: 1fr;
  }
  .kg-overview-actions {
    display: grid;
    grid-template-columns: 1fr;
  }
  .kg-canvas-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }
  .kg-canvas-shell {
    min-height: 560px;
  }
  .kg-node {
    width: 86px;
    min-height: 54px;
  }
  .kg-minimap {
    width: 138px;
  }
}
</style>
