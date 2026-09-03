<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import {
  Bell,
  BookOpen,
  BookOpenCheck,
  BrainCircuit,
  ChevronDown,
  GitBranch,
  History,
  Home,
  LayoutDashboard,
  LibraryBig,
  Menu,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  FileStack,
  ScanSearch,
  Settings2,
  UserRound,
  X,
  Route,
} from "lucide-vue-next";
import BrandWordmark from "@/components/layout/BrandWordmark.vue";
import { useLearnerStore } from "@/stores/learner";
import { useLearningPathStore } from "@/stores/learningPath";
import { adaptPathNodes, courseIdFromProfile } from "@/utils/knowledgeGraph";

type NavIcon = typeof Home;

interface NavLink {
  label: string;
  to: string;
  icon: NavIcon;
}

interface NavGroup {
  key: string;
  label: string;
  icon: NavIcon;
  items: NavLink[];
}

const route = useRoute();
const learner = useLearnerStore();
const learningPath = useLearningPathStore();
const mobileOpen = ref(false);
const sidebarCollapsed = ref(false);
const sidebarAnimating = ref(false);
const courseExpanded = ref(false);
const diagnosisExpanded = ref(false);
const resourceExpanded = ref(false);
let sidebarToggleTimer: number | undefined;

const primaryLinks: NavLink[] = [
  { label: "我的学习", to: "/app", icon: Home },
  { label: "学习路径", to: "/learning-path", icon: Route },
  { label: "学习记录", to: "/history", icon: History },
];

const primaryTailLinks: NavLink[] = [
  { label: "工作台", to: "/workspace", icon: LayoutDashboard },
  { label: "设置", to: "/profile/settings", icon: Settings2 },
];

const navGroups: NavGroup[] = [
  {
    key: "course",
    label: "课程中心",
    icon: LibraryBig,
    items: [
      { label: "课程知识库", to: "/resources#knowledge-base", icon: BookOpen },
      { label: "知识图谱", to: "/course-center/knowledge-graph", icon: GitBranch },
    ],
  },
  {
    key: "diagnosis",
    label: "学情中心",
    icon: BrainCircuit,
    items: [
      { label: "学情诊断", to: "/diagnosis", icon: ScanSearch },
      { label: "学习者画像", to: "/profile", icon: UserRound },
    ],
  },
  {
    key: "resource",
    label: "资源与测评",
    icon: FileStack,
    items: [
      { label: "课程资源", to: "/resources#learning-resources", icon: BookOpenCheck },
      { label: "测评反馈", to: "/assessment", icon: ClipboardCheck },
    ],
  },
];

const isHome = computed(() => route.path === "/app" || route.path === "/dashboard");
const isWorkspace = computed(() => route.path === "/workspace");
const pageTitle = computed(() => String(route.meta.title || "工作台"));
const breadcrumbTitle = computed(() => String(route.meta.breadcrumb || pageTitle.value));
const adaptedPath = computed(() => adaptPathNodes(learningPath.nodes, {
  courseId: courseIdFromProfile(learner.profile),
  profile: learner.profile,
  snapshot: learner.snapshot,
  learningProgress: learningPath.run?.learning_progress,
}));
const completedPathNodes = computed(() => adaptedPath.value.summary.masteredNodes);
const pathProgress = computed(() =>
  adaptedPath.value.summary.totalNodes ? completedPathNodes.value / adaptedPath.value.summary.totalNodes : 0,
);
const learningCourse = computed(() => learner.profile?.learning_scope?.chapter_name || "尚未选择课程");
const learningStage = computed(() => {
  if (!learner.profile) return "学情诊断";
  if (!learningPath.run) return "路径规划";
  if (adaptedPath.value.summary.recommendedNodeId) return "课程学习";
  return "学习完成";
});
const learningNextStep = computed(() => {
  if (!learner.profile) return "完成学情诊断";
  if (!learningPath.run) return "生成学习路径";
  const nextNode = adaptedPath.value.nodes.find((node) => node.id === adaptedPath.value.summary.recommendedNodeId);
  if (nextNode) {
    return `完成${nextNode.title}`;
  }
  return "查看学习记录";
});
const learningProgressLabel = computed(() => {
  if (!adaptedPath.value.summary.totalNodes) return "等待路径生成";
  return `${completedPathNodes.value} / ${adaptedPath.value.summary.totalNodes} 个节点`;
});
const systemStatus = computed(() => {
  if (learner.error || learningPath.error) {
    return { label: "AI 助学服务暂时不可用", tone: "unavailable", detail: "部分智能功能可能暂时不可使用" };
  }
  if (learner.loading || learningPath.loading) {
    return { label: "AI 助学服务准备中", tone: "preparing", detail: "正在准备你的学习数据" };
  }
  return { label: "AI 助学服务已就绪", tone: "ready", detail: "课程和学习功能可以继续使用" };
});
const avatarText = computed(() => learner.profile?.learner.name?.slice(0, 1) || "智");

function isActive(to: string) {
  const [path, hash] = to.split("#");
  if (hash) return route.path === path && route.hash === `#${hash}`;
  if (path === "/app") return isHome.value && !route.hash;
  if (route.hash) return false;
  return route.path === path || route.path.startsWith(`${path}/`);
}

function isGroupActive(group: NavGroup) {
  return group.items.some((item) => isActive(item.to));
}

function isGroupExpanded(group: NavGroup) {
  if (group.key === "course") return courseExpanded.value || isGroupActive(group);
  if (group.key === "diagnosis") return diagnosisExpanded.value || isGroupActive(group);
  return resourceExpanded.value || isGroupActive(group);
}

function toggleGroup(groupKey: string) {
  if (groupKey === "course") courseExpanded.value = !courseExpanded.value;
  if (groupKey === "diagnosis") diagnosisExpanded.value = !diagnosisExpanded.value;
  if (groupKey === "resource") resourceExpanded.value = !resourceExpanded.value;
}

function toggleSidebar() {
  sidebarAnimating.value = true;
  if (sidebarToggleTimer) window.clearTimeout(sidebarToggleTimer);
  requestAnimationFrame(() => {
    sidebarCollapsed.value = !sidebarCollapsed.value;
    sidebarToggleTimer = window.setTimeout(() => {
      sidebarAnimating.value = false;
    }, 260);
  });
}

onMounted(() => {
  document.body.classList.add("app-shell-active");
  void learner.loadLearners();
});

onUnmounted(() => {
  if (sidebarToggleTimer) window.clearTimeout(sidebarToggleTimer);
  document.body.classList.remove("app-shell-active");
});

watch(
  () => route.fullPath,
  () => {
    if (navGroups.some((group) => group.key === "course" && isGroupActive(group))) courseExpanded.value = true;
    if (navGroups.some((group) => group.key === "diagnosis" && isGroupActive(group))) diagnosisExpanded.value = true;
    if (navGroups.some((group) => group.key === "resource" && isGroupActive(group))) resourceExpanded.value = true;
  },
  { immediate: true },
);
</script>

<template>
  <div class="app-shell" :class="{ 'is-sidebar-collapsed': sidebarCollapsed, 'is-nav-animating': sidebarAnimating }">
    <div v-if="mobileOpen" class="mobile-backdrop" @click="mobileOpen = false" />

    <aside class="sidebar" :class="{ 'is-open': mobileOpen }">
      <div class="sidebar-head">
        <BrandWordmark to="/app" compact class="brand-link" @click="mobileOpen = false" />
        <button class="icon-button sidebar-close" title="关闭导航" @click="mobileOpen = false">
          <X :size="18" />
        </button>
      </div>

      <div class="sidebar-content">
        <nav class="side-nav primary-navigation" aria-label="平台导航">
          <RouterLink
            v-for="item in primaryLinks"
            :key="item.label"
            :to="item.to"
            class="nav-item"
            :class="{ active: isActive(item.to) }"
            :aria-current="isActive(item.to) ? 'page' : undefined"
            active-class="router-link-active-muted"
            exact-active-class="router-link-exact-active-muted"
            :title="sidebarCollapsed ? item.label : undefined"
            @click="mobileOpen = false"
          >
            <component :is="item.icon" :size="18" :stroke-width="1.8" />
            <span>{{ item.label }}</span>
          </RouterLink>

          <section
            v-for="group in navGroups"
            :key="group.key"
            class="nav-group"
            :class="{ 'is-active': isGroupActive(group), 'is-expanded': isGroupExpanded(group) }"
          >
            <button
              class="nav-group-trigger"
              type="button"
              :aria-expanded="isGroupExpanded(group)"
              :title="sidebarCollapsed ? group.label : undefined"
              @click="toggleGroup(group.key)"
            >
              <component :is="group.icon" :size="18" :stroke-width="1.8" />
              <span>{{ group.label }}</span>
              <ChevronDown :size="15" :class="{ rotated: isGroupExpanded(group) }" />
            </button>
            <Transition name="sidebar-subnav">
              <div v-show="isGroupExpanded(group) && !sidebarCollapsed" class="nav-subnav">
                <RouterLink
                  v-for="item in group.items"
                  :key="item.label"
                  :to="item.to"
                  class="nav-item nav-subitem"
                  :class="{ active: isActive(item.to) }"
                  :aria-current="isActive(item.to) ? 'page' : undefined"
                  :title="item.label"
                  @click="mobileOpen = false"
                >
                  <component :is="item.icon" :size="16" :stroke-width="1.8" />
                  <span>{{ item.label }}</span>
                </RouterLink>
              </div>
            </Transition>
          </section>

          <RouterLink
            v-for="item in primaryTailLinks"
            :key="item.label"
            :to="item.to"
            class="nav-item"
            :class="{ active: isActive(item.to) }"
            :aria-current="isActive(item.to) ? 'page' : undefined"
            active-class="router-link-active-muted"
            exact-active-class="router-link-exact-active-muted"
            :title="sidebarCollapsed ? item.label : undefined"
            @click="mobileOpen = false"
          >
            <component :is="item.icon" :size="18" :stroke-width="1.8" />
            <span>{{ item.label }}</span>
          </RouterLink>
        </nav>

        <div class="sidebar-spacer" aria-hidden="true" />

        <div class="sidebar-status-area">
          <div class="sidebar-course">
            <span class="eyebrow">当前学习进度</span>
            <strong>{{ learningCourse }}</strong>
            <span class="muted-text">{{ learner.profile ? "AI 正根据你的学习情况持续调整课程路径" : "完成学情诊断后，AI 将为你生成个性化学习路径" }}</span>
            <div class="course-progress-label">
              <span>学习进度</span>
              <b>{{ Math.round(pathProgress * 100) }}%</b>
            </div>
            <div class="progress-track"><span :style="{ width: `${Math.round(pathProgress * 100)}%` }" /></div>
            <div class="course-progress-label">
              <span>{{ learningProgressLabel }}</span>
              <b>{{ learningStage }}</b>
            </div>
            <span class="sidebar-next-step">下一步：{{ learningNextStep }}</span>
          </div>

          <div class="sidebar-status">
            <span class="online-dot" :class="`status-${systemStatus.tone}`" />
            <span>系统状态</span>
            <b>{{ systemStatus.label }}</b>
            <small>{{ systemStatus.detail }}</small>
          </div>
        </div>

        <div class="sidebar-user-area">
          <RouterLink
            to="/profile"
            class="sidebar-user"
            aria-label="进入个人中心"
            title="个人中心"
            @click="mobileOpen = false"
          >
            <span class="avatar">{{ avatarText }}</span>
            <span class="sidebar-user-copy">
              <b>{{ learner.profile?.learner?.name || learner.learnerName }}</b>
              <small>{{ learner.profile?.learner?.education?.level || "学习者" }} · 个人中心</small>
            </span>
            <ChevronRight :size="16" class="sidebar-user-chevron" />
          </RouterLink>
        </div>
      </div>

      <button class="sidebar-toggle-tab" :title="sidebarCollapsed ? '展开导航' : '收起导航'" @click="toggleSidebar">
        <ChevronRight v-if="sidebarCollapsed" :size="17" />
        <ChevronLeft v-else :size="17" />
      </button>
    </aside>

    <main class="main-column">
      <header class="topbar">
        <div class="topbar-left">
          <button class="icon-button mobile-menu" title="打开导航" @click="mobileOpen = true">
            <Menu :size="20" />
          </button>
          <div>
            <div class="breadcrumb">智数助手 <span>/</span> {{ breadcrumbTitle }}</div>
            <h1>{{ pageTitle }}</h1>
          </div>
        </div>

        <div class="topbar-actions">
          <span v-if="isWorkspace" class="sync-label"><span class="online-dot" :class="`status-${systemStatus.tone}`" />{{ systemStatus.label }}</span>
          <button class="icon-button topbar-icon" title="待处理通知">
            <Bell :size="18" />
          </button>
          <RouterLink to="/profile/settings" class="user-chip" title="个人中心">
            <span class="avatar">{{ avatarText }}</span>
            <span class="user-chip-copy">
              <b>{{ learner.learnerName }}</b>
              <small>平台用户</small>
            </span>
            <ChevronDown :size="15" />
          </RouterLink>
          <RouterLink to="/profile/settings" class="icon-button topbar-icon" title="设置">
            <Settings2 :size="18" />
          </RouterLink>
        </div>
      </header>

      <!-- 查询参数变化不应重新挂载页面，否则图谱缩放和拖拽状态会被重置。 -->
      <RouterView :key="String(route.name || route.path)" />
    </main>
  </div>
</template>
