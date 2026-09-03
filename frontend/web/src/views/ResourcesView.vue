<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  Bookmark,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileCheck2,
  FileText,
  Network,
  Play,
  RotateCcw,
  Search,
  X,
} from "lucide-vue-next";
import { courseKnowledgeBase, type CourseChapter, type CourseKnowledgeNode } from "@/data/courseKnowledgeBase";
import { useLearnerStore } from "@/stores/learner";
import { useLearningPathStore } from "@/stores/learningPath";
import { useLearningRecordsStore } from "@/stores/learningRecords";
import { courseIdFromProfile, courseTitle, knowledgeTitle } from "@/utils/knowledgeGraph";

type KnowledgeStatus = "mastered" | "learning" | "completed_unassessed" | "review" | "not_started" | "locked";
type ViewTab = "catalog" | "resources" | "favorites";
type ResourceKind = "all" | "lecture" | "example" | "practice" | "assessment";
type StatusFilter = "all" | KnowledgeStatus;
type SortMode = "course" | "status" | "mastery_desc" | "mastery_asc" | "recent";

const route = useRoute();
const router = useRouter();
const learner = useLearnerStore();
const path = useLearningPathStore();
const learningRecords = useLearningRecordsStore();

const selectedChapterId = ref(String(route.query.chapterId || route.query.chapter || courseKnowledgeBase.chapters[1]?.id || courseKnowledgeBase.chapters[0].id));
const selectedNodeId = ref(String(route.query.knowledgeId || route.query.kp || courseKnowledgeBase.chapters[1]?.nodes[3]?.id || courseKnowledgeBase.chapters[0].nodes[0].id));
const activeTab = ref<ViewTab>(readViewTab(route.query.tab, route.hash));
const searchQuery = ref(String(route.query.keyword || ""));
const resourceKind = ref<ResourceKind>(readResourceKind(route.query.resourceType, "all"));
const activeResourceTab = ref<ResourceKind>(readResourceKind(route.query.resourceTab, "lecture"));
const statusFilter = ref<StatusFilter>(readStatusFilter(route.query.masteryStatus));
const sortMode = ref<SortMode>(readSortMode(route.query.sort));
const completeSubmitting = ref(false);
const completeError = ref("");
const notice = ref("");
const favoriteIds = ref<string[]>(readFavorites());
const expandedChapterIds = ref<string[]>([selectedChapterId.value]);
const detailOpen = ref(route.query.detail === "1");

const allNodes = computed(() => courseKnowledgeBase.chapters.flatMap((chapter) => chapter.nodes));
const selectedChapter = computed(() =>
  courseKnowledgeBase.chapters.find((chapter) => chapter.id === selectedChapterId.value) || courseKnowledgeBase.chapters[0],
);
const selectedNode = computed(() =>
  allNodes.value.find((node) => node.id === selectedNodeId.value) || selectedChapter.value.nodes[0] || allNodes.value[0],
);
const pathNodeById = computed(() => new Map(path.nodes.map((node) => [node.concept_id, node])));
const currentConceptId = computed(() => path.run?.handoff?.concept_id || path.currentNode?.concept_id || path.run?.learning_progress?.concept_id || "");
const currentProgress = computed(() => path.run?.learning_progress?.concept_id === selectedNode.value?.id ? path.run.learning_progress : null);
const selectedStatus = computed(() => statusForNode(selectedNode.value));
const selectedMastery = computed(() => masteryForNode(selectedNode.value));
const selectedResources = computed(() => resourcesForNode(selectedNode.value, activeResourceTab.value));
const nodesInCurrentView = computed(() => activeTab.value === "catalog" ? selectedChapter.value.nodes : allNodes.value);
const filteredNodes = computed(() => {
  const query = searchQuery.value.trim().toLowerCase();
  let nodes = nodesInCurrentView.value.filter((node) => {
    const status = statusForNode(node);
    const matchesTab = activeTab.value !== "favorites" || favoriteIds.value.includes(node.id);
    const matchesStatus = statusFilter.value === "all" || status === statusFilter.value;
    const matchesKind = resourceKind.value === "all" || resourcesForNode(node, resourceKind.value).length > 0;
    const searchable = [
      node.title,
      node.summary,
      sectionTitle(node),
      ...resourcesForNode(node, "all").map((item) => `${item.title} ${item.label}`),
    ].join(" ").toLowerCase();
    const matchesQuery = !query || searchable.includes(query);
    return matchesTab && matchesStatus && matchesKind && matchesQuery;
  });
  if (sortMode.value === "mastery_desc") nodes = nodes.slice().sort((a, b) => (masteryForNode(b) ?? -1) - (masteryForNode(a) ?? -1));
  if (sortMode.value === "mastery_asc") nodes = nodes.slice().sort((a, b) => (masteryForNode(a) ?? 1) - (masteryForNode(b) ?? 1));
  if (sortMode.value === "status") nodes = nodes.slice().sort((a, b) => statusRank(statusForNode(a)) - statusRank(statusForNode(b)));
  if (sortMode.value === "recent") nodes = nodes.slice().sort((a, b) => recentRank(b) - recentRank(a));
  return nodes;
});
const filteredResourceRows = computed(() =>
  filteredNodes.value.flatMap((node) =>
    resourcesForNode(node, resourceKind.value).map((resource) => ({
      ...resource,
      node,
      chapter: courseKnowledgeBase.chapters.find((chapter) => chapter.id === node.chapterId),
    })),
  ),
);
const nodePanelTitle = computed(() => {
  if (activeTab.value === "resources") return "全部学习资源";
  if (activeTab.value === "favorites") return "我的收藏";
  return `第${String(selectedChapter.value.order).padStart(2, "0")}章 · ${selectedChapter.value.title}`;
});
const nodePanelSubtitle = computed(() => {
  if (activeTab.value === "resources") return "按课程结构汇总讲义、示例、练习与测评";
  if (activeTab.value === "favorites") return favoriteIds.value.length ? "你收藏的知识点会在这里集中展示" : "还没有收藏内容";
  return selectedChapter.value.subtitle;
});
const courseStats = computed(() => {
  const nodes = allNodes.value;
  const mastered = nodes.filter((node) => statusForNode(node) === "mastered").length;
  const learning = nodes.filter((node) => statusForNode(node) === "learning").length;
  const resources = nodes.reduce((sum, node) => sum + node.lectures + node.examples + node.exercises + node.assessments, 0);
  const assessments = nodes.reduce((sum, node) => sum + node.assessments, 0);
  return {
    total: nodes.length,
    mastered,
    learning,
    resources,
    assessments,
    progress: nodes.length ? Math.round((mastered / nodes.length) * 100) : 0,
  };
});
const chapterProgress = computed(() =>
  courseKnowledgeBase.chapters.map((chapter) => {
    const completed = chapter.nodes.filter((node) => ["mastered", "learning"].includes(statusForNode(node))).length;
    return { chapter, completed, total: chapter.nodes.length };
  }),
);
const canUseGeneratedResource = computed(() => Boolean(path.run?.run_id && selectedNode.value?.id === currentConceptId.value));
const contentCompleted = computed(() => Boolean(currentProgress.value?.lecture_completed));
const unlockedBySelected = computed(() =>
  allNodes.value.filter((node) => selectedNode.value && node.prerequisites.includes(selectedNode.value.id)).slice(0, 3),
);
const selectedRecentRecord = computed(() =>
  selectedNode.value
    ? learningRecords.records.find((record) => record.knowledgeNodeId === selectedNode.value?.id) || null
    : null,
);
const completeButtonLabel = computed(() => {
  if (completeSubmitting.value) return "正在保存";
  if (contentCompleted.value) return "已完成·去测评";
  return "标记已完成";
});
const primaryActionLabel = computed(() => {
  if (selectedStatus.value === "review") return "开始复习";
  if (selectedStatus.value === "completed_unassessed") return "去完成测评";
  if (selectedStatus.value === "mastered") return "复习知识点";
  return "继续学习";
});

function readFavorites() {
  try {
    const value = JSON.parse(localStorage.getItem("zhijing.course-kb.favorites.v1") || "[]") as string[];
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

function readViewTab(value: unknown, hash = ""): ViewTab {
  if (value === "resources" || hash === "#learning-resources") return "resources";
  if (value === "favorites") return "favorites";
  return "catalog";
}

function readResourceKind(value: unknown, fallback: ResourceKind): ResourceKind {
  return ["all", "lecture", "example", "practice", "assessment"].includes(String(value))
    ? String(value) as ResourceKind
    : fallback;
}

function readStatusFilter(value: unknown): StatusFilter {
  return ["mastered", "learning", "completed_unassessed", "review", "not_started", "locked"].includes(String(value))
    ? String(value) as StatusFilter
    : "all";
}

function readSortMode(value: unknown): SortMode {
  return ["course", "status", "mastery_desc", "mastery_asc", "recent"].includes(String(value))
    ? String(value) as SortMode
    : "course";
}

function persistFavorites() {
  localStorage.setItem("zhijing.course-kb.favorites.v1", JSON.stringify(favoriteIds.value));
}

function toggleFavorite(id: string) {
  favoriteIds.value = favoriteIds.value.includes(id)
    ? favoriteIds.value.filter((item) => item !== id)
    : [...favoriteIds.value, id];
  persistFavorites();
}

function toggleChapter(chapterId: string) {
  expandedChapterIds.value = expandedChapterIds.value.includes(chapterId)
    ? expandedChapterIds.value.filter((id) => id !== chapterId)
    : [...expandedChapterIds.value, chapterId];
}

function selectChapter(chapter: CourseChapter) {
  selectedChapterId.value = chapter.id;
  if (!expandedChapterIds.value.includes(chapter.id)) expandedChapterIds.value.push(chapter.id);
  if (chapter.nodes[0]) selectNode(chapter.nodes[0]);
}

function selectNode(node: CourseKnowledgeNode) {
  selectedNodeId.value = node.id;
  selectedChapterId.value = node.chapterId;
  detailOpen.value = true;
  notice.value = "";
  completeError.value = "";
  syncUrlState();
}

function closeDetail() {
  detailOpen.value = false;
  syncUrlState();
}

async function openLearning(node = selectedNode.value) {
  if (!node || statusForNode(node) === "locked") return;
  if (!path.run?.run_id) {
    await path.generate();
  } else if (pathNodeById.value.has(node.id) && node.id !== currentConceptId.value) {
    await path.startNode(node.id);
  }
  activeTab.value = "resources";
  activeResourceTab.value = "lecture";
  syncUrlState();
  notice.value = path.run?.run_id
    ? `已进入「${node.title}」的学习资源。`
    : "已打开课程知识点，完成学情诊断后可生成个性化资源。";
}

async function completeLearningContent() {
  if (!selectedNode.value) return;
  if (contentCompleted.value) {
    void router.push("/assessment");
    return;
  }
  if (!path.run?.run_id || selectedNode.value.id !== currentConceptId.value) {
    completeError.value = "请先进入当前知识点的学习资源。";
    return;
  }
  completeSubmitting.value = true;
  completeError.value = "";
  try {
    const updated = await path.completeLearningContent(selectedNode.value.id);
    const courseId = courseIdFromProfile(updated.profile || null) || selectedNode.value.chapterId;
    const occurredAt = new Date().toISOString();
    learningRecords.upsert({
      id: `${updated.run_id}:${selectedNode.value.id}:resource_completed`,
      learnerId: updated.profile?.learner_ref || "current-learner",
      courseId,
      courseTitle: courseTitle(courseId),
      knowledgeNodeId: selectedNode.value.id,
      knowledgeNodeTitle: selectedNode.value.title,
      resourceId: `${updated.run_id}:${selectedNode.value.id}:resource`,
      resourceTitle: `${selectedNode.value.title}学习资源`,
      assessmentId: null,
      attemptId: null,
      type: "resource_completed",
      title: "完成学习资源",
      description: `${selectedNode.value.title} · 学习内容已完成，等待测评验证`,
      durationSeconds: null,
      completionRate: 1,
      previousMastery: null,
      currentMastery: null,
      assessmentScore: null,
      assessmentAccuracy: null,
      previousRecommendedNodeId: selectedNode.value.id,
      currentRecommendedNodeId: updated.planning?.current_node?.concept_id || null,
      unlockedNodeIds: [],
      occurredAt,
      createdAt: occurredAt,
      source: "local-event",
      metadata: { runId: updated.run_id },
    });
    notice.value = "已完成该学习资源，学习进度和知识图谱状态已同步。";
  } catch (reason) {
    completeError.value = path.friendlyError(reason, "学习进度保存失败");
  } finally {
    completeSubmitting.value = false;
  }
}

async function openAssessment(node = selectedNode.value) {
  if (!node || statusForNode(node) === "locked") return;
  try {
    if (!path.run?.run_id) {
      await path.generate();
    }
    if (path.run?.run_id && pathNodeById.value.has(node.id) && node.id !== currentConceptId.value) {
      await path.startNode(node.id);
    }
    if (!path.run?.run_id) {
      completeError.value = "请先完成学习画像，再进入知识点测评。";
      return;
    }
    void router.push({ path: "/assessment", query: { kp: node.id, from: "knowledge-base" } });
  } catch (reason) {
    completeError.value = path.friendlyError(reason, "测评入口暂时无法打开");
  }
}

function setActiveTab(tab: ViewTab) {
  activeTab.value = tab;
  syncUrlState();
}

function setResourceTab(tab: ResourceKind) {
  activeResourceTab.value = tab;
  if (tab !== "all") activeTab.value = "resources";
  syncUrlState();
}

function clearFilters() {
  searchQuery.value = "";
  resourceKind.value = "all";
  statusFilter.value = "all";
  sortMode.value = "course";
  syncUrlState();
}

function syncUrlState() {
  const query: Record<string, string> = {
    ...Object.fromEntries(Object.entries(route.query).map(([key, value]) => [key, String(Array.isArray(value) ? value[0] || "" : value || "")])),
    tab: activeTab.value,
    chapter: selectedChapterId.value,
    kp: selectedNodeId.value,
    chapterId: selectedChapterId.value,
    knowledgeId: selectedNodeId.value,
    resourceTab: activeResourceTab.value,
    sort: sortMode.value,
  };
  if (searchQuery.value.trim()) query.keyword = searchQuery.value.trim();
  else delete query.keyword;
  if (resourceKind.value !== "all") query.resourceType = resourceKind.value;
  else delete query.resourceType;
  if (statusFilter.value !== "all") query.masteryStatus = statusFilter.value;
  else delete query.masteryStatus;
  if (detailOpen.value) query.detail = "1";
  else delete query.detail;
  void router.replace({
    query,
    hash: activeTab.value === "resources" ? "#learning-resources" : "#knowledge-base",
  });
}

function handleSearchEnter() {
  syncUrlState();
}

function selectCourse() {
  notice.value = "当前仅接入你已加入的人工智能基础课程，后续课程接入后可在这里切换。";
}

function resourceCount(node: CourseKnowledgeNode, kind: ResourceKind) {
  if (kind === "all") return node.lectures + node.examples + node.exercises + node.assessments;
  return {
    lecture: node.lectures,
    example: node.examples,
    practice: node.exercises,
    assessment: node.assessments,
  }[kind];
}

function resourceTabLabel(kind: ResourceKind) {
  return {
    all: "全部",
    lecture: "讲义",
    example: "示例",
    practice: "练习",
    assessment: "测评",
  }[kind];
}

function openResource(item: ReturnType<typeof resourcesForNode>[number]) {
  if (item.kind === "assessment") {
    void openAssessment();
    return;
  }
  void openLearning(selectedNode.value);
}

function locateInGraph() {
  void router.push({ path: "/course-center/knowledge-graph", query: selectedNode.value ? { nodeId: selectedNode.value.id, courseId: courseKnowledgeBase.id } : { courseId: courseKnowledgeBase.id } });
}

function masteryForNode(node?: CourseKnowledgeNode | null) {
  if (!node) return null;
  const fromPath = pathNodeById.value.get(node.id)?.mastery_score;
  if (typeof fromPath === "number") return fromPath;
  const snapshot = learner.snapshot?.knowledge_mastery.find((item) => item.concept_id === node.id)?.mastery_score;
  if (typeof snapshot === "number") return snapshot;
  const profile = learner.profile?.knowledge_mastery?.points?.[node.id]?.mastery;
  return typeof profile === "number" ? profile : null;
}

function statusForNode(node?: CourseKnowledgeNode | null): KnowledgeStatus {
  if (!node) return "not_started";
  const mastery = masteryForNode(node);
  if (mastery !== null && mastery >= 0.75) return "mastered";
  const progress = path.run?.learning_progress?.concept_id === node.id ? path.run.learning_progress : null;
  if (progress?.lecture_completed) return "completed_unassessed";
  if (node.id === currentConceptId.value || path.currentNode?.concept_id === node.id) return "learning";
  if (mastery !== null && mastery < 0.6) return "review";
  const unlocked = node.prerequisites.every((id) => {
    const prerequisite = allNodes.value.find((item) => item.id === id);
    const prerequisiteMastery = masteryForNode(prerequisite);
    return prerequisiteMastery === null || prerequisiteMastery >= 0.6 || path.run?.learning_progress?.concept_id === id;
  });
  return unlocked ? "not_started" : "locked";
}

function statusRank(status: KnowledgeStatus) {
  return { learning: 0, completed_unassessed: 1, review: 2, not_started: 3, mastered: 4, locked: 5 }[status];
}

function statusLabel(status: KnowledgeStatus) {
  return {
    mastered: "已掌握",
    learning: "学习中",
    completed_unassessed: "已完成·待测评",
    review: "建议复习",
    not_started: "未开始",
    locked: "先修未满足",
  }[status];
}

function actionLabelForNode(node: CourseKnowledgeNode) {
  const status = statusForNode(node);
  if (status === "locked") return "先修未满足";
  if (status === "completed_unassessed") return "去测评";
  if (status === "review") return "开始复习";
  if (status === "mastered") return "查看结果";
  if (status === "learning") return "继续学习";
  return "开始学习";
}

function runNodeAction(node: CourseKnowledgeNode) {
  const status = statusForNode(node);
  if (status === "locked") {
    selectNode(node);
    completeError.value = `请先完成：${node.prerequisites.map((id) => knowledgeTitle(id)).join("、")}`;
    return;
  }
  selectNode(node);
  if (status === "completed_unassessed") {
    void openAssessment(node);
    return;
  }
  if (status === "mastered") {
    void router.push({ path: "/assessment", query: { kp: node.id, mode: "result" } });
    return;
  }
  void openLearning(node);
}

function primaryAction() {
  if (!selectedNode.value) return;
  if (selectedStatus.value === "completed_unassessed") {
    void openAssessment(selectedNode.value);
    return;
  }
  void openLearning(selectedNode.value);
}

function learningProgressForNode(node: CourseKnowledgeNode) {
  return path.run?.learning_progress?.concept_id === node.id ? path.run.learning_progress : null;
}

function recentRank(node: CourseKnowledgeNode) {
  const record = learningRecords.records.find((item) => item.knowledgeNodeId === node.id);
  return record ? new Date(record.occurredAt).getTime() : 0;
}

function shortDate(value?: string | null) {
  if (!value) return "暂无";
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function onNodeKeydown(event: KeyboardEvent, node: CourseKnowledgeNode) {
  const index = filteredNodes.value.findIndex((item) => item.id === node.id);
  if (event.key === "Enter") {
    selectNode(node);
    return;
  }
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
  event.preventDefault();
  const next = filteredNodes.value[index + (event.key === "ArrowDown" ? 1 : -1)];
  if (next) selectNode(next);
}

function handleDetailKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") closeDetail();
}

onMounted(() => {
  window.addEventListener("keydown", handleDetailKeydown);
});

onUnmounted(() => {
  window.removeEventListener("keydown", handleDetailKeydown);
});

function statusPercent(node: CourseKnowledgeNode) {
  const progress = path.run?.learning_progress?.concept_id === node.id ? path.run.learning_progress.lecture_progress : null;
  if (typeof progress === "number") return Math.round(progress * 100);
  const mastery = masteryForNode(node);
  if (typeof mastery === "number") return Math.round(mastery * 100);
  return 0;
}

function resourcesForNode(node?: CourseKnowledgeNode | null, kind: ResourceKind = "all") {
  if (!node) return [];
  return [
    { kind: "lecture" as const, label: "讲义", title: `${node.title}工作原理`, meta: `${node.lectures}份讲义 · ${node.estimatedMinutes}分钟`, icon: Play },
    { kind: "example" as const, label: "示例", title: `${node.title}可视化示例`, meta: `${node.examples}个示例`, icon: FileText },
    { kind: "practice" as const, label: "练习", title: `${node.title}练习`, meta: `${node.exercises}道题`, icon: BookOpen },
    { kind: "assessment" as const, label: "测评", title: `${node.title}单元测评`, meta: `${node.assessments}套测评`, icon: FileCheck2 },
  ].filter((item) => kind === "all" || item.kind === kind);
}

function sectionTitle(node: CourseKnowledgeNode) {
  if (node.id.includes("convolution")) return "卷积与特征图";
  if (node.id.includes("gradient")) return "优化与梯度";
  if (node.id.includes("loss")) return "目标函数";
  if (node.id.includes("padding")) return "结构参数";
  return "课程知识";
}

watch(() => route.hash, (hash) => {
  if (hash === "#learning-resources") activeTab.value = "resources";
});

watch([searchQuery, resourceKind, statusFilter, sortMode], () => {
  syncUrlState();
});
</script>

<template>
  <div id="knowledge-base" class="course-kb page-stack">
    <section class="kb-overview panel">
      <div class="course-meta">
        <div class="course-cover">
          <strong>卷积神经网络</strong>
          <span>CNN</span>
        </div>
        <div class="course-info">
          <button class="course-title-button" type="button" @click="selectCourse">
            <span>{{ courseKnowledgeBase.currentTrack }}</span>
            <ChevronDown :size="16" />
          </button>
          <p>{{ courseKnowledgeBase.subtitle }} · 6章 · {{ courseStats.total }}个知识点</p>
          <div class="course-progress-line">
            <span>课程进度</span>
            <div class="progress-track"><i :style="{ width: `${courseStats.progress}%` }" /></div>
            <b>{{ courseStats.progress }}%</b>
          </div>
        </div>
      </div>
      <div class="course-stats">
        <div class="course-stat"><span>已掌握</span><b>{{ courseStats.mastered }}</b></div>
        <div class="course-stat"><span>学习中</span><b>{{ courseStats.learning }}</b></div>
        <div class="course-stat"><span>学习资源</span><b>{{ courseStats.resources }}</b></div>
        <div class="course-stat"><span>测评</span><b>{{ courseStats.assessments }}</b></div>
      </div>
      <div class="overview-actions">
        <button class="button button-secondary" type="button" @click="locateInGraph"><Network :size="17" />查看知识图谱</button>
        <button class="button button-primary" type="button" @click="openLearning()"><Play :size="17" />继续学习</button>
      </div>
    </section>

    <section class="kb-toolbar panel">
      <div class="kb-tabs" role="tablist" aria-label="课程知识库视图">
        <button :class="{ active: activeTab === 'catalog' }" type="button" @click="setActiveTab('catalog')">知识目录</button>
        <button :class="{ active: activeTab === 'resources' }" type="button" @click="setActiveTab('resources')">全部资源</button>
        <button :class="{ active: activeTab === 'favorites' }" type="button" @click="setActiveTab('favorites')">我的收藏</button>
      </div>
      <div class="kb-filters">
        <label class="kb-search">
          <Search :size="17" />
          <input v-model="searchQuery" type="search" placeholder="搜索知识点、讲义或练习" @keyup.enter="handleSearchEnter" />
        </label>
        <select v-model="resourceKind" aria-label="资源类型">
          <option value="all">全部资源类型</option>
          <option value="lecture">讲义</option>
          <option value="example">示例</option>
          <option value="practice">练习</option>
          <option value="assessment">测评</option>
        </select>
        <select v-model="statusFilter" aria-label="掌握状态">
          <option value="all">全部掌握状态</option>
          <option value="mastered">已掌握</option>
          <option value="learning">学习中</option>
          <option value="completed_unassessed">已完成待测评</option>
          <option value="review">建议复习</option>
          <option value="not_started">未开始</option>
          <option value="locked">先修未满足</option>
        </select>
        <select v-model="sortMode" aria-label="排序方式">
          <option value="course">按课程顺序</option>
          <option value="status">按状态优先</option>
          <option value="mastery_desc">掌握度从高到低</option>
          <option value="mastery_asc">掌握度从低到高</option>
          <option value="recent">按最近学习</option>
        </select>
      </div>
    </section>

    <section class="kb-workspace panel">
      <aside class="chapter-panel">
        <h3>课程目录</h3>
        <div class="chapter-list">
          <section v-for="item in chapterProgress" :key="item.chapter.id" class="chapter-group" :class="{ active: selectedChapterId === item.chapter.id }">
            <button type="button" @click="selectChapter(item.chapter)">
              <span>第{{ String(item.chapter.order).padStart(2, "0") }}章</span>
              <b>{{ item.chapter.title }}</b>
              <em>{{ item.completed }} / {{ item.total }}</em>
              <ChevronRight v-if="!expandedChapterIds.includes(item.chapter.id)" :size="15" @click.stop="toggleChapter(item.chapter.id)" />
              <ChevronDown v-else :size="15" @click.stop="toggleChapter(item.chapter.id)" />
            </button>
            <div v-if="expandedChapterIds.includes(item.chapter.id)" class="chapter-node-list">
              <button v-for="node in item.chapter.nodes" :key="node.id" :class="{ selected: selectedNodeId === node.id }" type="button" @click="selectNode(node)">
                <i :class="`status-${statusForNode(node)}`" />
                <span>{{ node.title }}</span>
              </button>
            </div>
          </section>
        </div>
      </aside>

      <main class="node-panel">
        <div class="node-panel-head">
          <div>
            <h3>{{ nodePanelTitle }}</h3>
            <p>{{ nodePanelSubtitle }}</p>
          </div>
          <b v-if="activeTab === 'resources'">{{ filteredResourceRows.length }}</b>
          <b v-else>{{ filteredNodes.length }} / {{ activeTab === "catalog" ? selectedChapter.nodes.length : allNodes.length }}</b>
        </div>
        <div v-if="activeTab === 'resources'" class="resource-table">
          <div class="resource-table-head"><span>资源名称</span><span>所属知识点</span><span>类型</span><span>操作</span></div>
          <article v-for="row in filteredResourceRows" :key="`${row.node.id}-${row.kind}`" class="resource-row" tabindex="0" @click="selectNode(row.node)" @keydown.enter="selectNode(row.node)">
            <span class="resource-name">
              <i :class="`resource-kind-${row.kind}`"><component :is="row.icon" :size="15" /></i>
              <b>{{ row.title }}</b>
              <small>{{ row.chapter?.title || "课程章节" }} · {{ row.meta }}</small>
            </span>
            <span>{{ row.node.title }}</span>
            <span>{{ row.label }}</span>
            <button class="node-actions" type="button" @click.stop="selectNode(row.node); openResource(row)">打开资源</button>
          </article>
          <div v-if="!filteredResourceRows.length" class="state-block">
            <strong>没有符合条件的资源</strong>
            <p>请调整搜索关键词或资源类型。</p>
            <button class="text-link" type="button" @click="clearFilters">清除筛选</button>
          </div>
        </div>
        <div v-else class="node-table">
          <div class="node-table-head"><span>知识点</span><span>掌握状态</span><span>资源</span><span>操作</span></div>
          <article
            v-for="node in filteredNodes"
            :key="node.id"
            class="node-row"
            :class="{ selected: selectedNodeId === node.id }"
            tabindex="0"
            @click="selectNode(node)"
            @keydown="onNodeKeydown($event, node)"
          >
            <span class="node-name"><i :class="`status-${statusForNode(node)}`" />{{ node.title }}</span>
            <span class="node-status">
              <b>{{ statusLabel(statusForNode(node)) }}</b>
              <em>{{ statusPercent(node) ? `${statusPercent(node)}%` : "待评估" }}</em>
              <small><i :style="{ width: `${statusPercent(node)}%` }" /></small>
            </span>
            <span class="node-resources">{{ node.lectures }}份讲义 · {{ node.examples }}个示例 · {{ node.exercises }}道练习</span>
            <button class="node-actions" type="button" :disabled="statusForNode(node) === 'locked'" :title="statusForNode(node) === 'locked' ? `请先完成：${node.prerequisites.map((id) => knowledgeTitle(id)).join('、')}` : undefined" @click.stop="runNodeAction(node)">
              {{ actionLabelForNode(node) }}
            </button>
          </article>
          <div v-if="!filteredNodes.length" class="state-block">
            <strong>{{ activeTab === "favorites" ? "还没有收藏内容" : "没有符合条件的知识点" }}</strong>
            <p>{{ activeTab === "favorites" ? "在知识点右侧点击收藏，即可在这里快速找回。" : "请调整搜索关键词、资源类型或掌握状态。" }}</p>
            <button class="text-link" type="button" @click="clearFilters">清除筛选</button>
          </div>
        </div>
        <div class="kb-recommend">
          <BookOpen :size="20" />
          <span><b>本章学习建议：</b>建议先完成「{{ selectedNode?.title }}」，再进入后续知识点。</span>
          <button class="text-link" type="button" @click="locateInGraph">查看推荐依据 <ChevronRight :size="15" /></button>
        </div>
      </main>

      <aside class="detail-panel" :class="{ 'is-open': detailOpen }" v-if="selectedNode" @keydown="handleDetailKeydown">
        <div class="detail-scroll">
          <div class="detail-header">
            <div>
              <h3>{{ selectedNode.title }}</h3>
              <span class="status-pill" :class="{ 'status-pill-success': selectedStatus === 'mastered', 'status-pill-warning': selectedStatus === 'review', 'status-pill-pending': selectedStatus === 'completed_unassessed' }">{{ statusLabel(selectedStatus) }}</span>
            </div>
            <button class="favorite-button" type="button" :aria-label="favoriteIds.includes(selectedNode.id) ? '取消收藏知识点' : '收藏知识点'" @click="toggleFavorite(selectedNode.id)">
              <Bookmark :size="20" :fill="favoriteIds.includes(selectedNode.id) ? 'currentColor' : 'none'" />
            </button>
            <button class="detail-close" type="button" aria-label="关闭详情" @click="closeDetail">
              <X :size="18" />
            </button>
          </div>

          <section class="detail-section">
            <h4>掌握状态</h4>
            <div class="detail-metrics">
              <span>当前状态 <b>{{ statusLabel(selectedStatus) }}</b></span>
              <span>掌握度 <b>{{ selectedMastery === null ? "待评估" : `${Math.round(selectedMastery * 100)}%` }}</b></span>
              <span>最近学习 <b>{{ shortDate(selectedRecentRecord?.occurredAt) }}</b></span>
              <span>最近测评 <b>{{ shortDate(learningRecords.records.find((record) => record.knowledgeNodeId === selectedNode.id && record.type === "assessment_completed")?.occurredAt) }}</b></span>
            </div>
          </section>

          <section class="detail-section">
            <h4>学习目标</h4>
            <p>{{ selectedNode.summary }}</p>
          </section>

          <section class="detail-section">
            <h4>先修知识</h4>
            <div class="relation-tags">
              <button v-for="id in selectedNode.prerequisites" :key="id" type="button" @click="selectNode(allNodes.find((node) => node.id === id) || selectedNode)">
                {{ knowledgeTitle(id) }}
              </button>
              <span v-if="!selectedNode.prerequisites.length">无先修要求</span>
            </div>
          </section>

          <section class="detail-section">
            <h4>完成后解锁</h4>
            <div class="relation-tags">
              <button v-for="node in unlockedBySelected" :key="node.id" type="button" @click="selectNode(node)">
                {{ node.title }}
              </button>
              <span v-if="!unlockedBySelected.length">后续综合任务</span>
            </div>
          </section>

          <section class="detail-section detail-resource-section">
            <div class="detail-tabs">
              <button
                v-for="kind in (['lecture', 'example', 'practice', 'assessment'] as ResourceKind[])"
                :key="kind"
                type="button"
                :class="{ active: activeResourceTab === kind }"
                @click="setResourceTab(kind)"
              >
                {{ resourceTabLabel(kind) }} {{ resourceCount(selectedNode, kind) }}
              </button>
            </div>
            <div id="learning-resources" class="resource-lines">
              <article v-for="item in selectedResources" :key="item.kind" tabindex="0" @click="openResource(item)" @keydown.enter="openResource(item)">
                <span :class="`resource-kind-${item.kind}`"><component :is="item.icon" :size="16" /></span>
                <div><b>{{ item.title }}</b><small>{{ item.label }} · {{ item.meta }} · {{ contentCompleted ? "已完成" : "未完成" }}</small></div>
                <button class="icon-button" type="button" aria-label="打开资源" @click.stop="openResource(item)">
                  <ChevronRight :size="17" />
                </button>
              </article>
              <div v-if="!selectedResources.length" class="state-block state-block-small">
                <strong>当前知识点暂无此类资源</strong>
                <p>请切换其他资源类型继续浏览。</p>
              </div>
            </div>
          </section>

          <p v-if="notice" class="learning-notice">{{ notice }}</p>
          <p v-if="completeError" class="inline-error">{{ completeError }}</p>
        </div>

        <div class="detail-actions">
          <button class="button button-primary button-full" type="button" :disabled="selectedStatus === 'locked'" @click="primaryAction">
            <Play :size="17" />{{ primaryActionLabel }}
          </button>
          <button class="button button-secondary button-full" type="button" :disabled="!canUseGeneratedResource || completeSubmitting" @click="completeLearningContent">
            <CheckCircle2 :size="17" />{{ completeButtonLabel }}
          </button>
          <button class="text-link detail-graph-link" type="button" @click="locateInGraph"><Network :size="16" />在知识图谱中定位</button>
        </div>
      </aside>
    </section>
  </div>
</template>

<style scoped>
.course-kb {
  --kb-heading: #10233f;
  --kb-body: #52657d;
  --kb-muted: #7a8ca5;
  --kb-primary: #2f6feb;
  --kb-primary-soft: #eef4ff;
  --kb-border: #dce5f0;
  --kb-divider: #e8eef5;
  width: 100%;
  max-width: 100%;
  overflow-x: clip;
}
.course-kb,
.course-kb * {
  box-sizing: border-box;
}
.course-kb :is(button, input, select) {
  max-width: 100%;
}
.course-kb :is(button, a, input, select):focus-visible {
  outline: 3px solid rgba(47, 111, 235, .18);
  outline-offset: 2px;
}
.kb-overview {
  display: grid;
  grid-template-columns: minmax(420px, 1.05fr) minmax(360px, .95fr) minmax(240px, auto);
  gap: 24px;
  align-items: center;
  /* 顶部课程概览收窄一些，保留两侧呼吸空间；下方工作区不受影响。 */
  width: 100%;
  margin-inline: 0;
  padding: 14px 24px 16px; /* 只压缩上下留白，让顶部块更扁一点 */
}
.course-meta {
  display: grid;
  grid-template-columns: 166px minmax(0, 1fr);
  gap: 20px;
  align-items: center;
  min-width: 0;
}
.course-cover {
  display: grid;
  align-content: center;
  width: 166px;
  height: 166px;
  padding: 20px;
  color: #fff;
  background:
    radial-gradient(circle at 75% 32%, rgba(86, 156, 255, .34), transparent 28%),
    linear-gradient(145deg, #0e2457, #132f73);
  border-radius: 8px;
  overflow: hidden;
}
.course-cover strong {
  display: -webkit-box;
  overflow: hidden;
  font-size: 22px;
  line-height: 1.35;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}
.course-cover span { margin-top: 8px; color: #bdd2ff; font-weight: 800; }
.course-info {
  min-width: 0;
}
.course-title-button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  padding: 0;
  color: var(--kb-heading);
  background: transparent;
  border: 0;
  font-size: 24px;
  font-weight: 800;
  line-height: 1.25;
  text-align: left;
}
.course-title-button span {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.course-meta p { margin: 8px 0 22px; color: var(--kb-body); font-size: 13px; }
.course-progress-line { display: grid; grid-template-columns: auto minmax(120px, 260px) 40px; gap: 12px; align-items: center; color: var(--kb-muted); font-size: 13px; }
.course-progress-line .progress-track, .node-status small { height: 7px; overflow: hidden; background: #edf2f7; border-radius: 99px; }
.course-progress-line i, .node-status small i { display: block; height: 100%; background: var(--kb-primary); border-radius: inherit; }
.course-progress-line b { color: var(--kb-body); }
.course-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(72px, 1fr));
  min-width: 0;
}
.course-stat { min-height: 72px; padding: 0 16px; border-left: 1px solid var(--kb-divider); }
.course-stat span, .course-stat b { display: block; text-align: center; }
.course-stat span { color: var(--kb-muted); font-size: 12px; }
.course-stat b { margin-top: 9px; color: var(--kb-heading); font-size: 25px; }
.overview-actions { display: grid; grid-template-columns: 1fr; gap: 12px; min-width: 0; }
.overview-actions .button { justify-content: center; width: 100%; min-height: 42px; white-space: nowrap; }
.kb-toolbar {
  display: grid;
  grid-template-columns: minmax(280px, 420px) minmax(0, 1fr);
  gap: 14px 18px;
  align-items: center;
  width: 100%;
  padding: 12px 18px;
}
.kb-tabs { display: grid; grid-template-columns: repeat(3, 1fr); align-self: stretch; }
.kb-tabs button {
  min-height: 42px;
  color: var(--kb-body);
  background: transparent;
  border: 0;
  border-bottom: 2px solid transparent;
  font-size: 14px;
  font-weight: 800;
}
.kb-tabs button.active { color: var(--kb-primary); border-bottom-color: var(--kb-primary); }
.kb-filters {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) repeat(3, minmax(136px, 168px));
  gap: 12px;
  min-width: 0;
}
.kb-search, .kb-toolbar select {
  display: flex;
  align-items: center;
  gap: 9px;
  height: 42px;
  min-width: 0;
  padding: 0 13px;
  color: var(--kb-muted);
  background: #fff;
  border: 1px solid var(--kb-border);
  border-radius: 8px;
}
.kb-search input, .kb-toolbar select { width: 100%; min-width: 0; color: var(--kb-heading); outline: 0; }
.kb-search input { border: 0; background: transparent; }
.kb-workspace {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr) 400px;
  gap: 0;
  width: 100%;
  max-width: 100%;
  height: clamp(360px, calc(100vh - 426px), 680px);
  min-height: 0;
  padding: 0;
  overflow: hidden;
}
.chapter-panel, .node-panel, .detail-panel {
  min-width: 0;
  max-width: 100%;
  padding: 22px;
}
.chapter-panel,
.node-panel {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}
.chapter-panel, .node-panel { border-right: 1px solid var(--kb-divider); }
.chapter-panel h3, .node-panel h3, .detail-panel h3 { margin: 0 0 14px; color: var(--kb-heading); }
.chapter-list { display: grid; gap: 7px; }
.chapter-group > button {
  display: grid;
  grid-template-columns: 60px minmax(0, 1fr) 42px 18px;
  gap: 8px;
  align-items: center;
  width: 100%;
  min-height: 48px;
  padding: 0 10px;
  color: var(--kb-body);
  background: transparent;
  border: 0;
  border-radius: 8px;
  text-align: left;
}
.chapter-group.active > button { color: var(--kb-primary); background: var(--kb-primary-soft); box-shadow: inset 3px 0 0 var(--kb-primary); }
.chapter-group b {
  display: -webkit-box;
  overflow: hidden;
  font-size: 13px;
  line-height: 1.35;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.chapter-group span, .chapter-group em { color: inherit; font-size: 12px; font-style: normal; }
.chapter-node-list { display: grid; gap: 4px; margin: 6px 0 8px 18px; padding-left: 10px; border-left: 1px solid var(--kb-divider); }
.chapter-node-list button {
  display: flex;
  align-items: center;
  gap: 9px;
  min-height: 42px;
  padding: 0 10px;
  color: var(--kb-body);
  background: transparent;
  border: 0;
  border-radius: 8px;
  text-align: left;
}
.chapter-node-list button.selected { color: var(--kb-primary); background: var(--kb-primary-soft); font-weight: 800; }
.chapter-node-list span {
  display: -webkit-box;
  overflow: hidden;
  line-height: 1.35;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.status-mastered, .status-learning, .status-review, .status-not_started, .status-locked {
  display: inline-block;
  width: 10px;
  height: 10px;
  flex: 0 0 auto;
  border: 2px solid currentColor;
  border-radius: 50%;
}
.status-mastered { color: #16a36a; background: #16a36a; }
.status-learning { color: var(--kb-primary); background: var(--kb-primary); }
.status-review { color: #d98b20; background: #fff; }
.status-not_started { color: var(--kb-primary); background: #fff; }
.status-locked { color: #94a3b8; background: #eef2f7; }
.node-panel-head { display: flex; justify-content: space-between; gap: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--kb-divider); }
.node-panel-head > div { min-width: 0; }
.node-panel-head p { margin: 4px 0 0; color: var(--kb-body); font-size: 13px; }
.node-panel-head b { color: var(--kb-heading); }
.node-table, .resource-table { display: grid; }
.node-table-head, .node-row,
.resource-table-head, .resource-row {
  display: grid;
  grid-template-columns: minmax(150px, 1fr) minmax(150px, .9fr) minmax(190px, 1.15fr) 112px;
  gap: 12px;
  align-items: center;
  min-width: 0;
}
.resource-table-head,
.node-table-head { min-height: 48px; color: var(--kb-muted); border-bottom: 1px solid var(--kb-divider); font-size: 12px; }
.resource-table-head,
.resource-row {
  grid-template-columns: minmax(220px, 1fr) minmax(120px, 180px) 82px 112px;
}
.node-row,
.resource-row {
  min-height: 68px;
  padding: 0;
  color: var(--kb-body);
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--kb-divider);
  text-align: left;
}
.node-row > *,
.resource-row > * {
  min-width: 0;
  max-width: 100%;
}
.node-row:focus-visible,
.resource-row:focus-visible {
  outline: 3px solid rgba(47, 111, 235, .16);
  outline-offset: -3px;
}
.node-row:hover, .node-row.selected, .resource-row:hover { background: #f3f7ff; }
.node-name {
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  overflow: hidden;
  color: var(--kb-heading);
  font-weight: 800;
  line-height: 1.45;
  overflow-wrap: anywhere;
}
.resource-name {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  column-gap: 10px;
  align-items: center;
}
.resource-name i {
  display: grid;
  grid-row: span 2;
  place-items: center;
  width: 28px;
  height: 28px;
  color: #fff;
  border-radius: 6px;
  font-style: normal;
}
.resource-name b,
.resource-name small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.resource-name b { color: var(--kb-heading); font-size: 13px; }
.resource-name small { margin-top: 3px; color: var(--kb-muted); font-size: 12px; }
.node-status { display: grid; gap: 3px; }
.node-status b { color: var(--kb-body); font-size: 12px; }
.node-status em, .node-resources { color: var(--kb-muted); font-size: 12px; font-style: normal; }
.node-resources {
  display: -webkit-box;
  overflow: hidden;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.node-actions {
  display: flex;
  justify-content: center;
  min-height: 36px;
  width: 100%;
  align-items: center;
  padding: 0 10px;
  color: var(--kb-primary);
  background: #fff;
  border: 1px solid #cbdaf6;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 800;
  white-space: nowrap;
}
.node-actions:disabled {
  color: #94a3b8;
  background: #f8fafc;
  border-color: #e1e8f2;
  cursor: not-allowed;
}
.kb-recommend {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  margin-top: 18px;
  padding: 14px 16px;
  color: var(--kb-body);
  background: #f6f9ff;
  border: 1px solid var(--kb-divider);
  border-radius: 10px;
  font-size: 13px;
}
.kb-recommend svg { color: var(--kb-primary); }
.detail-panel {
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  height: 100%;
  max-height: 100%;
  min-height: 0;
  padding: 0;
  background: #fff;
}
.detail-scroll {
  min-width: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 22px 22px 12px;
}
.detail-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 40px;
  gap: 12px;
  align-items: start;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--kb-divider);
}
.favorite-button {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  color: var(--kb-heading);
  background: #fff;
  border: 1px solid var(--kb-border);
  border-radius: 10px;
}
.detail-close {
  display: none;
  place-items: center;
  width: 40px;
  height: 40px;
  color: var(--kb-muted);
  background: #fff;
  border: 1px solid var(--kb-border);
  border-radius: 10px;
}
.detail-panel h3 {
  margin-bottom: 10px;
  font-size: 22px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}
.status-pill-pending { color: #07828a; background: #e6fffb; }
.detail-mastery { display: block; margin: 10px 0 16px; color: var(--kb-body); font-size: 13px; }
.detail-mastery b { color: var(--kb-heading); }
.detail-panel p { margin: 13px 0; color: var(--kb-body); font-size: 13px; line-height: 1.8; }
.detail-section {
  min-width: 0;
  padding: 18px 0;
  border-bottom: 1px solid var(--kb-divider);
}
.detail-section h4 {
  margin: 0 0 10px;
  color: var(--kb-heading);
  font-size: 14px;
}
.detail-section p {
  overflow-wrap: anywhere;
}
.detail-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 12px;
}
.detail-metrics span,
.detail-metrics b {
  display: block;
  min-width: 0;
}
.detail-metrics span {
  color: var(--kb-muted);
  font-size: 12px;
}
.detail-metrics b {
  margin-top: 4px;
  color: var(--kb-heading);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.relation-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.relation-tags button,
.relation-tags span {
  min-height: 30px;
  padding: 6px 10px;
  color: var(--kb-body);
  background: #f7faff;
  border: 1px solid var(--kb-divider);
  border-radius: 8px;
  font-size: 12px;
}
.relation-tags button:hover {
  color: var(--kb-primary);
  border-color: #bfd1f4;
}
.detail-resource-section {
  padding-top: 24px;
}
.detail-tabs {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0;
  margin: 0;
  border-bottom: 1px solid var(--kb-divider);
}
.detail-tabs button {
  min-height: 42px;
  color: var(--kb-body);
  background: transparent;
  border: 0;
  border-bottom: 2px solid transparent;
  font-weight: 800;
}
.detail-tabs button.active { color: var(--kb-primary); border-bottom-color: var(--kb-primary); }
.resource-lines { display: grid; padding-bottom: 14px; }
.resource-lines article {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) 32px;
  gap: 10px;
  align-items: center;
  min-height: 58px;
  min-width: 0;
  border-bottom: 1px solid var(--kb-divider);
  cursor: pointer;
}
.resource-lines article > span {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  color: #fff;
  border-radius: 6px;
}
.resource-kind-lecture { background: var(--kb-primary); }
.resource-kind-example { background: #8b5cf6; }
.resource-kind-practice { background: #16a36a; }
.resource-kind-assessment { background: #d98b20; }
.resource-lines article > div { min-width: 0; }
.resource-lines b, .resource-lines small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.resource-lines b { color: var(--kb-heading); font-size: 13px; }
.resource-lines small { margin-top: 3px; color: var(--kb-muted); font-size: 12px; }
.detail-actions {
  display: grid;
  gap: 10px;
  padding: 14px 22px max(18px, env(safe-area-inset-bottom));
  background: linear-gradient(180deg, rgba(255,255,255,.92), #fff);
  border-top: 1px solid var(--kb-divider);
}
.detail-graph-link { justify-content: center; min-height: 36px; }
@media (max-width: 1700px) {
  .kb-overview {
    grid-template-columns: minmax(360px, 1fr) minmax(320px, .9fr);
  }
  .overview-actions {
    grid-column: 1 / -1;
    grid-template-columns: repeat(2, minmax(0, 180px));
    justify-content: end;
  }
  .kb-toolbar {
    grid-template-columns: 1fr;
  }
  .kb-filters {
    grid-template-columns: minmax(260px, 1fr) repeat(3, minmax(136px, 1fr));
  }
  .kb-workspace {
    grid-template-columns: 280px minmax(0, 1fr) 340px;
  }
  .chapter-panel,
  .node-panel {
    padding: 18px;
  }
  .node-table-head,
  .node-row {
    grid-template-columns: minmax(96px, 1fr) minmax(96px, .78fr) minmax(112px, .9fr) 92px;
    gap: 8px;
  }
  .resource-table-head,
  .resource-row {
    grid-template-columns: minmax(160px, 1fr) minmax(96px, 130px) 62px 92px;
    gap: 8px;
  }
  .node-actions {
    padding: 0 8px;
  }
}
@media (max-width: 1199px) {
  .kb-overview {
    grid-template-columns: 1fr;
    width: 100%;
  }
  .course-stats {
    border-top: 1px solid var(--kb-divider);
    padding-top: 14px;
  }
  .kb-filters {
    grid-template-columns: minmax(220px, 1fr) repeat(2, minmax(130px, 1fr));
  }
  .kb-filters select:last-child {
    grid-column: span 2;
  }
  .kb-workspace {
    grid-template-columns: 280px minmax(0, 1fr);
    overflow: visible;
  }
  .chapter-panel,
  .node-panel {
    max-height: none;
  }
  .detail-panel {
    position: fixed;
    inset: 0 0 0 auto;
    z-index: 80;
    width: min(420px, 100vw);
    max-height: 100svh;
    height: 100svh;
    min-height: 0;
    border-left: 1px solid var(--kb-divider);
    box-shadow: -18px 0 36px rgba(16, 35, 63, .14);
    transform: translateX(100%);
    transition: transform .22s ease;
  }
  .detail-panel.is-open {
    transform: translateX(0);
  }
  .detail-close {
    display: grid;
  }
  .detail-header {
    grid-template-columns: minmax(0, 1fr) 40px 40px;
  }
}
@media (max-width: 899px) {
  .kb-overview, .kb-toolbar, .kb-workspace { grid-template-columns: 1fr; }
  .kb-overview > * { grid-column: auto !important; }
  .course-meta {
    grid-template-columns: 1fr;
  }
  .course-cover {
    width: 100%;
    height: 116px;
  }
  .course-cover strong {
    max-width: 180px;
    font-size: 24px;
  }
  .course-meta {
    min-width: 0;
  }
  .course-title-button {
    align-items: flex-start;
    text-align: left;
    font-size: 23px;
    line-height: 1.25;
  }
  .course-progress-line {
    grid-template-columns: 56px minmax(0, 1fr) 42px;
  }
  .course-stat {
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: center;
    min-height: 54px;
    padding: 0 14px;
    border-left: 0;
    border-top: 1px solid var(--kb-divider);
  }
  .course-stat span,
  .course-stat b {
    margin: 0;
    text-align: left;
  }
  .course-stat b {
    text-align: right;
  }
  .overview-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }
  .kb-filters {
    grid-template-columns: 1fr;
  }
  .kb-filters select:last-child {
    grid-column: auto;
  }
  .chapter-panel, .node-panel { border-right: 0; border-bottom: 1px solid var(--kb-divider); }
  .node-table-head, .resource-table-head { display: none; }
  .node-row, .resource-row { grid-template-columns: 1fr; gap: 8px; padding: 12px; }
  .kb-recommend { grid-template-columns: 28px 1fr; }
  .kb-recommend .text-link { grid-column: 2; }
}
@media (max-width: 520px) {
  .overview-actions {
    grid-template-columns: 1fr;
  }
  .course-stats {
    grid-template-columns: repeat(2, 1fr);
  }
  .course-stat {
    min-height: 58px;
  }
  .detail-panel {
    width: 100vw;
  }
}
</style>
