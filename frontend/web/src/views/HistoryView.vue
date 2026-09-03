<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  BarChart3,
  BookOpenCheck,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Download,
  FileCheck2,
  FileText,
  LineChart,
  Route,
  Search,
  X,
} from "lucide-vue-next";
import { useLearnerStore } from "@/stores/learner";
import { useLearningPathStore } from "@/stores/learningPath";
import { type LearningRecord, type LearningRecordType, useLearningRecordsStore } from "@/stores/learningRecords";
import { adaptPathNodes, courseIdFromProfile, courseTitle, knowledgeTitle } from "@/utils/knowledgeGraph";

type ActivityFilter = "all" | "learning" | "assessment" | "path";
type DatePreset = "7" | "30" | "90" | "semester" | "custom";

const route = useRoute();
const router = useRouter();
const learner = useLearnerStore();
const learningPath = useLearningPathStore();
const recordStore = useLearningRecordsStore();

const pageSize = 8;
const selectedRecord = ref<LearningRecord | null>(null);
const searchDraft = ref(String(route.query.keyword || ""));
const customStart = ref(String(route.query.startDate || ""));
const customEnd = ref(String(route.query.endDate || ""));
const exportState = ref("");
const rhythmFilter = ref<{ weekday: number; period: string } | null>(null);
let searchTimer: number | undefined;

const tabs: Array<{ key: ActivityFilter; label: string }> = [
  { key: "all", label: "全部记录" },
  { key: "learning", label: "学习内容" },
  { key: "assessment", label: "测评记录" },
  { key: "path", label: "路径调整" },
];
const datePresets: Array<{ key: DatePreset; label: string }> = [
  { key: "7", label: "近7天" },
  { key: "30", label: "近30天" },
  { key: "90", label: "近90天" },
  { key: "semester", label: "本学期" },
  { key: "custom", label: "自定义日期" },
];

const typeQuery = computed<ActivityFilter>(() => {
  const value = String(route.query.type || "all");
  return ["all", "learning", "assessment", "path"].includes(value) ? value as ActivityFilter : "all";
});
const dateQuery = computed<DatePreset>(() => {
  const value = String(route.query.range || "30");
  return ["7", "30", "90", "semester", "custom"].includes(value) ? value as DatePreset : "30";
});
const courseQuery = computed(() => String(route.query.courseId || "all"));
const keywordQuery = computed(() => String(route.query.keyword || "").trim());
const pageQuery = computed(() => Math.max(1, Number(route.query.page || 1) || 1));

const adaptedPath = computed(() => adaptPathNodes(learningPath.nodes, {
  courseId: courseIdFromProfile(learner.profile),
  profile: learner.profile,
  snapshot: learner.snapshot,
  learningProgress: learningPath.run?.learning_progress,
}));

const generatedRecords = computed<LearningRecord[]>(() => {
  const records: LearningRecord[] = [];
  const now = new Date().toISOString();
  const profile = learner.profile;
  const snapshot = learner.snapshot;
  const profileId = profile?.profile_id || "current-profile";
  const snapshotId = snapshot?.profile_id || profileId;
  const currentCourseId = courseIdFromProfile(learner.profile) || learningPath.run?.handoff?.chapter_id || "current-course";
  const currentCourseTitle = profile?.learning_scope?.chapter_name || courseTitle(currentCourseId);
  const learnerId = profile?.learner_id || snapshot?.learner_ref || "current-learner";

  if (learningPath.run?.run_id && learningPath.nodes.length) {
    records.push(makeRecord({
      id: `${learningPath.run.run_id}:path_replanned`,
      learnerId,
      courseId: currentCourseId,
      courseTitle: currentCourseTitle,
      knowledgeNodeId: learningPath.currentNode?.concept_id || null,
      knowledgeNodeTitle: learningPath.currentNode ? knowledgeTitle(learningPath.currentNode.concept_id, learningPath.currentNode.title, learningPath.currentNode.name) : null,
      type: "path_replanned",
      title: "学习路径已更新",
      description: `当前路径包含 ${learningPath.nodes.length} 个知识节点`,
      currentMastery: adaptedPath.value.summary.averageMastery,
      currentRecommendedNodeId: learningPath.currentNode?.concept_id || null,
      unlockedNodeIds: adaptedPath.value.nodes.filter((node) => node.isUnlocked).map((node) => node.id),
      occurredAt: now,
      source: "platform-run",
      metadata: { runId: learningPath.run.run_id },
    }));
  }

  const progress = learningPath.run?.learning_progress;
  if (progress?.lecture_completed) {
    const node = learningPath.nodes.find((item) => item.concept_id === progress.concept_id);
    const title = knowledgeTitle(progress.concept_id, node?.title, node?.name);
    records.push(makeRecord({
      id: `${learningPath.run?.run_id || "run"}:${progress.concept_id}:live-resource-completed`,
      learnerId,
      courseId: currentCourseId,
      courseTitle: currentCourseTitle,
      knowledgeNodeId: progress.concept_id,
      knowledgeNodeTitle: title,
      resourceId: `${learningPath.run?.run_id || "run"}:${progress.concept_id}:resource`,
      resourceTitle: `${title}学习资源`,
      type: "resource_completed",
      title: "完成学习资源",
      description: `${title} · ${progress.can_complete ? "已满足完成条件" : "已完成学习，等待练习或测评"}`,
      completionRate: progress.lecture_progress,
      currentRecommendedNodeId: learningPath.currentNode?.concept_id || null,
      occurredAt: now,
      source: "platform-run",
      metadata: { runId: learningPath.run?.run_id },
    }));
  }

  for (const item of snapshot?.knowledge_mastery || []) {
    if (typeof item.mastery_score !== "number") continue;
    records.push(makeRecord({
      id: `${snapshotId}:${item.concept_id}:${item.observed_at || "mastery"}`,
      learnerId,
      courseId: currentCourseId,
      courseTitle: currentCourseTitle,
      knowledgeNodeId: item.concept_id,
      knowledgeNodeTitle: knowledgeTitle(item.concept_id),
      assessmentId: item.evidence_refs?.[0] || null,
      attemptId: item.evidence_refs?.[0] || null,
      type: "mastery_updated",
      title: "掌握度已更新",
      description: `${knowledgeTitle(item.concept_id)} · 掌握度 ${Math.round(item.mastery_score * 100)}%`,
      currentMastery: item.mastery_score,
      assessmentScore: item.mastery_score,
      occurredAt: item.observed_at || now,
      source: "learner-profile",
    }));
  }

  for (const chapter of profile?.prior_chapters || []) {
    if (!chapter.completed_at && typeof chapter.time_spent_hours !== "number") continue;
    records.push(makeRecord({
      id: `${profileId}:${chapter.chapter_id}:chapter`,
      learnerId,
      courseId: chapter.chapter_id || currentCourseId,
      courseTitle: chapter.chapter_name || courseTitle(chapter.chapter_id || currentCourseId),
      resourceTitle: chapter.chapter_name,
      type: "resource_completed",
      title: "完成学习内容",
      description: chapter.conclusion || `${chapter.chapter_name} · 已完成课程学习`,
      durationSeconds: typeof chapter.time_spent_hours === "number" ? Math.round(chapter.time_spent_hours * 3600) : null,
      completionRate: chapter.accuracy ?? null,
      currentMastery: chapter.accuracy ?? null,
      assessmentScore: chapter.accuracy ?? null,
      assessmentAccuracy: chapter.accuracy ?? null,
      unlockedNodeIds: chapter.kps_covered || [],
      occurredAt: chapter.completed_at || now,
      source: "learner-profile",
    }));
  }

  return records;
});

const allRecords = computed(() => {
  const byId = new Map<string, LearningRecord>();
  for (const record of [...recordStore.records, ...generatedRecords.value]) byId.set(record.id, record);
  return [...byId.values()].sort((a, b) => new Date(b.occurredAt).getTime() - new Date(a.occurredAt).getTime());
});

const courseOptions = computed(() => {
  const map = new Map<string, string>();
  for (const record of allRecords.value) map.set(record.courseId, record.courseTitle);
  if (learner.profile?.learning_scope?.chapter_id) map.set(learner.profile.learning_scope.chapter_id, learner.profile.learning_scope.chapter_name || "当前课程");
  return [{ id: "all", title: "全部课程" }, ...[...map.entries()].map(([id, title]) => ({ id, title }))];
});

const dateRange = computed(() => {
  const now = new Date();
  if (dateQuery.value === "custom") {
    return {
      start: customStart.value ? new Date(`${customStart.value}T00:00:00`) : null,
      end: customEnd.value ? new Date(`${customEnd.value}T23:59:59`) : null,
    };
  }
  const days = dateQuery.value === "semester" ? 150 : Number(dateQuery.value);
  const start = new Date(now);
  start.setDate(now.getDate() - days + 1);
  start.setHours(0, 0, 0, 0);
  return { start, end: now };
});

const filteredRecords = computed(() => {
  const keyword = keywordQuery.value.toLowerCase();
  const { start, end } = dateRange.value;
  return allRecords.value.filter((record) => {
    const occurred = new Date(record.occurredAt);
    const text = [record.title, record.description, record.courseTitle, record.knowledgeNodeTitle, record.resourceTitle].filter(Boolean).join(" ").toLowerCase();
    return recordMatchesType(record)
      && (courseQuery.value === "all" || record.courseId === courseQuery.value)
      && (!start || occurred >= start)
      && (!end || occurred <= end)
      && (!keyword || text.includes(keyword))
      && (!rhythmFilter.value || (occurred.getDay() === rhythmFilter.value.weekday && periodForDate(occurred) === rhythmFilter.value.period));
  });
});

const totalPages = computed(() => Math.max(1, Math.ceil(filteredRecords.value.length / pageSize)));
const pagedRecords = computed(() => filteredRecords.value.slice((pageQuery.value - 1) * pageSize, pageQuery.value * pageSize));
const groupedRecords = computed(() => {
  const groups: Array<{ label: string; items: LearningRecord[] }> = [];
  for (const record of pagedRecords.value) {
    const label = dateGroupLabel(record.occurredAt);
    const group = groups.find((item) => item.label === label);
    if (group) group.items.push(record);
    else groups.push({ label, items: [record] });
  }
  return groups;
});

const summary = computed(() => {
  const duration = filteredRecords.value.reduce((sum, record) => sum + Math.min(record.durationSeconds || 0, 4 * 3600), 0);
  const completed = new Set(filteredRecords.value.filter((record) => ["resource_completed", "knowledge_completed"].includes(record.type) && record.knowledgeNodeId).map((record) => record.knowledgeNodeId));
  const assessments = filteredRecords.value.filter((record) => record.type === "assessment_completed").length;
  const masteryValues = filteredRecords.value.map((record) => record.currentMastery).filter((value): value is number => typeof value === "number");
  const averageMastery = masteryValues.length ? masteryValues.reduce((sum, value) => sum + value, 0) / masteryValues.length : null;
  return { duration, completed: completed.size, assessments, averageMastery };
});

const trendPoints = computed(() => {
  const days = dateQuery.value === "7" ? 7 : 30;
  return Array.from({ length: days }, (_, index) => {
    const date = new Date();
    date.setDate(date.getDate() - days + index + 1);
    const key = isoDate(date);
    const dayRecords = filteredRecords.value.filter((record) => isoDate(new Date(record.occurredAt)) === key);
    const masteryValues = dayRecords.map((record) => record.currentMastery).filter((value): value is number => typeof value === "number");
    return {
      key,
      durationHours: dayRecords.reduce((sum, record) => sum + (record.durationSeconds || 0), 0) / 3600,
      mastery: masteryValues.length ? masteryValues.reduce((sum, value) => sum + value, 0) / masteryValues.length : null,
    };
  });
});

const masteryRows = computed(() =>
  filteredRecords.value
    .filter((record) => record.knowledgeNodeId && (typeof record.currentMastery === "number" || typeof record.previousMastery === "number"))
    .slice(0, 8),
);

function makeRecord(partial: Partial<LearningRecord> & Pick<LearningRecord, "id" | "learnerId" | "courseId" | "courseTitle" | "type" | "title" | "occurredAt" | "source">): LearningRecord {
  return {
    knowledgeNodeId: null,
    knowledgeNodeTitle: null,
    resourceId: null,
    resourceTitle: null,
    assessmentId: null,
    attemptId: null,
    description: null,
    durationSeconds: null,
    completionRate: null,
    previousMastery: null,
    currentMastery: null,
    assessmentScore: null,
    assessmentAccuracy: null,
    previousRecommendedNodeId: null,
    currentRecommendedNodeId: null,
    unlockedNodeIds: [],
    createdAt: partial.occurredAt,
    ...partial,
  };
}

function updateQuery(patch: Record<string, string | number | undefined>) {
  void router.replace({ query: { ...route.query, ...patch } });
}

function recordMatchesType(record: LearningRecord) {
  if (typeQuery.value === "all") return true;
  if (typeQuery.value === "learning") return ["resource_started", "resource_completed", "knowledge_completed", "review_completed"].includes(record.type);
  if (typeQuery.value === "assessment") return ["assessment_completed", "mastery_updated"].includes(record.type);
  return ["path_replanned", "node_unlocked"].includes(record.type);
}

function debounceSearch(value: string) {
  searchDraft.value = value;
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => updateQuery({ keyword: value || undefined, page: 1 }), 300);
}

function applyCustomDate() {
  updateQuery({ range: "custom", startDate: customStart.value || undefined, endDate: customEnd.value || undefined, page: 1 });
}

function clearFilters() {
  rhythmFilter.value = null;
  searchDraft.value = "";
  customStart.value = "";
  customEnd.value = "";
  void router.replace({ query: { type: "all", range: "30", courseId: "all", page: 1 } });
}

function exportCsv() {
  exportState.value = "正在导出";
  const header = ["记录时间", "记录类型", "课程", "知识点", "资源或测评名称", "学习时长", "完成状态", "测评正确率", "原掌握度", "新掌握度", "路径变化"];
  const rows = filteredRecords.value.map((record) => [
    formatDateTime(record.occurredAt),
    recordTypeLabel(record.type),
    record.courseTitle,
    record.knowledgeNodeTitle || "",
    record.resourceTitle || record.assessmentId || "",
    formatDuration(record.durationSeconds),
    statusText(record),
    percentText(record.assessmentAccuracy),
    percentText(record.previousMastery),
    percentText(record.currentMastery),
    record.currentRecommendedNodeId ? `下一节点：${knowledgeTitle(record.currentRecommendedNodeId)}` : "",
  ]);
  const csv = [header, ...rows].map((row) => row.map((cell) => `"${String(cell).replaceAll("\"", "\"\"")}"`).join(",")).join("\n");
  const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `学习记录-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
  exportState.value = "导出成功";
  window.setTimeout(() => { exportState.value = ""; }, 1800);
}

function goRecordAction(record: LearningRecord) {
  if (record.type === "assessment_completed" || record.type === "mastery_updated") void router.push("/assessment");
  else if (record.type === "path_replanned" || record.type === "node_unlocked") void router.push({ path: "/learning-path", query: record.knowledgeNodeId ? { nodeId: record.knowledgeNodeId } : {} });
  else void router.push("/resources#learning-resources");
}

function dateGroupLabel(value: string) {
  const date = new Date(value);
  const today = isoDate(new Date());
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  if (isoDate(date) === today) return "今天";
  if (isoDate(date) === isoDate(yesterday)) return "昨天";
  return `${date.getMonth() + 1}月${date.getDate()}日`;
}

function isoDate(date: Date) {
  return date.toISOString().slice(0, 10);
}

function formatDateTime(value: string) {
  const date = new Date(value);
  return `${date.getMonth() + 1}月${date.getDate()}日 ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function formatDuration(seconds: number | null) {
  if (!seconds) return "-";
  if (seconds >= 3600) return `${(seconds / 3600).toFixed(1)}小时`;
  return `${Math.max(1, Math.round(seconds / 60))}分钟`;
}

function percentText(value: number | null) {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "待评估";
}

function statusText(record: LearningRecord) {
  if (record.type === "resource_completed") return "已完成·待测评";
  if (record.type === "assessment_completed") return "已提交";
  if (record.type === "mastery_updated") return "已更新";
  if (record.type === "path_replanned") return "已更新";
  return "已记录";
}

function recordTypeLabel(type: LearningRecordType) {
  const labels: Record<LearningRecordType, string> = {
    resource_started: "开始学习资源",
    resource_completed: "完成学习资源",
    knowledge_completed: "完成知识点学习",
    assessment_completed: "完成阶段测评",
    mastery_updated: "掌握度已更新",
    path_replanned: "学习路径已更新",
    node_unlocked: "解锁新知识点",
    review_completed: "完成错题复习",
  };
  return labels[type];
}

function recordIcon(type: LearningRecordType) {
  if (["assessment_completed", "mastery_updated"].includes(type)) return FileCheck2;
  if (["path_replanned", "node_unlocked"].includes(type)) return Route;
  return BookOpenCheck;
}

function recordTone(type: LearningRecordType) {
  if (["assessment_completed", "mastery_updated"].includes(type)) return "green";
  if (["path_replanned", "node_unlocked"].includes(type)) return "blue";
  return "cyan";
}

function periodForDate(date: Date) {
  const hour = date.getHours();
  if (hour < 12) return "上午";
  if (hour < 18) return "下午";
  return "晚上";
}

function rhythmLevel(weekday: number, period: string) {
  const seconds = filteredRecords.value
    .filter((record) => {
      const date = new Date(record.occurredAt);
      return date.getDay() === weekday && periodForDate(date) === period;
    })
    .reduce((sum, record) => sum + (record.durationSeconds || 0), 0);
  if (seconds >= 7200) return 4;
  if (seconds >= 3600) return 3;
  if (seconds >= 1200) return 2;
  if (seconds > 0) return 1;
  return 0;
}

watch(keywordQuery, (value) => {
  searchDraft.value = value;
});

watch([filteredRecords, pageQuery], () => {
  if (pageQuery.value > totalPages.value) updateQuery({ page: totalPages.value });
});
</script>

<template>
  <div class="learning-records page-stack">
    <section class="record-toolbar panel">
      <div class="record-tabs" role="tablist" aria-label="记录类型">
        <button v-for="tab in tabs" :key="tab.key" :class="{ active: typeQuery === tab.key }" type="button" role="tab" @click="updateQuery({ type: tab.key, page: 1 })">{{ tab.label }}</button>
      </div>
      <div class="record-filters">
        <label class="filter-field">
          <CalendarDays :size="16" />
          <select :value="dateQuery" aria-label="日期范围" @change="updateQuery({ range: ($event.target as HTMLSelectElement).value, page: 1 })">
            <option v-for="item in datePresets" :key="item.key" :value="item.key">{{ item.label }}</option>
          </select>
        </label>
        <label class="filter-field">
          <BookOpenCheck :size="16" />
          <select :value="courseQuery" aria-label="课程选择" @change="updateQuery({ courseId: ($event.target as HTMLSelectElement).value, page: 1 })">
            <option v-for="course in courseOptions" :key="course.id" :value="course.id">{{ course.title }}</option>
          </select>
        </label>
        <label class="filter-field search-field">
          <Search :size="16" />
          <input :value="searchDraft" type="search" placeholder="搜索知识点或资源" @input="debounceSearch(($event.target as HTMLInputElement).value)" @keydown.enter="updateQuery({ keyword: searchDraft || undefined, page: 1 })" />
          <button v-if="searchDraft" type="button" aria-label="清空搜索" @click="debounceSearch('')"><X :size="14" /></button>
        </label>
        <button class="button button-secondary" type="button" :disabled="exportState === '正在导出'" @click="exportCsv"><Download :size="16" />{{ exportState || "导出记录" }}</button>
      </div>
      <div v-if="dateQuery === 'custom'" class="custom-date-row">
        <input v-model="customStart" type="date" aria-label="开始日期" @change="applyCustomDate" />
        <span>至</span>
        <input v-model="customEnd" type="date" aria-label="结束日期" @change="applyCustomDate" />
      </div>
    </section>

    <section class="record-summary panel" aria-label="学习摘要">
      <div><Clock3 :size="24" /><span>学习时长</span><b>{{ summary.duration ? formatDuration(summary.duration) : "暂无数据" }}</b></div>
      <div><BookOpenCheck :size="24" /><span>完成知识点</span><b>{{ summary.completed || "暂无数据" }}</b></div>
      <div><FileText :size="24" /><span>完成测评</span><b>{{ summary.assessments || "暂无数据" }}</b></div>
      <div><BarChart3 :size="24" /><span>平均掌握度</span><b>{{ percentText(summary.averageMastery) }}</b></div>
    </section>

    <div class="record-main-grid">
      <section class="panel activity-panel">
        <div class="panel-heading">
          <div><h3>学习活动</h3><p>{{ filteredRecords.length }} 条记录匹配当前筛选</p></div>
          <button v-if="keywordQuery || typeQuery !== 'all' || courseQuery !== 'all' || rhythmFilter" class="text-link" type="button" @click="clearFilters">清除筛选</button>
        </div>
        <div v-if="!allRecords.length" class="state-block">
          <strong>还没有学习记录</strong>
          <p>开始第一个学习任务后，记录会显示在这里。</p>
          <button class="button button-primary" type="button" @click="router.push('/app')">开始学习</button>
        </div>
        <div v-else-if="!filteredRecords.length" class="state-block">
          <strong>没有找到符合条件的记录</strong>
          <p>尝试调整时间、课程或记录类型。</p>
          <button class="button button-secondary" type="button" @click="clearFilters">清除筛选</button>
        </div>
        <div v-else class="activity-groups">
          <div v-for="group in groupedRecords" :key="group.label" class="activity-group">
            <h4>{{ group.label }}</h4>
            <article v-for="record in group.items" :key="record.id" class="record-row" tabindex="0" :aria-label="`查看${record.title}详情`" @click="selectedRecord = record" @keydown.enter="selectedRecord = record">
              <span class="record-icon" :class="`tone-${recordTone(record.type)}`"><component :is="recordIcon(record.type)" :size="17" /></span>
              <span class="record-copy"><b>{{ record.title }}</b><small>{{ record.description || record.knowledgeNodeTitle || record.courseTitle }}</small></span>
              <time>{{ formatDateTime(record.occurredAt) }}</time>
              <span class="record-duration">{{ formatDuration(record.durationSeconds) }}</span>
              <strong class="record-result">{{ record.type === "mastery_updated" ? percentText(record.currentMastery) : statusText(record) }}</strong>
              <button class="button button-secondary button-small" type="button" @click.stop="goRecordAction(record)">{{ record.type === "assessment_completed" ? "查看反馈" : record.type === "path_replanned" ? "查看路径" : "继续学习" }}</button>
              <ChevronRight :size="16" class="icon-muted" />
            </article>
          </div>
          <div class="pagination">
            <button type="button" :disabled="pageQuery <= 1" @click="updateQuery({ page: pageQuery - 1 })"><ChevronLeft :size="15" />上一页</button>
            <button v-for="page in totalPages" :key="page" type="button" :class="{ active: pageQuery === page }" @click="updateQuery({ page })">{{ page }}</button>
            <button type="button" :disabled="pageQuery >= totalPages" @click="updateQuery({ page: pageQuery + 1 })">下一页<ChevronRight :size="15" /></button>
          </div>
        </div>
      </section>

      <aside class="record-side-stack">
        <section class="panel trend-card">
          <div class="panel-heading"><div><h3>近30天学习趋势</h3><p>学习时长与掌握度变化</p></div><LineChart :size="18" class="icon-blue" /></div>
          <svg class="trend-svg" viewBox="0 0 360 180" role="img" aria-label="学习时长与掌握度趋势图">
            <line v-for="line in 5" :key="line" x1="26" x2="344" :y1="20 + line * 28" :y2="20 + line * 28" />
            <polyline :points="trendPoints.map((point, index) => `${30 + index * (312 / Math.max(1, trendPoints.length - 1))},${154 - Math.min(point.durationHours, 4) * 28}`).join(' ')" class="duration-line" />
            <polyline :points="trendPoints.map((point, index) => `${30 + index * (312 / Math.max(1, trendPoints.length - 1))},${point.mastery === null ? 150 : 154 - point.mastery * 120}`).join(' ')" class="mastery-line" />
            <circle v-for="(point, index) in trendPoints" :key="point.key" :cx="30 + index * (312 / Math.max(1, trendPoints.length - 1))" :cy="154 - Math.min(point.durationHours, 4) * 28" r="3" tabindex="0" @click="updateQuery({ startDate: point.key, endDate: point.key, range: 'custom', page: 1 })" />
          </svg>
          <div class="chart-legend"><span><i class="blue" />学习时长</span><span><i class="cyan" />平均掌握度</span></div>
        </section>

        <section class="panel rhythm-card">
          <div class="panel-heading"><div><h3>学习节奏</h3><p>点击色块查看对应时段记录</p></div></div>
          <div class="rhythm-grid">
            <span />
            <b v-for="day in ['日','一','二','三','四','五','六']" :key="day">周{{ day }}</b>
            <template v-for="period in ['上午','下午','晚上']" :key="period">
              <em>{{ period }}</em>
              <button v-for="day in [0,1,2,3,4,5,6]" :key="`${period}-${day}`" type="button" :class="`level-${rhythmLevel(day, period)}`" :aria-label="`筛选周${day} ${period}的学习记录`" @click="rhythmFilter = { weekday: day, period }; updateQuery({ page: 1 })" />
            </template>
          </div>
          <button v-if="rhythmFilter" class="text-link" type="button" @click="rhythmFilter = null">取消时段筛选</button>
        </section>
      </aside>
    </div>

    <section class="panel mastery-table-panel">
      <div class="panel-heading">
        <div><h3>知识掌握变化</h3><p>来自学习者画像、测评结果和当前学习路径</p></div>
        <button class="text-link" type="button" @click="router.push('/profile')">查看学习者画像 <ChevronRight :size="15" /></button>
      </div>
      <div v-if="!masteryRows.length" class="state-block">
        <strong>完成知识点评测后，这里会展示掌握度变化。</strong>
        <button class="button button-secondary" type="button" @click="router.push('/assessment')">去完成测评</button>
      </div>
      <div v-else class="mastery-record-table">
        <table>
          <thead><tr><th>知识点</th><th>所属课程</th><th>最近测评</th><th>掌握度变化</th><th>当前状态</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="record in masteryRows" :key="record.id" tabindex="0" @click="selectedRecord = record" @keydown.enter="selectedRecord = record">
              <td>{{ record.knowledgeNodeTitle }}</td>
              <td>{{ record.courseTitle }}</td>
              <td>{{ formatDateTime(record.occurredAt) }}</td>
              <td><b>{{ percentText(record.previousMastery) }}</b> → <b>{{ percentText(record.currentMastery) }}</b></td>
              <td><span class="status-pill" :class="{ 'status-pill-success': (record.currentMastery || 0) >= 0.75, 'status-pill-warning': (record.currentMastery || 0) < 0.6 }">{{ (record.currentMastery || 0) >= 0.75 ? "已掌握" : (record.currentMastery || 0) < 0.6 ? "建议复习" : "学习中" }}</span></td>
              <td><button class="text-link" type="button" @click.stop="goRecordAction(record)">查看知识点</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <div v-if="selectedRecord" class="record-drawer-backdrop" @click="selectedRecord = null" />
    <aside v-if="selectedRecord" class="record-drawer" aria-label="学习记录详情">
      <button class="icon-button drawer-close" type="button" aria-label="关闭详情" @click="selectedRecord = null"><X :size="18" /></button>
      <span class="status-pill">{{ recordTypeLabel(selectedRecord.type) }}</span>
      <h3>{{ selectedRecord.title }}</h3>
      <p>{{ selectedRecord.description || "这条记录来自当前学习状态。" }}</p>
      <dl>
        <div><dt>发生时间</dt><dd>{{ formatDateTime(selectedRecord.occurredAt) }}</dd></div>
        <div><dt>所属课程</dt><dd>{{ selectedRecord.courseTitle }}</dd></div>
        <div><dt>知识点</dt><dd>{{ selectedRecord.knowledgeNodeTitle || "未绑定具体知识点" }}</dd></div>
        <div><dt>学习时长</dt><dd>{{ formatDuration(selectedRecord.durationSeconds) }}</dd></div>
        <div><dt>掌握度</dt><dd>{{ percentText(selectedRecord.currentMastery) }}</dd></div>
        <div><dt>数据来源</dt><dd>{{ selectedRecord.source === "local-event" ? "学习操作事件" : selectedRecord.source === "platform-run" ? "当前学习路径" : "学习者画像" }}</dd></div>
      </dl>
      <button class="button button-primary button-full" type="button" @click="goRecordAction(selectedRecord)">继续处理这条记录 <ChevronRight :size="16" /></button>
    </aside>
  </div>
</template>

<style scoped>
.learning-records { --page-bg: #f4f7fb; --panel-bg: #fff; --primary: #2f6feb; --heading: #10233f; --body: #52657d; --muted: #7a8ca5; --border: #dce5f0; --divider: #e8eef5; }
.record-toolbar { display: grid; gap: 14px; padding: 16px; }
.record-tabs { display: grid; grid-template-columns: repeat(4, minmax(96px, 1fr)); max-width: 460px; border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.record-tabs button { min-height: 38px; color: var(--body); background: #fff; border: 0; border-right: 1px solid var(--divider); font-size: 13px; font-weight: 700; }
.record-tabs button:last-child { border-right: 0; }
.record-tabs button.active { color: #fff; background: var(--primary); }
.record-filters { display: grid; grid-template-columns: minmax(150px, 174px) minmax(190px, 250px) minmax(240px, 1fr) auto; gap: 12px; }
.filter-field { display: flex; align-items: center; gap: 8px; min-width: 0; height: 40px; padding: 0 12px; color: var(--muted); background: #fff; border: 1px solid var(--border); border-radius: 9px; }
.filter-field select, .filter-field input { width: 100%; min-width: 0; color: var(--heading); background: transparent; border: 0; outline: 0; font-size: 13px; }
.search-field button { display: grid; place-items: center; padding: 0; color: var(--muted); background: transparent; border: 0; }
.custom-date-row { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 12px; }
.custom-date-row input { height: 34px; padding: 0 10px; border: 1px solid var(--border); border-radius: 8px; }
.record-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); padding: 0; overflow: hidden; }
.record-summary > div { display: grid; grid-template-columns: 34px 1fr; gap: 2px 12px; align-items: center; padding: 18px 26px; border-right: 1px solid var(--divider); }
.record-summary > div:last-child { border-right: 0; }
.record-summary svg { grid-row: span 2; color: var(--primary); }
.record-summary span { color: var(--muted); font-size: 12px; }
.record-summary b { color: var(--heading); font-size: 23px; }
.record-main-grid { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(320px, .78fr); gap: 16px; }
.activity-panel { min-height: 480px; }
.activity-groups { display: grid; gap: 12px; }
.activity-group h4 { margin: 0 0 7px; color: var(--heading); font-size: 14px; }
.record-row { display: grid; grid-template-columns: 36px minmax(0, 1fr) 104px 70px 104px 88px 18px; gap: 12px; align-items: center; min-height: 56px; padding: 8px 12px; border-bottom: 1px solid var(--divider); cursor: pointer; }
.record-row:hover, .record-row:focus-visible { background: #f7faff; outline: 0; }
.record-icon { display: grid; place-items: center; width: 32px; height: 32px; border-radius: 9px; }
.tone-blue { color: var(--primary); background: #eef4ff; }
.tone-green { color: #149a88; background: #eaf8f4; }
.tone-cyan { color: #0b91ac; background: #e8f7fb; }
.record-copy { min-width: 0; }
.record-copy b, .record-copy small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.record-copy b { color: var(--heading); font-size: 13px; }
.record-copy small, .record-row time, .record-duration { color: var(--muted); font-size: 12px; }
.record-result { color: #149a88; font-size: 12px; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 8px; padding-top: 8px; }
.pagination button { display: inline-flex; align-items: center; min-height: 30px; padding: 0 10px; color: var(--primary); background: #fff; border: 1px solid #cbdaf6; border-radius: 7px; font-size: 12px; }
.pagination button.active { color: #fff; background: var(--primary); border-color: var(--primary); }
.pagination button:disabled { color: var(--muted); background: #f6f8fb; }
.record-side-stack { display: grid; gap: 16px; align-content: start; }
.trend-svg { width: 100%; height: 180px; }
.trend-svg line { stroke: #e8eef5; stroke-width: 1; }
.trend-svg polyline { fill: none; stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; }
.duration-line { stroke: var(--primary); }
.mastery-line { stroke: #18a7a0; }
.trend-svg circle { fill: var(--primary); cursor: pointer; }
.chart-legend { display: flex; justify-content: center; gap: 18px; color: var(--muted); font-size: 12px; }
.chart-legend span { display: inline-flex; align-items: center; gap: 6px; }
.chart-legend i { width: 9px; height: 9px; border-radius: 50%; }
.chart-legend .blue { background: var(--primary); }
.chart-legend .cyan { background: #18a7a0; }
.rhythm-grid { display: grid; grid-template-columns: 36px repeat(7, 1fr); gap: 5px; align-items: center; }
.rhythm-grid b, .rhythm-grid em { color: var(--muted); font-size: 11px; font-style: normal; text-align: center; }
.rhythm-grid button { aspect-ratio: 1.9; border: 0; border-radius: 3px; }
.level-0 { background: #edf3fb; }.level-1 { background: #cfe0ff; }.level-2 { background: #9fc0ff; }.level-3 { background: #5d91f4; }.level-4 { background: #2f6feb; }
.mastery-record-table { overflow-x: auto; }
.mastery-record-table table { width: 100%; min-width: 760px; border-collapse: collapse; }
.mastery-record-table th, .mastery-record-table td { padding: 10px 12px; border-bottom: 1px solid var(--divider); color: var(--body); font-size: 12px; text-align: left; }
.mastery-record-table th { color: var(--heading); background: #f7f9fc; font-weight: 800; }
.mastery-record-table tr:hover, .mastery-record-table tr:focus-visible { background: #f7faff; outline: 0; cursor: pointer; }
.record-drawer-backdrop { position: fixed; inset: 0; z-index: 60; background: rgba(16, 35, 63, .18); }
.record-drawer { position: fixed; top: 0; right: 0; z-index: 61; width: min(460px, 100vw); height: 100vh; padding: 26px; background: #fff; border-left: 1px solid var(--border); box-shadow: -12px 0 30px rgba(16, 35, 63, .12); overflow-y: auto; }
.drawer-close { position: absolute; top: 18px; right: 18px; }
.record-drawer h3 { margin: 18px 0 8px; font-size: 22px; }
.record-drawer dl { display: grid; gap: 10px; margin: 22px 0; }
.record-drawer dl > div { display: flex; justify-content: space-between; gap: 16px; padding-bottom: 10px; border-bottom: 1px solid var(--divider); }
.record-drawer dt { color: var(--muted); font-size: 12px; }
.record-drawer dd { margin: 0; color: var(--heading); font-size: 12px; font-weight: 700; text-align: right; }
@media (max-width: 1120px) {
  .record-filters, .record-main-grid { grid-template-columns: 1fr; }
  .record-row { grid-template-columns: 36px minmax(0, 1fr) 88px 18px; }
  .record-duration, .record-result, .record-row .button { display: none; }
}
@media (max-width: 680px) {
  .record-tabs, .record-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .record-summary > div { border-right: 0; border-bottom: 1px solid var(--divider); }
  .record-row { grid-template-columns: 32px minmax(0, 1fr) 16px; }
  .record-row time { display: none; }
}
</style>
