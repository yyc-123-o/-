import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to) {
    if (to.hash) return { el: to.hash, behavior: "smooth", top: 88 };
    return { top: 0 };
  },
  routes: [
    { path: "/", name: "home", component: () => import("@/views/LandingView.vue"), meta: { title: "产品首页", public: true } },
    { path: "/login", name: "login", component: () => import("@/views/LoginView.vue"), meta: { title: "登录", public: true } },
    { path: "/register", name: "register", component: () => import("@/views/RegisterView.vue"), meta: { title: "注册", public: true } },
    { path: "/app", name: "app", component: () => import("@/views/DashboardView.vue"), meta: { title: "平台首页" } },
    { path: "/dashboard", redirect: "/app" },
    { path: "/knowledge-base", redirect: "/resources" },
    { path: "/planning", redirect: "/learning-path" },
    { path: "/diagnosis", name: "diagnosis", component: () => import("@/views/DiagnosisView.vue"), meta: { title: "学情诊断" } },
    { path: "/diagnosis/basic", name: "diagnosis-basic", component: () => import("@/views/DiagnosisBasicView.vue"), meta: { title: "基础信息" } },
    { path: "/diagnosis/assessment", name: "diagnosis-assessment", component: () => import("@/views/DiagnosisAssessmentView.vue"), meta: { title: "知识水平评估" } },
    { path: "/profile", name: "profile", component: () => import("@/views/ProfileView.vue"), meta: { title: "学习者画像" } },
    { path: "/learning-path", name: "learning-path", component: () => import("@/views/LearningPathView.vue"), meta: { title: "课程规划" } },
    { path: "/resources", name: "resources", component: () => import("@/views/ResourcesView.vue"), meta: { title: "知识库" } },
    { path: "/assessment", name: "assessment", component: () => import("@/views/AssessmentView.vue"), meta: { title: "测评与反馈" } },
    { path: "/history", name: "history", component: () => import("@/views/HistoryView.vue"), meta: { title: "学习历史" } },
    { path: "/profile/settings", name: "settings", component: () => import("@/views/SettingsView.vue"), meta: { title: "个人中心" } },
  ],
});

router.afterEach((to) => {
  const title = String(to.meta.title || "平台首页");
  document.title = `${title} | 织知成径`;
});

export default router;
