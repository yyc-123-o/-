import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", meta: { title: "知径 | AI 个性化学习平台", layout: "public" }, component: () => import("@/views/LandingView.vue") },
    { path: "/dashboard", meta: { title: "首页 Dashboard" }, component: () => import("@/views/DashboardView.vue") },
    { path: "/diagnosis", meta: { title: "学情诊断" }, component: () => import("@/views/DiagnosisView.vue") },
    { path: "/diagnosis/basic", meta: { title: "基础信息" }, component: () => import("@/views/DiagnosisBasicView.vue") },
    { path: "/diagnosis/assessment", meta: { title: "知识水平评估" }, component: () => import("@/views/DiagnosisAssessmentView.vue") },
    { path: "/profile", meta: { title: "学习者画像" }, component: () => import("@/views/ProfileView.vue") },
    { path: "/learning-path", meta: { title: "我的学习路径" }, component: () => import("@/views/LearningPathView.vue") },
    { path: "/resources", meta: { title: "学习资源" }, component: () => import("@/views/ResourcesView.vue") },
    { path: "/assessment", meta: { title: "测评反馈" }, component: () => import("@/views/AssessmentView.vue") },
    { path: "/history", meta: { title: "学习历史" }, component: () => import("@/views/HistoryView.vue") },
    { path: "/profile/settings", meta: { title: "个人中心" }, component: () => import("@/views/SettingsView.vue") },
  ],
  scrollBehavior: (to) => (to.hash ? { el: to.hash, behavior: "smooth" } : { top: 0 }),
});

export default router;
