<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  ArrowRight,
  Filter,
  Maximize2,
  Network,
  Play,
  RefreshCw,
  Search,
} from "lucide-vue-next";
import { useRoute, useRouter } from "vue-router";
import KnowledgeGraphCanvas from "@/components/KnowledgeGraphCanvas.vue";
import StateBlocks from "@/components/StateBlocks.vue";
import { useLearningPathStore } from "@/stores/learningPath";
import { useLearnerStore } from "@/stores/learner";
import type { KnowledgeNode, KnowledgeStatus } from "@/types/knowledgeGraph";
import { formatMastery } from "@/utils/mastery";
import {
  adaptPathNodes,
  canonicalCourseId,
  courseIdFromProfile,
  courseTitle,
  knowledgeTitle,
} from "@/utils/knowledgeGraph";

type ViewMode = "recommended" | "all" | "learned";

const route = useRoute();
const router = useRouter();
const path = useLearningPathStore();
const learner = useLearnerStore();
const savedCourseId = typeof window !== "undefined" ? window.localStorage.getItem("zhijing.learning-path.course") || "" : "";
const selectedId = ref(typeof route.query.kp === "string" ? route.query.kp : "");
const selectedCourseId = ref(typeof route.query.course === "string" ? route.query.course : savedCourseId);
const viewMode = ref<ViewMode>("recommended");
const searchQuery = ref("");
const domainFilter = ref("all");
const zoom = ref(1);
const fitKey = ref(0);

const profile = computed(() => learner.profile);
const profileCourseId = computed(() => courseIdFromProfile(profile.value));
const courseOptions = computed(() => {
  const ids = new Set<string>();
  if (profileCourseId.value) ids.add(canonicalCourseId(profileCourseId.value));
  path.nodes.forEach((node) => {
    if (node.chapter_id) ids.add(canonicalCourseId(node.chapter_id));
  });
  return [...ids]
    .filter(Boolean)
    .map((id) => ({
      id,
      title: id === canonicalCourseId(profileCourseId.value)
        ? profile.value?.learning_scope?.chapter_name || courseTitle(id)
        : courseTitle(id),
    }));
});
const courseId = computed(() => selectedCourseId.value || canonicalCourseId(profileCourseId.value));
const courseName = computed(() => courseTitle(courseId.value));
const courseTarget = computed(() => profile.value?.learning_scope?.primary_kp_name || "完成学情诊断后生成");
const normalizedPath = computed(() => adaptPathNodes(path.nodes, {
  courseId: courseId.value,
  profile: profile.value,
  snapshot: learner.snapshot,
  learningProgress: path.run?.learning_progress,
}));
const graphNodes = computed(() => normalizedPath.value.nodes);
const graphEdges = computed(() => normalizedPath.value.edges);
const summary = computed(() => normalizedPath.value.summary);
const recommendedNode = computed(() =>
  graphNodes.value.find((node) => node.id === summary.value.recommendedNodeId) || null,
);
const currentNode = computed(() => recommendedNode.value);
const selectedNode = computed(() => {
  if (selectedId.value) {
    const selected = graphNodes.value.find((node) => node.id === selectedId.value);
    if (selected) return selected;
  }
  return recommendedNode.value;
});
const selectedNodeStatus = computed<KnowledgeStatus | "">(() => selectedNode.value?.status || "");
const selectedMastery = computed(() => formatMastery(selectedNode.value?.mastery));
const domainOptions = computed(() => [...new Set(graphNodes.value.map((node) => node.domain))]);
const recommendedPathIds = computed(() => new Set(summary.value.recommendedPathNodeIds));
const visibleIds = computed(() => {
  if (viewMode.value === "all") return new Set(graphNodes.value.map((node) => node.id));
  if (viewMode.value === "learned") {
    return new Set(graphNodes.value.filter((node) => node.status === "mastered").map((node) => node.id));
  }
  const ids = new Set(summary.value.recommendedPathNodeIds);
  let frontier = [...ids];
  for (let depth = 0; depth < 2; depth += 1) {
    const next: string[] = [];
    graphEdges.value.forEach((edge) => {
      if (frontier.includes(edge.source) && !ids.has(edge.target)) {
        ids.add(edge.target);
        next.push(edge.target);
      }
    });
    frontier = next;
  }
  return ids;
});
const filteredNodes = computed(() => {
  const query = searchQuery.value.trim().toLowerCase();
  return graphNodes.value.filter((node) => {
    if (!visibleIds.value.has(node.id)) return false;
    if (domainFilter.value !== "all" && node.domain !== domainFilter.value) return false;
    if (!query) return true;
    return `${node.title} ${node.domain} ${node.stage}`.toLowerCase().includes(query);
  });
});
const filteredNodeIds = computed(() => new Set(filteredNodes.value.map((node) => node.id)));
const filteredEdges = computed(() =>
  graphEdges.value.filter((edge) => filteredNodeIds.value.has(edge.source) && filteredNodeIds.value.has(edge.target)),
);
const selectedPrerequisites = computed(() =>
  (selectedNode.value?.prerequisiteIds || [])
    .map((id) => graphNodes.value.find((node) => node.id === id))
    .filter((node): node is KnowledgeNode => Boolean(node)),
);
const unlockedNodes = computed(() =>
  selectedNode.value
    ? graphNodes.value
      .filter((node) => node.prerequisiteIds.includes(selectedNode.value?.id || ""))
      .slice(0, 3)
    : [],
);
const missingPrerequisites = computed(() =>
  (selectedNode.value?.prerequisiteIds || [])
    .filter((id) => !graphNodes.value.some((node) => node.id === id))
    .map((id) => knowledgeTitle(id)),
);
const graphStatusText = computed(() => {
  if (path.loading) return "正在生成学习路径";
  if (path.error) return "路径规划暂时失败，原有数据仍然保留";
  if (!courseId.value) return "完成诊断后生成";
  if (!graphNodes.value.length) return "当前课程的知识图谱尚未生成";
  return `${summary.value.masteredNodes} / ${summary.value.totalNodes} 个知识点已掌握`;
});
const recommendationReason = computed(() => {
  const node = selectedNode.value;
  if (!node) return "完成学情诊断并生成路径后，这里会显示推荐依据。";
  const readyPrerequisites = selectedPrerequisites.value.filter((item) => (item.mastery ?? 0) >= 0.6).length;
  if (node.status === "recommended" && readyPrerequisites) {
    return `你已掌握${selectedPrerequisites.value.slice(0, 2).map((item) => item.title).join("、")}，该节点的先修条件已经满足。`;
  }
  if (node.status === "recommended" && node.mastery !== null && node.mastery < 0.6) {
    return `最近记录中，该知识点掌握度为 ${formatMastery(node.mastery)}，系统建议优先补强。`;
  }
  if (node.status === "locked") {
    return missingPrerequisites.value.length
      ? `需要先完成${missingPrerequisites.value.slice(0, 2).join("、")}等前置内容。`
      : "一个或多个先修知识尚未达到解锁阈值。";
  }
  if (unlockedNodes.value.length) {
    return `完成后可继续学习${unlockedNodes.value.slice(0, 2).map((item) => item.title).join("、")}。`;
  }
  return node.reasonCodes.includes("mastery_missing")
    ? "当前还没有足够的测评证据，建议先完成一次诊断或预学习。"
    : "该节点属于当前课程知识网络，路径会根据学习反馈继续调整。";
});
const actionLabel = computed(() => {
  if (!selectedNode.value) return "开始诊断";
  if (selectedNodeStatus.value === "locked") return "先完成前置内容";
  if (selectedNodeStatus.value === "mastered") return "复习知识点";
  if (selectedNodeStatus.value === "completed") return "去完成测评";
  if (selectedNodeStatus.value === "learning") return "继续学习";
  if (selectedNodeStatus.value === "unevaluated") return "开始诊断";
  return "开始学习";
});
const actionDisabled = computed(() => !selectedNode.value || selectedNodeStatus.value === "locked");

function selectNode(id: string) {
  selectedId.value = id;
  void router.replace({ query: { ...route.query, kp: id } });
  const node = graphNodes.value.find((item) => item.id === id);
  if (node?.status === "available" && path.run) void path.startNode(id);
}

function jumpToNode(id: string) {
  if (!graphNodes.value.some((node) => node.id === id)) return;
  selectNode(id);
  viewMode.value = "all";
}

function generatePath() {
  void path.generate();
}

function selectCourse(value: string) {
  const nextCourseId = canonicalCourseId(value);
  if (!nextCourseId || nextCourseId === courseId.value) return;
  selectedCourseId.value = nextCourseId;
  selectedId.value = "";
  viewMode.value = "recommended";
  searchQuery.value = "";
  domainFilter.value = "all";
  void router.replace({
    query: {
      ...route.query,
      course: nextCourseId,
      kp: undefined,
    },
  });
}

function openPathSettings() {
  void router.push("/profile");
}

function openSelectedResource() {
  if (actionDisabled.value) return;
  if (selectedNodeStatus.value === "completed") {
    void router.push("/assessment");
    return;
  }
  void router.push("/resources");
}

watch(() => route.query.kp, (value) => {
  selectedId.value = typeof value === "string" ? value : "";
});

watch(() => route.query.course, (value) => {
  if (typeof value === "string" && value !== selectedCourseId.value) {
    selectedCourseId.value = canonicalCourseId(value);
  }
});

watch([profileCourseId, () => path.nodes.length], () => {
  if (selectedCourseId.value) return;
  const fallback = profileCourseId.value || courseOptions.value[0]?.id;
  if (fallback) selectedCourseId.value = canonicalCourseId(fallback);
}, { immediate: true });

watch(courseId, (value) => {
  if (!value) return;
  if (typeof window !== "undefined") window.localStorage.setItem("zhijing.learning-path.course", canonicalCourseId(value));
  if (route.query.course !== canonicalCourseId(value)) {
    void router.replace({ query: { ...route.query, course: canonicalCourseId(value) } });
  }
}, { immediate: true });

onMounted(() => {
  if (learner.snapshot && path.run?.profile_id !== learner.snapshot.profile_id) void path.generate();
});
</script>

<template>
  <div class="path-reference-page page-stack">
    <header class="path-reference-header path-reference-header--rebuilt">
      <div class="path-title-block">
        <div class="path-breadcrumb">智数助手 <span>/</span> 学习路径</div>
        <h2>学习路径</h2>
        <p>根据你的诊断结果、学习目标和学习记录动态生成。</p>
        <div class="path-course-context">
          <label for="path-course">当前课程</label>
          <select
            id="path-course"
            :value="courseId || ''"
            :disabled="courseOptions.length <= 1"
            @change="selectCourse(($event.target as HTMLSelectElement).value)"
          >
            <option v-if="!courseOptions.length" value="">完成诊断后生成</option>
            <option v-for="course in courseOptions" :key="course.id" :value="course.id">{{ course.title }}</option>
          </select>
          <span>课程目标：{{ courseTarget }}</span>
        </div>
      </div>
      <div class="path-header-actions">
        <button type="button" class="button button-secondary" :disabled="path.loading" @click="generatePath">
          <RefreshCw :size="16" />
          {{ path.loading ? "规划中" : "重新规划" }}
        </button>
        <button type="button" class="path-settings-link" @click="openPathSettings">路径设置</button>
      </div>
    </header>

    <section v-if="path.error" class="path-inline-error">
      {{ graphStatusText }}
      <button type="button" class="text-link" @click="generatePath">重试</button>
    </section>

    <section v-if="!courseId || (!graphNodes.length && !path.loading)" class="panel path-empty-panel">
      <StateBlocks
        type="empty"
        :title="courseId ? '当前课程的知识图谱尚未生成' : '完成诊断后生成学习路径'"
        :message="courseId ? '当前课程暂时没有可用的知识节点和先修关系。' : '完成学情诊断后，系统会依据当前课程生成个性化路径。'"
      />
      <button type="button" class="button button-primary" @click="courseId ? generatePath() : router.push('/diagnosis')">
        {{ courseId ? "重新生成图谱" : "进入学情诊断" }} <ArrowRight :size="16" />
      </button>
    </section>

    <template v-else>
      <section class="path-summary-strip path-summary-strip--rebuilt">
        <div class="path-summary-progress">
          <span>路径进度</span>
          <strong>{{ summary.totalNodes ? Math.round(summary.masteredNodes / summary.totalNodes * 100) : 0 }}%</strong>
          <div class="progress-track"><span :style="{ width: `${summary.totalNodes ? summary.masteredNodes / summary.totalNodes * 100 : 0}%` }" /></div>
        </div>
        <div><span>已掌握知识点</span><strong>{{ summary.masteredNodes }} <small>/ {{ summary.totalNodes }}</small></strong></div>
        <div><span>当前推荐</span><strong>{{ recommendedNode?.title || "暂无推荐" }}</strong></div>
        <div><span>平均掌握度</span><strong>{{ formatMastery(summary.averageMastery) }}</strong></div>
        <div><span>预计剩余时间</span><strong>{{ summary.estimatedRemainingMinutes ? `${Math.ceil(summary.estimatedRemainingMinutes / 60)} 小时` : "暂无数据" }}</strong></div>
      </section>

      <div class="path-reference-layout path-reference-layout--rebuilt">
        <section id="knowledge-graph" class="panel graph-reference-panel graph-reference-panel--rebuilt">
          <div class="graph-panel-heading">
            <div>
              <h3>知识图谱</h3>
              <p>节点由当前课程的真实先修关系自动布局，箭头表示学习方向。</p>
            </div>
            <span class="path-status-text"><i />{{ graphStatusText }}</span>
          </div>

          <div class="graph-toolbar graph-toolbar--rebuilt">
            <div class="graph-view-tabs" role="tablist" aria-label="图谱视图">
              <button type="button" :class="{ active: viewMode === 'recommended' }" @click="viewMode = 'recommended'">推荐路径</button>
              <button type="button" :class="{ active: viewMode === 'all' }" @click="viewMode = 'all'">完整图谱</button>
              <button type="button" :class="{ active: viewMode === 'learned' }" @click="viewMode = 'learned'">已学习</button>
            </div>
            <label class="graph-search">
              <Search :size="15" />
              <input v-model="searchQuery" type="search" placeholder="搜索知识点" aria-label="搜索知识点" />
            </label>
            <label class="graph-filter">
              <Filter :size="15" />
              <select v-model="domainFilter" aria-label="筛选知识领域">
                <option value="all">全部领域</option>
                <option v-for="domain in domainOptions" :key="domain" :value="domain">{{ domain }}</option>
              </select>
            </label>
            <button type="button" class="graph-tool-button" title="适应画布" aria-label="适应画布" @click="fitKey += 1">
              <Maximize2 :size="15" />
            </button>
          </div>

          <div class="graph-legend graph-legend--rebuilt">
            <span><i class="legend-dot legend-dot--current" />当前推荐</span>
            <span><i class="legend-dot legend-dot--available" />未学习 · 可开始</span>
            <span><i class="legend-dot legend-dot--learning" />学习中</span>
            <span><i class="legend-dot legend-dot--mastered" />已掌握 · 颜色越深掌握度越高</span>
            <span><i class="legend-dot legend-dot--blocked" />先修未满足</span>
          </div>

          <KnowledgeGraphCanvas
            :nodes="filteredNodes"
            :edges="filteredEdges"
            :selected-id="selectedNode?.id"
            :recommended-path-node-ids="[...recommendedPathIds]"
            :zoom="zoom"
            :fit-key="fitKey"
            @select="selectNode"
            @update:zoom="zoom = $event"
          />
          <p v-if="filteredNodes.length !== graphNodes.length" class="graph-filter-note">
            当前显示 {{ filteredNodes.length }} / {{ graphNodes.length }} 个节点
          </p>
        </section>

        <aside class="path-detail-panel path-detail-panel--rebuilt">
          <section class="panel path-node-detail path-node-detail--rebuilt">
            <div class="detail-panel-topline">
              <span class="path-current-indicator"><i />{{ selectedNodeStatus === "recommended" ? "当前推荐" : selectedNodeStatus === "mastered" ? "已掌握" : selectedNodeStatus === "completed" ? "已完成·待测评" : selectedNodeStatus === "learning" ? "学习中" : selectedNodeStatus === "locked" ? "先修未满足" : "尚未评估" }}</span>
              <Network :size="18" class="detail-panel-icon" />
            </div>
            <h3>{{ selectedNode?.title || "选择一个知识节点" }}</h3>
            <div v-if="selectedNode" class="detail-node-meta">
              <span>{{ selectedNode.domain }}</span>
              <span>{{ selectedNode.difficulty }}</span>
              <span>{{ selectedNode.stage }}</span>
            </div>
            <div v-if="selectedNode" class="detail-mastery">
              <span>当前掌握度</span>
              <strong>{{ selectedMastery }}</strong>
              <div class="progress-track"><span :style="{ width: selectedNode.mastery === null ? '0%' : `${selectedNode.mastery * 100}%` }" /></div>
              <small>{{ selectedNode.mastery === null ? "尚未形成有效测评证据" : "掌握度来自当前学习者的诊断与测评记录" }}</small>
            </div>
            <div class="detail-explanation">
              <h4>为什么推荐</h4>
              <p>{{ recommendationReason }}</p>
            </div>
            <div v-if="selectedPrerequisites.length || missingPrerequisites.length" class="detail-relation">
              <h4>先修知识</h4>
              <button v-for="node in selectedPrerequisites" :key="node.id" type="button" @click="jumpToNode(node.id)">
                <span>{{ node.title }}</span><small>{{ formatMastery(node.mastery) }}</small>
              </button>
              <span v-for="item in missingPrerequisites" :key="item" class="detail-relation-missing">{{ item }} · 课程前置内容</span>
            </div>
            <div v-if="unlockedNodes.length" class="detail-relation detail-relation--unlock">
              <h4>完成后解锁</h4>
              <button v-for="node in unlockedNodes" :key="node.id" type="button" @click="jumpToNode(node.id)">
                <span>{{ node.title }}</span><small>{{ node.status === "locked" ? "待解锁" : "可学习" }}</small>
              </button>
            </div>
            <div v-if="selectedNode" class="detail-resource-summary">
              <div><span>课程讲义</span><b>{{ selectedNode.resourceCount || "暂无数据" }}</b></div>
              <div><span>练习与测评</span><b>{{ selectedNode.assessmentCount || "暂无数据" }}</b></div>
              <div><span>预计学习</span><b>{{ selectedNode.estimatedMinutes ? `${selectedNode.estimatedMinutes} 分钟` : "暂无数据" }}</b></div>
            </div>
            <button
              type="button"
              class="button button-primary button-full"
              :disabled="actionDisabled"
              :title="actionDisabled ? '请先完成前置知识' : undefined"
              @click="openSelectedResource"
            >
              <Play :size="16" /> {{ actionLabel }}
            </button>
            <p v-if="actionDisabled" class="detail-disabled-hint">完成前置知识后才能开始此节点。</p>
          </section>
        </aside>
      </div>
    </template>
  </div>
</template>
