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
    { path: "/app", name: "app", component: () => import("@/views/MyLearningView.vue"), meta: { title: "我的学习", menuKey: "app" } },
    { path: "/dashboard", redirect: "/app" },
    { path: "/workspace", name: "workspace", component: () => import("@/views/DashboardView.vue"), meta: { title: "工作台", menuKey: "workspace" } },
    { path: "/knowledge-base", redirect: "/courses" },
    { path: "/courses", name: "courses", component: () => import("@/views/CourseLibraryView.vue"), meta: { title: "课程库", breadcrumb: "课程中心 / 课程库", menuKey: "course-library", groupKey: "course" } },
    { path: "/courses/:courseId/knowledge", name: "course-knowledge", component: () => import("@/views/ResourcesView.vue"), meta: { title: "课程知识库", breadcrumb: "课程中心 / 课程知识库", menuKey: "course-library", groupKey: "course" } },
    { path: "/knowledge-graph", name: "knowledge-graph", component: () => import("@/views/KnowledgeGraphView.vue"), meta: { title: "知识图谱", breadcrumb: "课程中心 / 知识图谱", menuKey: "knowledge-graph", groupKey: "course" } },
    { path: "/course-center/knowledge-graph", redirect: (to) => ({ path: "/knowledge-graph", query: to.query, hash: to.hash }) },
    { path: "/planning", redirect: "/learning-path" },
    { path: "/diagnosis", name: "diagnosis", component: () => import("@/views/DiagnosisView.vue"), meta: { title: "学情诊断", menuKey: "diagnosis", groupKey: "diagnosis" } },
    { path: "/diagnosis/basic", name: "diagnosis-basic", component: () => import("@/views/DiagnosisBasicView.vue"), meta: { title: "基础信息", menuKey: "diagnosis", groupKey: "diagnosis" } },
    { path: "/diagnosis/assessment", name: "diagnosis-assessment", component: () => import("@/views/DiagnosisAssessmentView.vue"), meta: { title: "知识水平评估", menuKey: "diagnosis", groupKey: "diagnosis" } },
    { path: "/profile", name: "profile", component: () => import("@/views/ProfileView.vue"), meta: { title: "学习者画像", menuKey: "learner-profile", groupKey: "diagnosis" } },
    { path: "/learning-path", name: "learning-path", component: () => import("@/views/LearningPathView.vue"), meta: { title: "学习路径", menuKey: "learning-path" } },
    { path: "/resources", name: "resources", component: () => import("@/views/LearningResourcesView.vue"), meta: { title: "学习资源", breadcrumb: "资源与测评 / 学习资源", menuKey: "learning-resources", groupKey: "resource" } },
    { path: "/resources/:resourceId", name: "resource-detail", component: () => import("@/views/ResourceLearningView.vue"), meta: { title: "资源详情", breadcrumb: "资源与测评 / 学习资源", menuKey: "learning-resources", groupKey: "resource" } },
    { path: "/learn/:resourceId", name: "resource-learn", component: () => import("@/views/ResourceLearningView.vue"), meta: { title: "资源学习", breadcrumb: "资源与测评 / 学习资源", menuKey: "learning-resources", groupKey: "resource" } },
    { path: "/assessment", name: "assessment", component: () => import("@/views/AssessmentView.vue"), meta: { title: "测评与反馈", menuKey: "assessment", groupKey: "resource" } },
    { path: "/history", name: "history", component: () => import("@/views/HistoryView.vue"), meta: { title: "学习记录", menuKey: "history" } },
    { path: "/settings", name: "settings", component: () => import("@/views/SettingsView.vue"), meta: { title: "设置", menuKey: "settings" } },
    { path: "/profile/settings", redirect: (to) => ({ path: "/settings", query: to.query, hash: to.hash }) },
  ],
});

router.afterEach((to) => {
  const title = String(to.meta.title || "平台首页");
  document.title = `${title} | 织知成径`;
});

export default router;
