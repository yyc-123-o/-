<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import {
  ArrowRight,
  Bookmark,
  BookmarkCheck,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Copy,
  ExternalLink,
  Filter,
  LayoutGrid,
  List,
  LoaderCircle,
  MoreHorizontal,
  Search,
  Sparkles,
  SlidersHorizontal,
  X,
} from "lucide-vue-next";
import {
  buildResourceCatalog,
  firstResourceForKnowledgePoint,
  type LearningResource,
  type LearningResourceDifficulty,
  type LearningResourceStatus,
  type LearningResourceType,
} from "@/utils/resourceCatalog";
import { courseKnowledgeBase } from "@/data/courseKnowledgeBase";
import { useLearnerStore } from "@/stores/learner";
import { useLearningPathStore } from "@/stores/learningPath";
import { useLearningRecordsStore, type LearningRecord } from "@/stores/learningRecords";

type ResourceCategory = "all" | LearningResourceType | "favorites" | "recent";
type SortMode = "updated" | "duration" | "course" | "status";
type ViewMode = "list" | "grid";
type SourceFilter = "all" | "course" | "recent";
type DateRange = "all" | "7" | "30" | "90" | "custom";
type YesNoFilter = "all" | "yes" | "no";
type ResourceDisplayStatus = LearningResourceStatus | "review";
type StatusVariant = "default" | "success" | "warning";

interface ResourceItem extends LearningResource {
  latestRecord: LearningRecord | null;
  origin: SourceFilter;
  statusView: ResourceDisplayStatus;
  statusLabel: string;
  statusVariant: StatusVariant;
  updatedStamp: number;
  updatedLabel: string;
  hasAttachment: boolean;
  learnable: boolean;
}

const route = useRoute();
const router = useRouter();
const learner = useLearnerStore();
const path = useLearningPathStore();
const learningRecords = useLearningRecordsStore();

const catalog = ref<LearningResource[]>([]);
const catalogReady = ref(false);
const catalogError = ref("");
const assistantOpen = ref(false);
const moreFiltersOpen = ref(false);
const activeMenuId = ref("");
const loadingHold = ref(true);
const notice = ref("");
const noticeTone = ref<"success" | "warning" | "info">("info");

const favoriteIds = ref<string[]>(readStoredIds("zhijing.learning-resources.favorites.v1"));
const laterIds = ref<string[]>(readStoredIds("zhijing.learning-resources.later.v1"));

const activeCategory = ref<ResourceCategory>("all");
const searchDraft = ref("");
const keyword = ref("");
const courseId = ref("all");
const chapterId = ref("all");
const knowledgePointId = ref("all");
const difficulty = ref<"all" | LearningResourceDifficulty>("all");
const status = ref<"all" | ResourceDisplayStatus>("all");
const sortMode = ref<SortMode>("updated");
const viewMode = ref<ViewMode>("list");
const page = ref(1);
const pageSize = ref(20);
const sourceFilter = ref<SourceFilter>("all");
const updateRange = ref<DateRange>("all");
const startDate = ref("");
const endDate = ref("");
const attachmentFilter = ref<YesNoFilter>("all");
const pathScopeFilter = ref<YesNoFilter>("all");

const searchTimer = ref<number | undefined>(undefined);
const syncingFromRoute = ref(false);
const pageSizes = [10, 20, 40];

const chapterOptions = computed(() => courseKnowledgeBase.chapters);
const knowledgePointOptions = computed(() => courseKnowledgeBase.chapters.flatMap((chapter) => chapter.nodes));
const courseOptions = computed(() => [{
  id: courseKnowledgeBase.id,
  title: courseKnowledgeBase.currentTrack || courseKnowledgeBase.title,
}]);

const currentPathIds = computed(() => new Set(path.nodes.map((node) => node.concept_id)));

const decoratedResources = computed<ResourceItem[]>(() => catalog.value.map((resource) => decorateResource(resource)));

const tabCounts = computed(() => {
  const items = decoratedResources.value;
  return {
    all: items.length,
    lecture: items.filter((item) => item.type === "lecture").length,
    video: items.filter((item) => item.type === "video").length,
    example: items.filter((item) => item.type === "example").length,
    practice: items.filter((item) => item.type === "practice").length,
    assessment: items.filter((item) => item.type === "assessment").length,
    favorites: items.filter((item) => favoriteIds.value.includes(item.id)).length,
    recent: items.filter((item) => Boolean(item.latestRecord)).length,
  };
});

const tabs = computed<Array<{ key: ResourceCategory; label: string; count: number }>>(() => ([
  { key: "all", label: "全部资源", count: tabCounts.value.all },
  { key: "lecture", label: "讲义", count: tabCounts.value.lecture },
  { key: "video", label: "视频", count: tabCounts.value.video },
  { key: "example", label: "示例", count: tabCounts.value.example },
  { key: "practice", label: "练习", count: tabCounts.value.practice },
  { key: "assessment", label: "测评", count: tabCounts.value.assessment },
  { key: "favorites", label: "我的收藏", count: tabCounts.value.favorites },
  { key: "recent", label: "最近学习", count: tabCounts.value.recent },
]));

const activeTabLabel = computed(() => tabs.value.find((tab) => tab.key === activeCategory.value)?.label || "全部资源");
const latestUpdateLabel = computed(() => {
  const stamps = decoratedResources.value.map((item) => item.updatedStamp).filter((stamp) => Number.isFinite(stamp) && stamp > 0);
  if (!stamps.length) return "暂无数据";
  return formatDate(new Date(Math.max(...stamps)));
});

const filteredResources = computed(() => {
  const text = keyword.value.trim().toLowerCase();
  const nodeIndexMap = new Map(knowledgePointOptions.value.map((node, index) => [node.id, index]));
  const chapterIndexMap = new Map(chapterOptions.value.map((chapter, index) => [chapter.id, index]));

  let items = decoratedResources.value.filter((item) => {
    const matchesCategory =
      activeCategory.value === "all"
      || activeCategory.value === "favorites"
      || activeCategory.value === "recent"
      || item.type === activeCategory.value;
    const matchesFavorites = activeCategory.value !== "favorites" || favoriteIds.value.includes(item.id);
    const matchesRecent = activeCategory.value !== "recent" || Boolean(item.latestRecord);
    const matchesCourse = courseId.value === "all" || item.courseId === courseId.value;
    const matchesChapter = chapterId.value === "all" || item.chapterId === chapterId.value;
    const matchesKnowledge = knowledgePointId.value === "all" || item.knowledgePointIds.includes(knowledgePointId.value);
    const matchesDifficulty = difficulty.value === "all" || item.difficulty === difficulty.value;
    const matchesStatus = status.value === "all" || item.statusView === status.value;
    const matchesSource = sourceFilter.value === "all" || item.origin === sourceFilter.value;
    const matchesAttachment = attachmentFilter.value === "all" || (attachmentFilter.value === "yes" ? item.hasAttachment : !item.hasAttachment);
    const matchesPath = pathScopeFilter.value === "all" || (pathScopeFilter.value === "yes" ? item.learnable : !item.learnable);
    const matchesDate = matchDateRange(item.updatedStamp);
    const searchable = [
      item.title,
      item.courseTitle,
      item.chapterTitle,
      item.knowledgePointTitle,
      item.typeLabel,
      item.statusLabel,
      item.updatedLabel,
    ].join(" ").toLowerCase();
    return matchesCategory && matchesFavorites && matchesRecent && matchesCourse && matchesChapter && matchesKnowledge && matchesDifficulty && matchesStatus && matchesSource && matchesAttachment && matchesPath && matchesDate && (!text || searchable.includes(text));
  });

  if (sortMode.value === "duration") {
    items = items.slice().sort((a, b) => {
      if (b.duration !== a.duration) return b.duration - a.duration;
      return b.updatedStamp - a.updatedStamp;
    });
  } else if (sortMode.value === "course") {
    items = items.slice().sort((a, b) => {
      const chapterDelta = (chapterIndexMap.get(a.chapterId) || 0) - (chapterIndexMap.get(b.chapterId) || 0);
      if (chapterDelta) return chapterDelta;
      const nodeA = nodeIndexMap.get(a.knowledgePointIds[0]) || 0;
      const nodeB = nodeIndexMap.get(b.knowledgePointIds[0]) || 0;
      if (nodeA !== nodeB) return nodeA - nodeB;
      return a.title.localeCompare(b.title, "zh-CN");
    });
  } else if (sortMode.value === "status") {
    items = items.slice().sort((a, b) => {
      const rankDelta = statusRank(a.statusView) - statusRank(b.statusView);
      if (rankDelta) return rankDelta;
      return b.updatedStamp - a.updatedStamp;
    });
  } else {
    items = items.slice().sort((a, b) => b.updatedStamp - a.updatedStamp);
  }

  return items;
});

const totalPages = computed(() => Math.max(1, Math.ceil(filteredResources.value.length / pageSize.value)));
const pageResources = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  return filteredResources.value.slice(start, start + pageSize.value);
});
const pageRangeText = computed(() => {
  const total = filteredResources.value.length;
  if (!total) return "0 项";
  const start = (page.value - 1) * pageSize.value + 1;
  const end = Math.min(page.value * pageSize.value, total);
  return `${start}-${end} / ${total}`;
});
const hasActiveFilters = computed(() =>
  activeCategory.value !== "all"
  || keyword.value.trim() !== ""
  || courseId.value !== "all"
  || chapterId.value !== "all"
  || knowledgePointId.value !== "all"
  || difficulty.value !== "all"
  || status.value !== "all"
  || sortMode.value !== "updated"
  || sourceFilter.value !== "all"
  || updateRange.value !== "all"
  || attachmentFilter.value !== "all"
  || pathScopeFilter.value !== "all"
  || viewMode.value !== "list"
  || pageSize.value !== 20,
);
const advancedFilterCount = computed(() => [
  chapterId.value,
  sourceFilter.value,
  updateRange.value,
  attachmentFilter.value,
  pathScopeFilter.value,
].filter((value) => value !== "all").length + (updateRange.value === "custom" && (startDate.value || endDate.value) ? 1 : 0));
const loading = computed(() => !catalogReady.value || learner.loading || path.loading || loadingHold.value);
const pageError = computed(() => catalogError.value || "");

function readStoredIds(key: string) {
  try {
    if (typeof window === "undefined") return [];
    const parsed = JSON.parse(localStorage.getItem(key) || "[]") as string[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function persistStoredIds(key: string, value: string[]) {
  if (typeof window === "undefined") return;
  localStorage.setItem(key, JSON.stringify(value));
}

function statusRank(value: ResourceDisplayStatus) {
  if (value === "completed") return 0;
  if (value === "learning") return 1;
  if (value === "review") return 2;
  return 3;
}

function statusLabel(value: ResourceDisplayStatus) {
  if (value === "completed") return "已完成";
  if (value === "learning") return "学习中";
  if (value === "review") return "建议复习";
  return "未开始";
}

function statusVariant(value: ResourceDisplayStatus): StatusVariant {
  if (value === "completed") return "success";
  if (value === "review") return "warning";
  return "default";
}

function formatDate(date: Date) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date).replaceAll("/", "-");
}

function parseString(value: unknown) {
  if (Array.isArray(value)) return String(value[0] || "");
  return String(value || "");
}

function parseNumber(value: unknown, fallback: number) {
  const parsed = Number(parseString(value));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function readCategory(value: unknown): ResourceCategory {
  const key = parseString(value) || "all";
  return ["all", "lecture", "video", "example", "practice", "assessment", "favorites", "recent"].includes(key)
    ? key as ResourceCategory
    : "all";
}

function readDifficulty(value: unknown) {
  const key = parseString(value);
  return ["basic", "standard", "advanced"].includes(key) ? key as LearningResourceDifficulty : "all";
}

function readStatus(value: unknown) {
  const key = parseString(value);
  return ["not_started", "learning", "completed", "review"].includes(key) ? key as ResourceDisplayStatus : "all";
}

function readSort(value: unknown): SortMode {
  const key = parseString(value);
  return ["updated", "duration", "course", "status"].includes(key) ? key as SortMode : "updated";
}

function readView(value: unknown): ViewMode {
  const key = parseString(value);
  return key === "grid" ? "grid" : "list";
}

function readSource(value: unknown): SourceFilter {
  const key = parseString(value);
  return ["all", "course", "recent"].includes(key) ? key as SourceFilter : "all";
}

function readDateRange(value: unknown): DateRange {
  const key = parseString(value);
  return ["all", "7", "30", "90", "custom"].includes(key) ? key as DateRange : "all";
}

function readYesNo(value: unknown): YesNoFilter {
  const key = parseString(value);
  return ["all", "yes", "no"].includes(key) ? key as YesNoFilter : "all";
}

function hydrateFromRoute() {
  syncingFromRoute.value = true;
  activeCategory.value = readCategory(route.query.category || route.query.type);
  searchDraft.value = parseString(route.query.keyword || route.query.q || "");
  keyword.value = searchDraft.value;
  courseId.value = parseString(route.query.courseId || "all") || "all";
  chapterId.value = parseString(route.query.chapterId || "all") || "all";
  knowledgePointId.value = parseString(route.query.knowledgePointId || route.query.kp || "all") || "all";
  difficulty.value = readDifficulty(route.query.difficulty);
  status.value = readStatus(route.query.status);
  sortMode.value = readSort(route.query.sort);
  viewMode.value = readView(route.query.view);
  page.value = parseNumber(route.query.page, 1);
  pageSize.value = pageSizes.includes(parseNumber(route.query.pageSize, 20)) ? parseNumber(route.query.pageSize, 20) : 20;
  sourceFilter.value = readSource(route.query.source || route.query.origin);
  updateRange.value = readDateRange(route.query.updatedRange || route.query.range);
  startDate.value = parseString(route.query.startDate || "");
  endDate.value = parseString(route.query.endDate || "");
  attachmentFilter.value = readYesNo(route.query.attachment || route.query.hasAttachment);
  pathScopeFilter.value = readYesNo(route.query.pathScope || route.query.learnable);
  if (page.value < 1) page.value = 1;
  if (!pageSizes.includes(pageSize.value)) pageSize.value = 20;
  window.requestAnimationFrame(() => {
    syncingFromRoute.value = false;
  });
}

function buildQuery() {
  const query: Record<string, string> = {};
  if (activeCategory.value !== "all") query.category = activeCategory.value;
  if (keyword.value.trim()) query.keyword = keyword.value.trim();
  if (courseId.value !== "all") query.courseId = courseId.value;
  if (chapterId.value !== "all") query.chapterId = chapterId.value;
  if (knowledgePointId.value !== "all") query.knowledgePointId = knowledgePointId.value;
  if (difficulty.value !== "all") query.difficulty = difficulty.value;
  if (status.value !== "all") query.status = status.value;
  if (sortMode.value !== "updated") query.sort = sortMode.value;
  if (viewMode.value !== "list") query.view = viewMode.value;
  if (page.value > 1) query.page = String(page.value);
  if (pageSize.value !== 20) query.pageSize = String(pageSize.value);
  if (sourceFilter.value !== "all") query.source = sourceFilter.value;
  if (updateRange.value !== "all") query.updatedRange = updateRange.value;
  if (updateRange.value === "custom" && startDate.value) query.startDate = startDate.value;
  if (updateRange.value === "custom" && endDate.value) query.endDate = endDate.value;
  if (attachmentFilter.value !== "all") query.attachment = attachmentFilter.value;
  if (pathScopeFilter.value !== "all") query.pathScope = pathScopeFilter.value;
  return query;
}

function querySignature(query: Record<string, string>) {
  return Object.keys(query).sort().map((key) => `${key}=${query[key]}`).join("&");
}

function syncRoute() {
  if (syncingFromRoute.value) return;
  const nextQuery = buildQuery();
  const currentQuery = normalizeQuery(route.query);
  if (querySignature(nextQuery) === querySignature(currentQuery)) return;
  void router.replace({ path: "/resources", query: nextQuery });
}

function normalizeQuery(query: Record<string, unknown>) {
  const result: Record<string, string> = {};
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    result[key] = Array.isArray(value) ? String(value[0] || "") : String(value);
  }
  return result;
}

function setCategory(category: ResourceCategory) {
  activeCategory.value = category;
}

function handleSearchInput(value: string) {
  searchDraft.value = value;
  if (searchTimer.value) window.clearTimeout(searchTimer.value);
  searchTimer.value = window.setTimeout(() => {
    keyword.value = value;
  }, 360);
}

function clearSearch() {
  searchDraft.value = "";
  keyword.value = "";
}

function clearFilters() {
  activeCategory.value = "all";
  searchDraft.value = "";
  keyword.value = "";
  courseId.value = "all";
  chapterId.value = "all";
  knowledgePointId.value = "all";
  difficulty.value = "all";
  status.value = "all";
  sortMode.value = "updated";
  viewMode.value = "list";
  page.value = 1;
  pageSize.value = 20;
  sourceFilter.value = "all";
  updateRange.value = "all";
  startDate.value = "";
  endDate.value = "";
  attachmentFilter.value = "all";
  pathScopeFilter.value = "all";
  moreFiltersOpen.value = false;
}

function toggleFavorite(resource: ResourceItem) {
  favoriteIds.value = favoriteIds.value.includes(resource.id)
    ? favoriteIds.value.filter((id) => id !== resource.id)
    : [...favoriteIds.value, resource.id];
  persistStoredIds("zhijing.learning-resources.favorites.v1", favoriteIds.value);
}

function toggleLater(resource: ResourceItem) {
  laterIds.value = laterIds.value.includes(resource.id)
    ? laterIds.value.filter((id) => id !== resource.id)
    : [...laterIds.value, resource.id];
  persistStoredIds("zhijing.learning-resources.later.v1", laterIds.value);
  showNotice(laterIds.value.includes(resource.id) ? "已加入稍后学习" : "已从稍后学习中移除", "success");
}

function openResource(resource: ResourceItem) {
  const query: Record<string, string> = { from: "resources" };
  if (activeCategory.value !== "all") query.category = activeCategory.value;
  void router.push({ path: `/learn/${resource.id}`, query });
}

function openResourceDetail(resource: ResourceItem) {
  void router.push({ path: `/resources/${resource.id}`, query: { from: "resources" } });
}

async function copyResourceLink(resource: ResourceItem) {
  const target = router.resolve({ path: `/resources/${resource.id}` });
  const url = new URL(target.href, window.location.origin).toString();
  try {
    await navigator.clipboard.writeText(url);
    showNotice("资源链接已复制", "success");
  } catch {
    showNotice("复制失败，请手动复制地址栏链接", "warning");
  }
}

function toggleMoreMenu(id: string) {
  activeMenuId.value = activeMenuId.value === id ? "" : id;
}

function closeMenus(event?: MouseEvent) {
  const target = event?.target as HTMLElement | null;
  if (target?.closest(".resource-more-button") || target?.closest(".resource-advanced")) return;
  if (target?.closest(".resource-menu") || target?.closest(".resource-assistant")) return;
  activeMenuId.value = "";
  if (moreFiltersOpen.value && !target?.closest(".resource-advanced") && !target?.closest(".resource-more-button")) {
    moreFiltersOpen.value = false;
  }
}

function openAssistant() {
  assistantOpen.value = true;
}

function closeAssistant() {
  assistantOpen.value = false;
}

function showNotice(text: string, tone: "success" | "warning" | "info" = "info") {
  notice.value = text;
  noticeTone.value = tone;
  window.setTimeout(() => {
    if (notice.value === text) notice.value = "";
  }, 2400);
}

function resourceLearningAmount(resource: ResourceItem) {
  if (resource.type === "assessment" || resource.type === "practice") {
    return resource.questionCount ? `${resource.questionCount} 题` : `${resource.duration} 分钟`;
  }
  return `${resource.duration} 分钟`;
}

function resourceOriginLabel(resource: ResourceItem) {
  return resource.origin === "recent" ? "最近学习" : "课程知识库";
}

function statusClass(resource: ResourceItem) {
  if (resource.statusVariant === "success") return "status-pill-success";
  if (resource.statusVariant === "warning") return "status-pill-warning";
  return "";
}

function decorateResource(resource: LearningResource): ResourceItem {
  const latestRecord = latestRecordForResource(resource);
  const nodeId = resource.knowledgePointIds[0] || "";
  const currentNodeId = path.currentNode?.concept_id || path.run?.learning_progress?.concept_id || "";
  const mastery = learner.profile?.knowledge_mastery?.points?.[nodeId]?.mastery;
  const updatedStamp = latestRecord ? new Date(latestRecord.occurredAt).getTime() : new Date(resource.updatedAt).getTime();
  let statusView: ResourceDisplayStatus = resource.status;

  if (latestRecord) {
    if (latestRecord.type === "resource_started") statusView = "learning";
    else if (latestRecord.type === "resource_completed" || latestRecord.type === "knowledge_completed" || latestRecord.type === "assessment_completed") statusView = "completed";
    else if (latestRecord.type === "review_completed") statusView = "review";
  } else if (nodeId && currentPathIds.value.has(nodeId) && currentNodeId === nodeId) {
    statusView = "learning";
  } else if (typeof mastery === "number" && mastery < 0.6) {
    statusView = "review";
  }

  return {
    ...resource,
    latestRecord,
    origin: latestRecord ? "recent" : "course",
    statusView,
    statusLabel: statusLabel(statusView),
    statusVariant: statusVariant(statusView),
    updatedStamp,
    updatedLabel: formatDate(new Date(updatedStamp)),
    hasAttachment: resource.questionCount > 0,
    learnable: Boolean(currentPathIds.value.has(nodeId) || latestRecord),
  };
}

function latestRecordForResource(resource: LearningResource) {
  const nodeId = resource.knowledgePointIds[0];
  const direct = learningRecords.records.find((record) => record.resourceId === resource.id);
  if (direct) return direct;
  if (!nodeId) return null;
  const matched = learningRecords.records.find((record) =>
    record.knowledgeNodeId === nodeId
    && ["resource_started", "resource_completed", "knowledge_completed", "assessment_completed", "review_completed"].includes(record.type),
  );
  return matched || null;
}

function matchDateRange(stamp: number) {
  if (updateRange.value === "all") return true;
  if (updateRange.value === "custom") {
    const start = startDate.value ? new Date(startDate.value).getTime() : Number.NEGATIVE_INFINITY;
    const end = endDate.value ? new Date(`${endDate.value}T23:59:59`).getTime() : Number.POSITIVE_INFINITY;
    return stamp >= start && stamp <= end;
  }
  const days = Number(updateRange.value);
  const threshold = Date.now() - days * 24 * 60 * 60 * 1000;
  return stamp >= threshold;
}

function changePage(nextPage: number) {
  page.value = Math.min(Math.max(1, nextPage), totalPages.value);
}

function changePageSize(nextSize: number) {
  pageSize.value = pageSizes.includes(nextSize) ? nextSize : 20;
}

function reloadCatalog() {
  catalogError.value = "";
  try {
    catalog.value = buildResourceCatalog();
  } catch (error) {
    catalogError.value = error instanceof Error ? error.message : "资源加载失败";
  }
  loadingHold.value = false;
}

onMounted(() => {
  reloadCatalog();
  hydrateFromRoute();
  document.addEventListener("click", closeMenus);
  window.requestAnimationFrame(() => {
    loadingHold.value = false;
  });
});

onUnmounted(() => {
  document.removeEventListener("click", closeMenus);
  if (searchTimer.value) window.clearTimeout(searchTimer.value);
});

watch(() => route.fullPath, hydrateFromRoute);

watch([
  activeCategory,
  keyword,
  courseId,
  chapterId,
  knowledgePointId,
  difficulty,
  status,
  sortMode,
  viewMode,
  sourceFilter,
  updateRange,
  startDate,
  endDate,
  attachmentFilter,
  pathScopeFilter,
], () => {
  if (syncingFromRoute.value) return;
  if (page.value !== 1) {
    page.value = 1;
    return;
  }
  syncRoute();
});

watch([page, pageSize], () => {
  if (syncingFromRoute.value) return;
  syncRoute();
});

watch(favoriteIds, (value) => {
  persistStoredIds("zhijing.learning-resources.favorites.v1", value);
}, { deep: true });

watch(laterIds, (value) => {
  persistStoredIds("zhijing.learning-resources.later.v1", value);
}, { deep: true });

watch(filteredResources, () => {
  if (page.value > totalPages.value) page.value = totalPages.value;
});
</script>

<template>
  <div class="learning-resources page-stack">
    <section class="resource-page-hero">
      <div class="resource-page-hero__copy">
        <p class="eyebrow">智数助手 / 资源与测评 / 学习资源</p>
        <h2>学习资源</h2>
        <p class="resource-page-hero__subtitle">跨课程查找讲义、视频、示例、练习与测评资源。</p>
      </div>
      <div class="resource-page-hero__meta">
        <div class="resource-page-hero__update">
          <span class="resource-page-hero__update-label">最近更新</span>
          <strong>{{ latestUpdateLabel }}</strong>
        </div>
        <button class="text-link resource-help-button" type="button" @click="openAssistant">
          使用帮助 <ArrowRight :size="15" />
        </button>
      </div>
    </section>

    <p v-if="notice" class="resource-notice" :class="`is-${noticeTone}`">{{ notice }}</p>

    <section v-if="pageError" class="panel resource-error">
      <div class="resource-state">
        <div class="resource-state__icon"><X :size="20" /></div>
        <strong>资源加载失败</strong>
        <p>请检查网络后重试。</p>
        <button class="button button-secondary" type="button" @click="reloadCatalog">
          <LoaderCircle :size="16" />
          重新加载
        </button>
      </div>
    </section>

    <section v-else-if="loading" class="panel resource-loading">
      <div class="resource-skeleton resource-skeleton__tabs">
        <span v-for="n in 8" :key="`tab-${n}`" />
      </div>
      <div class="resource-skeleton resource-skeleton__bar">
        <span />
        <span />
        <span />
        <span />
        <span />
        <span />
      </div>
      <div class="resource-skeleton resource-skeleton__table">
        <span v-for="n in 5" :key="`line-${n}`" />
      </div>
    </section>

    <section v-else class="panel resource-browser">
      <nav class="resource-category-tabs" aria-label="资源分类">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="resource-category-tab"
          :class="{ active: activeCategory === tab.key }"
          :aria-selected="activeCategory === tab.key"
          @click="setCategory(tab.key)"
        >
          <span>{{ tab.label }}</span>
          <small>{{ tab.count }}</small>
        </button>
      </nav>

      <div class="resource-filter-bar">
        <label class="resource-filter resource-search">
          <Search :size="16" />
          <input v-model="searchDraft" type="search" placeholder="搜索资源名称、课程、知识点" @input="handleSearchInput(($event.target as HTMLInputElement).value)" />
          <button v-if="searchDraft" type="button" class="resource-inline-clear" aria-label="清空搜索" @click="clearSearch">
            <X :size="14" />
          </button>
        </label>

        <label class="resource-filter">
          <span>全部课程</span>
          <select v-model="courseId">
            <option value="all">全部课程</option>
            <option v-for="course in courseOptions" :key="course.id" :value="course.id">{{ course.title }}</option>
          </select>
        </label>

        <label class="resource-filter">
          <span>全部知识点</span>
          <select v-model="knowledgePointId">
            <option value="all">全部知识点</option>
            <option v-for="node in knowledgePointOptions" :key="node.id" :value="node.id">{{ node.title }}</option>
          </select>
        </label>

        <label class="resource-filter">
          <span>全部难度</span>
          <select v-model="difficulty">
            <option value="all">全部难度</option>
            <option value="basic">基础</option>
            <option value="standard">标准</option>
            <option value="advanced">进阶</option>
          </select>
        </label>

        <label class="resource-filter">
          <span>学习状态</span>
          <select v-model="status">
            <option value="all">全部状态</option>
            <option value="not_started">未开始</option>
            <option value="learning">学习中</option>
            <option value="completed">已完成</option>
            <option value="review">建议复习</option>
          </select>
        </label>

        <button class="resource-filter resource-more-button" type="button" :class="{ active: moreFiltersOpen, 'has-badge': advancedFilterCount > 0 }" @click.stop="moreFiltersOpen = !moreFiltersOpen">
          <SlidersHorizontal :size="16" />
          <span>更多筛选</span>
          <small v-if="advancedFilterCount > 0">{{ advancedFilterCount }}</small>
        </button>

        <label class="resource-filter resource-sort">
          <span>排序</span>
          <select v-model="sortMode">
            <option value="updated">最近更新</option>
            <option value="duration">学习量</option>
            <option value="course">课程结构</option>
            <option value="status">完成状态</option>
          </select>
        </label>
      </div>

      <div v-if="moreFiltersOpen" class="resource-advanced" @click.stop>
        <label class="resource-filter">
          <span>所属章节</span>
          <select v-model="chapterId">
            <option value="all">全部章节</option>
            <option v-for="chapter in chapterOptions" :key="chapter.id" :value="chapter.id">{{ chapter.title }}</option>
          </select>
        </label>

        <label class="resource-filter">
          <span>资源来源</span>
          <select v-model="sourceFilter">
            <option value="all">全部来源</option>
            <option value="course">课程知识库</option>
            <option value="recent">最近学习</option>
          </select>
        </label>

        <label class="resource-filter">
          <span>更新时间范围</span>
          <select v-model="updateRange">
            <option value="all">全部时间</option>
            <option value="7">最近 7 天</option>
            <option value="30">最近 30 天</option>
            <option value="90">最近 90 天</option>
            <option value="custom">自定义</option>
          </select>
        </label>

        <label class="resource-filter">
          <span>是否含附件</span>
          <select v-model="attachmentFilter">
            <option value="all">全部</option>
            <option value="yes">含附件</option>
            <option value="no">不含附件</option>
          </select>
        </label>

        <label class="resource-filter">
          <span>仅看当前路径资源</span>
          <select v-model="pathScopeFilter">
            <option value="all">全部资源</option>
            <option value="yes">仅当前路径</option>
            <option value="no">排除当前路径</option>
          </select>
        </label>

        <div v-if="updateRange === 'custom'" class="resource-date-range">
          <label class="resource-filter">
            <span>开始日期</span>
            <input v-model="startDate" type="date" />
          </label>
          <label class="resource-filter">
            <span>结束日期</span>
            <input v-model="endDate" type="date" />
          </label>
        </div>

        <div class="resource-advanced__actions">
          <button class="button button-secondary" type="button" @click="clearFilters">
            <X :size="16" />
            清除筛选
          </button>
          <button class="button button-primary" type="button" @click="moreFiltersOpen = false">
            完成
          </button>
        </div>
      </div>

      <div class="resource-result-header">
        <div class="resource-result-copy">
          <h3>{{ activeTabLabel }} · 共 {{ filteredResources.length }} 项</h3>
          <p>
            <span v-if="hasActiveFilters">已应用筛选条件</span>
            <span v-else>默认浏览全部资源</span>
          </p>
        </div>

        <div class="resource-result-actions">
          <button class="text-link" v-if="hasActiveFilters" type="button" @click="clearFilters">清除筛选</button>
          <div class="resource-view-switch" role="group" aria-label="切换视图">
            <button type="button" :class="{ active: viewMode === 'list' }" aria-label="列表视图" @click="viewMode = 'list'"><List :size="16" /></button>
            <button type="button" :class="{ active: viewMode === 'grid' }" aria-label="卡片视图" @click="viewMode = 'grid'"><LayoutGrid :size="16" /></button>
          </div>
        </div>
      </div>

      <div v-if="filteredResources.length === 0" class="resource-empty">
        <div class="resource-state">
          <div class="resource-state__icon"><Filter :size="22" /></div>
          <strong>{{ activeCategory === 'favorites' ? '还没有收藏资源' : activeCategory === 'recent' ? '暂时没有最近学习记录' : '没有找到匹配的资源' }}</strong>
          <p>{{ activeCategory === 'favorites' ? '收藏常用资源后，可以在这里快速找到它们。' : activeCategory === 'recent' ? '开始学习资源后，最近访问内容会显示在这里。' : '请尝试更换关键词或减少筛选条件。' }}</p>
          <button class="button button-secondary" type="button" @click="activeCategory === 'favorites' || activeCategory === 'recent' ? setCategory('all') : clearFilters()">
            {{ activeCategory === 'favorites' || activeCategory === 'recent' ? '浏览全部资源' : '清除筛选' }}
          </button>
        </div>
      </div>

      <template v-else>
        <div v-if="viewMode === 'list'" class="resource-table">
          <div class="resource-table-head">
            <span>资源名称</span>
            <span>类型</span>
            <span>所属课程</span>
            <span>关联知识点</span>
            <span>学习量</span>
            <span>状态</span>
            <span>更新时间</span>
            <span>操作</span>
          </div>

          <article v-for="resource in pageResources" :key="resource.id" class="resource-row">
            <span class="resource-name-cell">
              <i class="resource-type-chip" :class="`type-${resource.type}`">
                <component :is="resource.icon" :size="15" />
              </i>
              <span class="resource-name-copy">
                <strong>{{ resource.title }}</strong>
                <small>{{ resource.knowledgePointTitle }}</small>
              </span>
            </span>
            <span>{{ resource.typeLabel }}</span>
            <span>{{ resource.courseTitle }}</span>
            <span>{{ resource.knowledgePointTitle }}</span>
            <span>{{ resourceLearningAmount(resource) }}</span>
            <span><span class="status-pill" :class="statusClass(resource)">{{ resource.statusLabel }}</span></span>
            <span>{{ resource.updatedLabel }}</span>
            <span class="resource-actions">
              <button type="button" class="resource-icon-button" :aria-label="favoriteIds.includes(resource.id) ? '取消收藏' : '收藏资源'" :title="favoriteIds.includes(resource.id) ? '取消收藏' : '收藏资源'" @click.stop="toggleFavorite(resource)">
                <BookmarkCheck v-if="favoriteIds.includes(resource.id)" :size="15" />
                <Bookmark v-else :size="15" />
              </button>
              <button type="button" class="resource-open-button" @click="openResource(resource)">
                打开 <ArrowRight :size="14" />
              </button>
              <button type="button" class="resource-icon-button" :aria-label="`更多操作：${resource.title}`" title="更多操作" @click.stop="toggleMoreMenu(resource.id)">
                <MoreHorizontal :size="15" />
              </button>
              <div v-if="activeMenuId === resource.id" class="resource-menu" @click.stop>
                <button type="button" @click="openResourceDetail(resource)">
                  <ExternalLink :size="14" /> 查看详情
                </button>
                <button type="button" @click="openResource(resource)">
                  <ArrowRight :size="14" /> 打开学习页
                </button>
                <button type="button" @click="copyResourceLink(resource)">
                  <Copy :size="14" /> 复制资源链接
                </button>
                <button type="button" @click="toggleLater(resource)">
                  <Clock3 :size="14" /> {{ laterIds.includes(resource.id) ? "取消稍后学习" : "标记稍后学习" }}
                </button>
              </div>
            </span>
          </article>
        </div>

        <div v-else class="resource-grid">
          <article v-for="resource in pageResources" :key="resource.id" class="resource-card">
            <div class="resource-card__head">
              <div class="resource-card__title">
                <span class="resource-type-chip" :class="`type-${resource.type}`">
                  <component :is="resource.icon" :size="16" />
                </span>
                <div>
                  <strong>{{ resource.title }}</strong>
                  <small>{{ resource.courseTitle }}</small>
                </div>
              </div>
              <button type="button" class="resource-icon-button" :aria-label="favoriteIds.includes(resource.id) ? '取消收藏' : '收藏资源'" @click="toggleFavorite(resource)">
                <BookmarkCheck v-if="favoriteIds.includes(resource.id)" :size="15" />
                <Bookmark v-else :size="15" />
              </button>
            </div>

            <p class="resource-card__summary">{{ resource.knowledgePointTitle }} · {{ resource.typeLabel }} · {{ resourceLearningAmount(resource) }}</p>

            <div class="resource-card__meta">
              <span><CheckCircle2 :size="14" /> {{ resource.statusLabel }}</span>
              <span><Clock3 :size="14" /> {{ resource.updatedLabel }}</span>
              <span><FileText :size="14" /> {{ resourceOriginLabel(resource) }}</span>
              <span><CalendarDays :size="14" /> {{ resource.chapterTitle }}</span>
            </div>

            <div class="resource-card__footer">
              <span class="status-pill" :class="statusClass(resource)">{{ resource.statusLabel }}</span>
              <div class="resource-card__actions">
                <button class="resource-mini-button" type="button" :aria-label="`更多操作：${resource.title}`" @click.stop="toggleMoreMenu(resource.id)">
                  <MoreHorizontal :size="15" />
                </button>
                <button class="resource-open-button" type="button" @click="openResource(resource)">
                  打开 <ArrowRight :size="14" />
                </button>
              </div>
            </div>

            <div v-if="activeMenuId === resource.id" class="resource-menu resource-menu--card" @click.stop>
              <button type="button" @click="openResourceDetail(resource)">
                <ExternalLink :size="14" /> 查看详情
              </button>
              <button type="button" @click="openResource(resource)">
                <ArrowRight :size="14" /> 打开学习页
              </button>
              <button type="button" @click="copyResourceLink(resource)">
                <Copy :size="14" /> 复制资源链接
              </button>
              <button type="button" @click="toggleLater(resource)">
                <Clock3 :size="14" /> {{ laterIds.includes(resource.id) ? "取消稍后学习" : "标记稍后学习" }}
              </button>
            </div>
          </article>
        </div>

        <footer class="resource-pagination">
          <div class="resource-pagination__summary">
            <span>{{ pageRangeText }}</span>
            <small>每页 {{ pageSize }} 条</small>
          </div>

          <div class="resource-pagination__controls">
            <label class="resource-page-size">
              <span>每页</span>
              <select :value="pageSize" @change="changePageSize(Number(($event.target as HTMLSelectElement).value))">
                <option v-for="size in pageSizes" :key="size" :value="size">{{ size }}</option>
              </select>
            </label>

            <button class="pagination-button" type="button" :disabled="page <= 1" @click="changePage(page - 1)">上一页</button>
            <span class="pagination-page">{{ page }} / {{ totalPages }}</span>
            <button class="pagination-button" type="button" :disabled="page >= totalPages" @click="changePage(page + 1)">下一页</button>
          </div>
        </footer>
      </template>
    </section>

    <button class="resource-assistant-launcher" type="button" aria-label="打开织知助手" @click="openAssistant">
      <Sparkles :size="18" />
      <span>织知助手</span>
    </button>

    <div v-if="assistantOpen" class="resource-assistant-backdrop" @click="closeAssistant" />
    <aside v-if="assistantOpen" class="resource-assistant" aria-label="织知助手面板">
      <div class="resource-assistant__head">
        <div>
          <p class="eyebrow">织知助手</p>
          <h3>帮你快速找到下一步</h3>
        </div>
        <button class="resource-icon-button" type="button" aria-label="关闭织知助手" @click="closeAssistant">
          <X :size="16" />
        </button>
      </div>
      <p class="resource-assistant__copy">你可以直接进入学习路径、学习记录或学情中心，继续完成当前任务。</p>
      <div class="resource-assistant__links">
        <RouterLink to="/learning-path" class="resource-assistant__link" @click="closeAssistant">学习路径</RouterLink>
        <RouterLink to="/history" class="resource-assistant__link" @click="closeAssistant">学习记录</RouterLink>
        <RouterLink to="/diagnosis" class="resource-assistant__link" @click="closeAssistant">学情诊断</RouterLink>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.learning-resources {
  color: var(--text);
}

.resource-page-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  padding: 4px 4px 8px;
}

.resource-page-hero__copy {
  min-width: 0;
}

.resource-page-hero__copy h2 {
  margin: 6px 0 6px;
  color: var(--text);
  font-size: clamp(30px, 3vw, 42px);
  line-height: 1.1;
}

.resource-page-hero__subtitle {
  max-width: 680px;
  color: var(--muted);
  font-size: 15px;
  line-height: 1.7;
}

.resource-page-hero__meta {
  display: flex;
  align-items: center;
  gap: 14px;
  flex: 0 0 auto;
}

.resource-page-hero__update {
  display: grid;
  gap: 4px;
  justify-items: end;
  color: var(--text);
}

.resource-page-hero__update-label {
  color: var(--muted);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.resource-page-hero__update strong {
  font-size: 13px;
}

.resource-help-button {
  padding: 0;
}

.resource-notice {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  padding: 9px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.resource-notice.is-success {
  color: var(--green);
  background: var(--green-soft);
}

.resource-notice.is-warning {
  color: var(--amber);
  background: var(--amber-soft);
}

.resource-notice.is-info {
  color: var(--blue);
  background: var(--blue-soft);
}

.resource-browser {
  min-width: 0;
  padding: 0;
  overflow: hidden;
  border-radius: 18px;
}

.resource-category-tabs {
  display: flex;
  gap: 10px;
  padding: 0 20px;
  overflow-x: auto;
  border-bottom: 1px solid var(--line);
  scrollbar-width: none;
}

.resource-category-tabs::-webkit-scrollbar {
  width: 0;
  height: 0;
}

.resource-category-tab {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 60px;
  padding: 0 4px;
  color: var(--muted);
  background: transparent;
  border: 0;
  border-bottom: 2px solid transparent;
  font-size: 14px;
  font-weight: 800;
  white-space: nowrap;
  cursor: pointer;
}

.resource-category-tab small {
  color: inherit;
  font-size: 12px;
  font-weight: 700;
  opacity: .72;
}

.resource-category-tab.active {
  color: var(--blue);
  border-bottom-color: var(--blue);
}

.resource-filter-bar {
  display: grid;
  grid-template-columns: minmax(260px, 1.55fr) repeat(5, minmax(132px, 1fr));
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--line);
  background: #fbfdff;
}

.resource-filter {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  height: 42px;
  padding: 0 12px;
  color: var(--muted);
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 12px;
}

.resource-filter span {
  flex: 0 0 auto;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.resource-filter select,
.resource-filter input {
  width: 100%;
  min-width: 0;
  height: 100%;
  color: var(--text);
  background: transparent;
  border: 0;
  outline: none;
  font: inherit;
}

.resource-search {
  padding-right: 38px;
}

.resource-search svg {
  color: var(--muted);
}

.resource-inline-clear {
  position: absolute;
  top: 50%;
  right: 10px;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  padding: 0;
  color: var(--muted);
  background: transparent;
  border: 0;
  transform: translateY(-50%);
}

.resource-more-button {
  justify-content: center;
  color: var(--text);
  cursor: pointer;
}

.resource-more-button.active {
  color: var(--blue);
  border-color: #c7d9fb;
  background: var(--blue-soft);
}

.resource-more-button small {
  display: grid;
  place-items: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  color: #fff;
  background: var(--blue);
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
}

.resource-sort {
  padding-right: 10px;
}

.resource-advanced {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  padding: 14px 20px 16px;
  border-bottom: 1px solid var(--line);
  background: #fff;
}

.resource-date-range {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.resource-advanced__actions {
  display: flex;
  grid-column: 1 / -1;
  justify-content: flex-end;
  gap: 10px;
}

.resource-result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px;
}

.resource-result-copy h3 {
  margin: 0;
  font-size: 18px;
}

.resource-result-copy p {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 12px;
}

.resource-result-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.resource-view-switch {
  display: flex;
  padding: 3px;
  background: #f1f6fd;
  border: 1px solid #dce5f1;
  border-radius: 12px;
}

.resource-view-switch button {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  color: var(--muted);
  background: transparent;
  border: 0;
  border-radius: 10px;
}

.resource-view-switch button.active {
  color: var(--blue);
  background: #fff;
  box-shadow: 0 4px 10px rgba(47, 111, 236, .09);
}

.resource-empty,
.resource-error,
.resource-loading {
  min-width: 0;
  padding: 20px;
}

.resource-state {
  display: grid;
  place-items: center;
  gap: 10px;
  padding: 52px 20px;
  text-align: center;
}

.resource-state__icon {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  color: var(--blue);
  background: var(--blue-soft);
  border-radius: 16px;
}

.resource-state strong {
  font-size: 18px;
}

.resource-state p {
  margin: 0;
  color: var(--muted);
  line-height: 1.7;
}

.resource-skeleton {
  display: grid;
  gap: 12px;
}

.resource-skeleton span {
  display: block;
  border-radius: 12px;
  background: linear-gradient(90deg, #edf3fb 0%, #f8fbff 50%, #edf3fb 100%);
  background-size: 220% 100%;
  animation: resource-shimmer 1.5s ease-in-out infinite;
}

.resource-skeleton__tabs {
  grid-template-columns: repeat(8, minmax(72px, 1fr));
  padding: 18px 20px 0;
}

.resource-skeleton__tabs span {
  height: 20px;
}

.resource-skeleton__bar {
  grid-template-columns: repeat(6, minmax(0, 1fr));
  padding: 18px 20px;
}

.resource-skeleton__bar span {
  height: 42px;
}

.resource-skeleton__table {
  padding: 0 20px 20px;
}

.resource-skeleton__table span {
  height: 56px;
}

.resource-table {
  display: grid;
}

.resource-table-head,
.resource-row {
  display: grid;
  grid-template-columns: minmax(250px, 1.5fr) 90px minmax(150px, 1fr) minmax(160px, 1fr) 96px 96px 112px minmax(180px, 0.92fr);
  gap: 12px;
  align-items: center;
  padding: 14px 20px;
}

.resource-table-head {
  color: var(--muted);
  background: #f8fbff;
  font-size: 12px;
  font-weight: 800;
}

.resource-row {
  position: relative;
  border-top: 1px solid var(--line);
  color: #38516f;
  font-size: 13px;
}

.resource-row:hover {
  background: #fbfdff;
}

.resource-row > span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resource-name-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.resource-name-copy {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.resource-name-copy strong,
.resource-name-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resource-name-copy strong {
  color: var(--text);
  font-size: 13px;
}

.resource-name-copy small {
  color: var(--muted);
  font-size: 11px;
}

.resource-type-chip {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  flex: 0 0 auto;
  color: #fff;
  border-radius: 10px;
}

.type-lecture { background: #2563eb; }
.type-video { background: #7c3aed; }
.type-example { background: #0891b2; }
.type-practice { background: #16a34a; }
.type-assessment { background: #d97706; }

.resource-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  position: relative;
  overflow: visible;
}

.resource-icon-button {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  flex: 0 0 auto;
  color: var(--muted);
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 10px;
}

.resource-icon-button:hover {
  color: var(--blue);
  background: var(--blue-soft);
}

.resource-open-button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 36px;
  padding: 0 12px;
  color: var(--blue-dark);
  background: var(--blue-soft);
  border: 1px solid #c8d9f6;
  border-radius: 10px;
  font-weight: 700;
}

.resource-open-button:hover {
  background: #dfeaff;
}

.resource-menu {
  position: absolute;
  top: 42px;
  right: 0;
  z-index: 4;
  width: 200px;
  padding: 8px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 12px;
  box-shadow: var(--shadow);
}

.resource-menu button {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 36px;
  padding: 0 10px;
  color: var(--text);
  background: transparent;
  border: 0;
  border-radius: 8px;
  text-align: left;
}

.resource-menu button:hover {
  color: var(--blue-dark);
  background: var(--blue-soft);
}

.resource-menu--card {
  top: auto;
  bottom: calc(100% + 10px);
}

.resource-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  padding: 0 20px 20px;
}

.resource-card {
  position: relative;
  display: grid;
  gap: 14px;
  min-width: 0;
  padding: 16px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 16px;
  box-shadow: var(--shadow-soft);
}

.resource-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.resource-card__title {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
}

.resource-card__title > div {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.resource-card__title strong,
.resource-card__title small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resource-card__title strong {
  color: var(--text);
  font-size: 14px;
}

.resource-card__title small {
  color: var(--muted);
  font-size: 11px;
}

.resource-card__summary {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.6;
}

.resource-card__meta {
  display: grid;
  gap: 8px;
  color: var(--muted);
  font-size: 12px;
}

.resource-card__meta span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.resource-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.resource-card__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.resource-mini-button {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  color: var(--muted);
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 10px;
}

.resource-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px 20px;
  border-top: 1px solid var(--line);
  background: #fff;
}

.resource-pagination__summary {
  display: flex;
  align-items: baseline;
  gap: 8px;
  color: var(--text);
}

.resource-pagination__summary small {
  color: var(--muted);
  font-size: 12px;
}

.resource-pagination__controls {
  display: flex;
  align-items: center;
  gap: 10px;
}

.resource-page-size {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 38px;
  padding: 0 10px;
  color: var(--muted);
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 10px;
}

.resource-page-size span {
  font-size: 12px;
  font-weight: 700;
}

.resource-page-size select {
  border: 0;
  outline: none;
  background: transparent;
  font: inherit;
}

.pagination-button {
  min-height: 38px;
  padding: 0 12px;
  color: var(--text);
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 10px;
  font-weight: 700;
}

.pagination-button:hover:not(:disabled) {
  color: var(--blue);
  background: var(--blue-soft);
}

.pagination-button:disabled {
  opacity: .5;
}

.pagination-page {
  min-width: 72px;
  text-align: center;
  font-weight: 800;
}

.resource-assistant-launcher {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 55;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 52px;
  padding: 0 16px;
  color: #fff;
  background: linear-gradient(135deg, var(--blue), #5c8fff);
  border: 0;
  border-radius: 999px;
  box-shadow: var(--shadow);
  font-weight: 800;
}

.resource-assistant-backdrop {
  position: fixed;
  inset: 0;
  z-index: 54;
  background: rgba(16, 35, 63, .12);
}

.resource-assistant {
  position: fixed;
  right: 24px;
  bottom: 84px;
  z-index: 56;
  width: min(360px, calc(100vw - 32px));
  padding: 18px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 18px;
  box-shadow: var(--shadow);
}

.resource-assistant__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.resource-assistant__head h3 {
  margin: 4px 0 0;
  font-size: 18px;
}

.resource-assistant__copy {
  margin: 12px 0 14px;
  color: var(--muted);
  line-height: 1.7;
}

.resource-assistant__links {
  display: grid;
  gap: 10px;
}

.resource-assistant__link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 42px;
  padding: 0 12px;
  color: var(--text);
  background: #fbfdff;
  border: 1px solid var(--line);
  border-radius: 12px;
  font-weight: 700;
}

.resource-assistant__link:hover {
  color: var(--blue);
  background: var(--blue-soft);
}

@keyframes resource-shimmer {
  0% { background-position: 100% 50%; }
  100% { background-position: 0 50%; }
}

@media (max-width: 1320px) {
  .resource-filter-bar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .resource-advanced {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .resource-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .resource-table-head {
    display: none;
  }

  .resource-row {
    grid-template-columns: 1fr;
    gap: 8px;
    padding: 16px 20px;
  }

  .resource-actions {
    justify-content: flex-start;
  }
}

@media (max-width: 920px) {
  .resource-page-hero {
    align-items: flex-start;
    flex-direction: column;
  }

  .resource-page-hero__meta {
    width: 100%;
    justify-content: space-between;
  }

  .resource-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .resource-pagination {
    align-items: flex-start;
    flex-direction: column;
  }
}

@media (max-width: 720px) {
  .resource-filter-bar,
  .resource-advanced {
    grid-template-columns: 1fr;
  }

  .resource-date-range {
    grid-template-columns: 1fr;
  }

  .resource-grid {
    grid-template-columns: 1fr;
  }

  .resource-result-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .resource-result-actions,
  .resource-pagination__controls {
    width: 100%;
    justify-content: space-between;
  }

  .resource-assistant-launcher,
  .resource-assistant {
    right: 16px;
  }
}
</style>
