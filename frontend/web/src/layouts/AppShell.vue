<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import {
  BarChart3, BookOpen, BrainCircuit, ChevronDown, Clock3, Compass,
  GraduationCap, History, Home, Library, Menu, Settings2, Sparkles, UserRound, X,
} from "lucide-vue-next";
import { useLearnerStore } from "@/stores/learner";

const route = useRoute();
const learner = useLearnerStore();
const mobileOpen = ref(false);
const navItems = [
  { label: "学习首页", to: "/dashboard", icon: Home },
  { label: "学情诊断", to: "/diagnosis", icon: BrainCircuit },
  { label: "学习者画像", to: "/profile", icon: UserRound },
  { label: "我的学习路径", to: "/learning-path", icon: Compass },
  { label: "学习资源", to: "/resources", icon: Library },
  { label: "测评反馈", to: "/assessment", icon: BarChart3 },
  { label: "学习历史", to: "/history", icon: History },
  { label: "个人中心", to: "/profile/settings", icon: Settings2 },
];
const pageTitle = computed(() => (route.meta.title as string) || "学习工作台");

onMounted(() => learner.loadLearners());
</script>

<template>
  <div class="app-shell">
    <div v-if="mobileOpen" class="mobile-backdrop" @click="mobileOpen = false" />
    <aside class="sidebar" :class="{ 'is-open': mobileOpen }">
      <div class="sidebar-head">
        <RouterLink to="/dashboard" class="brand" @click="mobileOpen = false">
          <span class="brand-mark">知</span>
          <span><strong>知径</strong><small>AI 个性化学习平台</small></span>
        </RouterLink>
        <button class="icon-button sidebar-close" title="关闭导航" @click="mobileOpen = false"><X :size="18" /></button>
      </div>
      <div class="workspace-label">学习空间</div>
      <nav class="side-nav">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="nav-item"
          :class="{ active: route.path === item.to || (item.to === '/diagnosis' && route.path.startsWith('/diagnosis/')) }"
          @click="mobileOpen = false"
        >
          <component :is="item.icon" :size="18" :stroke-width="1.8" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="sidebar-course">
        <span class="eyebrow">当前课程</span>
        <strong>AI 与机器学习基础</strong>
        <span class="muted-text">诊断范围：核心知识图谱</span>
        <div class="progress-track"><span :style="{ width: learner.profile ? '72%' : '28%' }" /></div>
        <div class="course-progress-label"><span>学习进度</span><b>{{ learner.profile ? "72%" : "28%" }}</b></div>
      </div>
      <div class="sidebar-status"><span class="online-dot" /><span>系统状态</span><b>API {{ learner.error ? "异常" : "正常" }}</b></div>
    </aside>

    <main class="main-column">
      <header class="topbar">
        <div class="topbar-left">
          <button class="icon-button mobile-menu" title="打开导航" @click="mobileOpen = true"><Menu :size="20" /></button>
          <div>
            <div class="breadcrumb">AI 与机器学习基础 <span>/</span> {{ pageTitle }}</div>
            <h1>{{ pageTitle }}</h1>
          </div>
        </div>
        <div class="topbar-actions">
          <span class="sync-label"><span class="online-dot" />数据实时同步</span>
          <RouterLink to="/profile/settings" class="user-chip" title="个人中心">
            <span class="avatar">张</span>
            <span class="user-chip-copy"><b>{{ learner.learnerName }}</b><small>学习者</small></span>
            <ChevronDown :size="15" />
          </RouterLink>
        </div>
      </header>
      <RouterView />
    </main>

    <aside class="right-rail">
      <div class="rail-status"><span class="eyebrow">LEARNER STATUS</span><span class="status-pill status-pill-success">实时</span></div>
      <div class="rail-profile">
        <div class="avatar avatar-large">{{ learner.profile?.learner?.name?.slice(0, 1) || "学" }}</div>
        <strong>{{ learner.learnerName }}</strong>
        <span>{{ learner.profile?.learner?.education?.major || "完成诊断后生成你的学习画像" }}</span>
      </div>
      <div class="rail-metric"><span>总体掌握度</span><b>{{ learner.profile ? `${Math.round(learner.mastery * 100)}%` : "待诊断" }}</b></div>
      <div class="rail-metric"><span>薄弱知识点</span><b>{{ learner.profile ? learner.weakPoints.length : "—" }}</b></div>
      <div class="rail-next">
        <span class="eyebrow">NEXT ACTION</span>
        <strong>{{ learner.profile ? "生成你的个性化路径" : "完成学情诊断" }}</strong>
        <RouterLink :to="learner.profile ? '/learning-path' : '/diagnosis'" class="text-link">继续前往 <span>→</span></RouterLink>
      </div>
      <div class="rail-ai">
        <div class="ai-label"><span class="ai-mark"><Sparkles :size="13" /></span><span>AI 学习顾问</span></div>
        <p>{{ learner.profile ? "我会根据你的掌握度和学习目标，推荐下一步最合适的学习内容。" : "完成几个问题后，我会帮你识别优势与薄弱点。" }}</p>
      </div>
      <div class="rail-time"><Clock3 :size="16" /><span>今天建议学习 <b>25 分钟</b></span></div>
    </aside>
  </div>
</template>
