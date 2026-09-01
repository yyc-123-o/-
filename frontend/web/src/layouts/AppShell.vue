<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import {
  Bell,
  BookOpenCheck,
  BrainCircuit,
  ChevronDown,
  Database,
  GitBranch,
  History,
  Home,
  Library,
  Menu,
  ChevronLeft,
  ChevronRight,
  Settings2,
  UserRound,
  Workflow,
  X,
} from "lucide-vue-next";
import BrandWordmark from "@/components/layout/BrandWordmark.vue";
import { useLearnerStore } from "@/stores/learner";

const route = useRoute();
const learner = useLearnerStore();
const mobileOpen = ref(false);
const sidebarCollapsed = ref(false);
const sidebarAnimating = ref(false);
let sidebarToggleTimer: number | undefined;

const navItems = [
  { label: "首页", to: "/dashboard", icon: Home },
  { label: "知识库", to: "/resources", icon: Database },
  { label: "知识图谱", to: "/learning-path", icon: GitBranch },
  { label: "学情诊断", to: "/diagnosis", icon: BrainCircuit },
  { label: "课程规划", to: "/learning-path", icon: BookOpenCheck },
  { label: "Agent 工作流", to: "/dashboard#agents", icon: Workflow },
  { label: "资源中心", to: "/resources", icon: Library },
  { label: "测评与反馈", to: "/assessment", icon: History },
];

const isHome = computed(() => route.path === "/" || route.path === "/dashboard");
const pageTitle = computed(() => String(route.meta.title || "平台工作区"));
const apiLabel = computed(() => {
  if (learner.loading) return "同步中";
  if (learner.error) return "接口待连接";
  if (learner.learners.length || learner.profile) return "接口已同步";
  return "等待数据";
});
const avatarText = computed(() => learner.profile?.learner.name?.slice(0, 1) || "智");

function isActive(to: string) {
  const [path, hash] = to.split("#");
  if (hash) return route.path === path && route.hash === `#${hash}`;
  if (path === "/dashboard") return isHome.value && !route.hash;
  if (path === "/learning-path") return route.path === "/learning-path";
  if (path === "/resources") return route.path === "/resources";
  return route.path === path || route.path.startsWith(`${path}/`);
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
</script>

<template>
  <div class="app-shell" :class="{ 'is-sidebar-collapsed': sidebarCollapsed, 'is-nav-animating': sidebarAnimating }">
    <div v-if="mobileOpen" class="mobile-backdrop" @click="mobileOpen = false" />

    <aside class="sidebar" :class="{ 'is-open': mobileOpen }">
      <div class="sidebar-head">
        <BrandWordmark to="/dashboard" compact class="brand-link" @click="mobileOpen = false" />
        <button class="icon-button sidebar-close" title="关闭导航" @click="mobileOpen = false">
          <X :size="18" />
        </button>
      </div>

      <nav class="side-nav" aria-label="平台导航">
        <RouterLink
          v-for="item in navItems"
          :key="item.label"
          :to="item.to"
          class="nav-item"
          :class="{ active: isActive(item.to) }"
          active-class="router-link-active-muted"
          exact-active-class="router-link-exact-active-muted"
          :title="sidebarCollapsed ? item.label : undefined"
          @click="mobileOpen = false"
        >
          <component :is="item.icon" :size="18" :stroke-width="1.8" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <RouterLink
        to="/profile/settings"
        class="nav-item sidebar-settings"
        :class="{ active: route.path === '/profile/settings' }"
        title="设置"
        @click="mobileOpen = false"
      >
        <Settings2 :size="18" :stroke-width="1.8" />
        <span>设置</span>
      </RouterLink>

      <button class="sidebar-toggle-tab" :title="sidebarCollapsed ? '展开导航' : '收起导航'" @click="toggleSidebar">
        <ChevronRight v-if="sidebarCollapsed" :size="17" />
        <ChevronLeft v-else :size="17" />
      </button>

      <div class="sidebar-course">
        <span class="eyebrow">当前工作空间</span>
        <strong>课程知识库治理</strong>
        <span class="muted-text">知识库、图谱、诊断、规划和资源生成协同运行</span>
        <div class="progress-track"><span :style="{ width: learner.profile ? '58%' : '22%' }" /></div>
        <div class="course-progress-label">
          <span>{{ learner.profile ? "画像已接入" : "等待学情输入" }}</span>
          <b>{{ learner.profile ? "规划可运行" : "待诊断" }}</b>
        </div>
      </div>

      <div class="sidebar-status">
        <span class="online-dot" :class="{ muted: learner.error }" />
        <span>系统状态</span>
        <b>{{ apiLabel }}</b>
      </div>
    </aside>

    <main class="main-column">
      <header class="topbar">
        <div class="topbar-left">
          <button class="icon-button mobile-menu" title="打开导航" @click="mobileOpen = true">
            <Menu :size="20" />
          </button>
          <div>
            <div class="breadcrumb">智数助手 <span>/</span> {{ pageTitle }}</div>
            <h1>{{ pageTitle }}</h1>
          </div>
        </div>

        <div class="topbar-actions">
          <span class="sync-label"><span class="online-dot" :class="{ muted: learner.error }" />{{ apiLabel }}</span>
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

      <RouterView :key="route.fullPath" />
    </main>
  </div>
</template>
