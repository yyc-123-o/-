<script setup lang="ts">
import { computed, onMounted } from "vue";
import {
  ArrowRight,
  BookOpenCheck,
  Check,
  CheckCircle2,
  CircleAlert,
  ClipboardCheck,
  Clock3,
  FileText,
  History,
  Lightbulb,
  Play,
  Route,
  Target,
} from "lucide-vue-next";
import { RouterLink, useRouter } from "vue-router";
import ProgressRing from "@/components/ProgressRing.vue";
import { useLearnerStore } from "@/stores/learner";
import { useLearningPathStore } from "@/stores/learningPath";
import { firstResourceForKnowledgePoint } from "@/utils/resourceCatalog";

const learner = useLearnerStore();
const path = useLearningPathStore();
const router = useRouter();

const profile = computed(() => learner.profile);
const nodes = computed(() => path.nodes);
const currentNode = computed(() => path.currentNode);
const completedNodes = computed(() =>
  nodes.value.filter((node) => ["completed", "done"].includes(node.status)),
);
const completedCount = computed(() => completedNodes.value.length);
const totalNodes = computed(() => nodes.value.length);
const progressValue = computed(() =>
  totalNodes.value ? completedCount.value / totalNodes.value : 0,
);
const progressPercent = computed(() => Math.round(progressValue.value * 100));
const overallMastery = computed(() => {
  const mastery = profile.value?.knowledge_mastery?.overall_mastery;
  return typeof mastery === "number" ? mastery : 0;
});
const courseName = computed(() =>
  profile.value?.learning_scope?.chapter_name || "尚未选择学习课程",
);
const courseTarget = computed(() =>
  profile.value?.learning_scope?.target_depth
    ? `目标深度：${profile.value.learning_scope.target_depth}`
    : "完成学情诊断后，系统会根据你的目标安排学习内容",
);
const currentNodeName = computed(() =>
  currentNode.value?.title || currentNode.value?.name || "下一学习节点",
);
const weakPoint = computed(() =>
  learner.weakPoints[0]?.name
  || profile.value?.knowledge_gaps?.[0]?.kp_name
  || "暂未识别薄弱知识点",
);
const currentMinutes = computed(() => currentNode.value?.estimated_minutes || null);
const currentLearningResource = computed(() =>
  currentNode.value?.concept_id ? firstResourceForKnowledgePoint(currentNode.value.concept_id) : null,
);
const currentStage = computed(() => {
  if (!profile.value) return "学情诊断";
  if (!path.run) return "课程规划";
  if (currentNode.value) return "课程学习";
  return "学习复盘";
});
const nextAction = computed(() => {
  if (learner.error) {
    return { label: "重新同步", to: "", kind: "retry" as const };
  }
  if (!profile.value) {
    return { label: "开始诊断", to: "/diagnosis", kind: "link" as const };
  }
  if (!path.run) {
    return { label: "生成路径", to: "/learning-path", kind: "link" as const };
  }
  return { label: "继续学习", to: currentLearningResource.value ? `/learn/${currentLearningResource.value.id}` : "/resources", kind: "link" as const };
});

const stageDefinitions = computed(() => {
  const hasProfile = Boolean(profile.value);
  const hasTestEvidence = Boolean(profile.value?.knowledge_mastery?.tested_kps);
  const hasPath = Boolean(path.run);
  return [
    { key: "materials", label: "课程资料", icon: FileText, state: hasProfile ? "done" : "current" },
    { key: "graph", label: "知识图谱", icon: Route, state: hasPath ? "done" : hasProfile ? "current" : "locked" },
    { key: "diagnosis", label: "学情诊断", icon: Target, state: hasTestEvidence ? "done" : "current" },
    { key: "planning", label: "课程规划", icon: BookOpenCheck, state: hasPath ? "current" : "locked" },
  ];
});

const nextLearning = computed(() => {
  if (!profile.value) {
    return {
      eyebrow: "第一步",
      title: "先完成一次学情诊断",
      description: "让系统了解你的基础、目标和薄弱知识点，再生成真正适合你的学习路径。",
      meta: "预计 10–15 分钟",
      to: "/diagnosis",
      action: "开始诊断",
    };
  }
  if (!path.run) {
    return {
      eyebrow: "准备开始",
      title: "生成你的个性化学习路径",
      description: "课程知识和学情信息已经准备好，下一步将按先修关系安排学习内容。",
      meta: "基于当前学习画像",
      to: "/learning-path",
      action: "生成路径",
    };
  }
  return {
    eyebrow: "当前推荐",
    title: currentNodeName.value,
    description: currentNode.value?.summary || "完成当前节点后，测评反馈会帮助系统继续调整下一步安排。",
    meta: currentMinutes.value ? `预计 ${currentMinutes.value} 分钟` : "进入资源中心开始学习",
    to: currentLearningResource.value ? `/learn/${currentLearningResource.value.id}` : "/resources",
    action: "继续学习",
  };
});

const adviceText = computed(() => {
  if (!profile.value) return "完成学情诊断后，AI 会根据你的掌握情况给出第一条学习建议。";
  if (!path.run) return "先生成学习路径，系统会结合知识图谱和你的学习目标安排先后顺序。";
  return `建议优先补强“${weakPoint.value}”，再进入下一项核心任务。学习反馈会持续影响后续规划。`;
});

const resources = computed(() => path.run?.resources as Record<string, any> | null);
const resourceDraft = computed(() => {
  const result = resources.value;
  return result?.formal_package?.draft
    || result?.preview_package?.draft
    || result?.draft
    || null;
});
const recentResources = computed(() => {
  const draft = resourceDraft.value;
  if (!draft) return [];
  const items: Array<{ title: string; meta: string; icon: typeof FileText }> = [];
  if (draft.lecture) {
    items.push({
      title: draft.lecture.title || `${currentNodeName.value}讲解`,
      meta: currentMinutes.value ? `${currentMinutes.value} 分钟 · 讲解` : "讲解资源",
      icon: BookOpenCheck,
    });
  }
  if (draft.practical_guide) {
    items.push({
      title: `${currentNodeName.value}实践练习`,
      meta: "实践练习",
      icon: Play,
    });
  }
  if (draft.student_quiz) {
    items.push({
      title: `${currentNodeName.value}单元测评`,
      meta: `${draft.student_quiz.items?.length || 0} 题 · 测评`,
      icon: ClipboardCheck,
    });
  }
  return items.slice(0, 3);
});

const feedbackReport = computed(() => learner.outcomeReport);
const feedbackTitle = computed(() => {
  if (feedbackReport.value?.overall_verdict) return feedbackReport.value.overall_verdict;
  return "还没有最近一次测评反馈";
});
const feedbackText = computed(() =>
  feedbackReport.value?.recommendation
  || profile.value?.diagnosis_summary?.short
  || "完成一次学习或测评后，这里会显示掌握度变化和下一步建议。",
);
const feedbackDelta = computed(() => {
  const accuracy = feedbackReport.value?.accuracy;
  if (typeof accuracy?.before !== "number" || typeof accuracy.after !== "number") return "";
  return `${Math.round(accuracy.before * 100)}% → ${Math.round(accuracy.after * 100)}%`;
});
const testedKnowledge = computed(() => profile.value?.knowledge_mastery?.tested_kps || 0);
const totalKnowledge = computed(() => profile.value?.knowledge_mastery?.total_kps || 0);
const weeklyHours = computed(() => profile.value?.learner?.self_assessment?.weekly_hours);
const interactionCount = computed(() => profile.value?.meta?.total_interaction_count);
const todayLabel = computed(() =>
  new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(new Date()),
);

function retrySync() {
  void learner.loadLearners();
}

function openStage(stage: { state: string; key: string }) {
  if (stage.state === "locked") {
    void router.push("/diagnosis");
    return;
  }
  const routes: Record<string, string> = {
    materials: "/courses",
    graph: "/learning-path#knowledge-graph",
    diagnosis: "/diagnosis",
    planning: "/learning-path",
  };
  void router.push(routes[stage.key]);
}

onMounted(() => {
  if (!learner.profile && !learner.loading) void learner.loadLearners();
});
</script>

<template>
  <div class="my-learning-reference">
    <header class="reference-page-intro">
      <div>
        <p class="reference-kicker">MY LEARNING</p>
        <h2>今天，从下一步开始</h2>
        <p class="reference-intro-copy">把学习目标、知识路径和每一次反馈，整理成你真正能走下去的课程计划。</p>
      </div>
      <div class="reference-date">
        <span class="reference-date-dot" />
        <time>{{ todayLabel }}</time>
      </div>
    </header>

    <p v-if="learner.error" class="reference-sync-notice">
      学习数据暂时未同步，部分信息可能延迟。
      <button type="button" @click="retrySync">重新同步</button>
    </p>
    <div v-else-if="learner.loading || path.loading" class="reference-loading" aria-live="polite">
      <span class="reference-loading-bar" />
      正在同步学习数据
    </div>

    <div class="reference-grid reference-grid--top">
      <section class="reference-card today-learning-card">
        <div class="reference-card-heading">
          <div>
            <p class="reference-eyebrow">TODAY'S LEARNING</p>
            <h3>今日学习</h3>
          </div>
          <RouterLink to="/history" class="reference-text-link">查看学习记录</RouterLink>
        </div>

        <div class="today-learning-body">
          <div class="today-learning-copy">
            <span class="reference-status-label">
              <CheckCircle2 v-if="path.run" :size="15" />
              <CircleAlert v-else :size="15" />
              {{ path.run ? "学习路径已就绪" : profile ? "等待生成学习路径" : "还没有学习画像" }}
            </span>
            <h4>{{ courseName }}</h4>
            <p class="today-learning-description">{{ courseTarget }}</p>
            <div class="today-learning-meta">
              <span><Clock3 :size="15" />{{ currentMinutes ? `预计 ${currentMinutes} 分钟` : "等待学习记录" }}</span>
              <span><History :size="15" />{{ interactionCount ? `${interactionCount} 次学习记录` : "暂无学习记录" }}</span>
            </div>
            <div class="reference-actions">
              <button v-if="nextAction.kind === 'retry'" type="button" class="reference-button reference-button--primary" @click="retrySync">
                {{ nextAction.label }} <ArrowRight :size="16" />
              </button>
              <RouterLink v-else :to="nextAction.to" class="reference-button reference-button--primary">
                {{ nextAction.label }} <ArrowRight :size="16" />
              </RouterLink>
              <RouterLink to="/learning-path" class="reference-text-link">查看完整路径</RouterLink>
            </div>
          </div>

          <div class="today-route-preview" aria-label="四阶段学习流程">
            <svg viewBox="0 0 420 190" role="img" aria-hidden="true">
              <path class="route-line route-line--base" d="M24 142 C90 142 96 52 166 70 S255 160 292 102 S348 32 396 47" />
              <path class="route-line route-line--progress" d="M24 142 C90 142 96 52 166 70" :style="{ strokeDasharray: `${Math.max(progressPercent, 18)}% 100%` }" />
              <circle class="route-node route-node--done" cx="24" cy="142" r="8" />
              <circle class="route-node route-node--done" cx="166" cy="70" r="8" />
              <circle class="route-node route-node--current" cx="292" cy="102" r="10" />
              <circle class="route-node route-node--locked" cx="396" cy="47" r="8" />
              <path class="route-lock" d="M392 45v-3a4 4 0 0 1 8 0v3M391 45h10v8h-10z" />
            </svg>
            <div class="route-preview-label route-preview-label--one"><span>课程资料</span><b>已完成</b></div>
            <div class="route-preview-label route-preview-label--two"><span>知识图谱</span><b>已完成</b></div>
            <div class="route-preview-label route-preview-label--three"><span>学情诊断</span><b>当前阶段</b></div>
            <div class="route-preview-label route-preview-label--four"><span>课程规划</span><b>待解锁</b></div>
          </div>
        </div>
      </section>

      <section class="reference-card learning-overview-card">
        <div class="reference-card-heading">
          <div>
            <p class="reference-eyebrow">LEARNING OVERVIEW</p>
            <h3>学习概览</h3>
          </div>
          <RouterLink to="/profile" class="reference-icon-link" title="查看学习者画像" aria-label="查看学习者画像">
            <ArrowRight :size="17" />
          </RouterLink>
        </div>
        <div class="overview-ring-row">
          <ProgressRing :value="overallMastery" label="总体掌握度" :size="122" />
          <div class="overview-summary">
            <strong>{{ overallMastery ? `${Math.round(overallMastery * 100)}%` : "—" }}</strong>
            <span>{{ totalKnowledge ? `已了解 ${testedKnowledge} / ${totalKnowledge} 个知识点` : "等待诊断数据" }}</span>
            <RouterLink to="/profile" class="reference-text-link">查看学习者画像</RouterLink>
          </div>
        </div>
        <div class="overview-facts">
          <div><span>每周计划</span><b>{{ weeklyHours ? `${weeklyHours} 小时` : "—" }}</b></div>
          <div><span>薄弱知识点</span><b>{{ weakPoint }}</b></div>
        </div>
      </section>
    </div>

    <div class="reference-grid reference-grid--middle">
      <section class="reference-card next-learning-card">
        <div class="reference-card-heading">
          <div>
            <p class="reference-eyebrow">NEXT STEP</p>
            <h3>接下来怎么学</h3>
          </div>
          <Route :size="19" class="reference-heading-icon" />
        </div>
        <div class="next-learning-content">
          <span class="next-learning-index">{{ nextLearning.eyebrow }}</span>
          <h4>{{ nextLearning.title }}</h4>
          <p>{{ nextLearning.description }}</p>
          <div class="next-learning-footer">
            <span><Clock3 :size="15" />{{ nextLearning.meta }}</span>
            <RouterLink :to="nextLearning.to" class="reference-text-link">{{ nextLearning.action }} <ArrowRight :size="14" /></RouterLink>
          </div>
        </div>
        <div class="stage-flow" aria-label="学习流程">
          <button
            v-for="stage in stageDefinitions"
            :key="stage.key"
            type="button"
            class="stage-flow-item"
            :class="`is-${stage.state}`"
            :aria-disabled="stage.state === 'locked'"
            @click="openStage(stage)"
          >
            <span class="stage-flow-node">
              <Check v-if="stage.state === 'done'" :size="14" />
              <component :is="stage.icon" v-else :size="14" />
            </span>
            <span>{{ stage.label }}</span>
          </button>
        </div>
      </section>

      <section class="reference-card learning-suggestion-card">
        <div class="reference-card-heading">
          <div>
            <p class="reference-eyebrow">AI LEARNING ADVICE</p>
            <h3>AI 学习建议</h3>
          </div>
          <span class="suggestion-mark"><Lightbulb :size="17" /></span>
        </div>
        <div class="suggestion-body">
          <p>{{ adviceText }}</p>
          <div class="suggestion-note">
            <span>基于当前掌握情况</span>
            <strong>{{ currentStage }}</strong>
          </div>
        </div>
        <RouterLink to="/profile" class="reference-text-link">查看建议依据 <ArrowRight :size="14" /></RouterLink>
      </section>
    </div>

    <div class="reference-grid reference-grid--bottom">
      <section class="reference-card latest-feedback-card">
        <div class="reference-card-heading">
          <div>
            <p class="reference-eyebrow">LATEST FEEDBACK</p>
            <h3>最近一次反馈</h3>
          </div>
          <ClipboardCheck :size="19" class="reference-heading-icon" />
        </div>
        <div class="feedback-status">
          <span :class="{ 'is-empty': !feedbackReport }">{{ feedbackReport ? "测评已完成" : "等待测评" }}</span>
          <b v-if="feedbackDelta">{{ feedbackDelta }}</b>
        </div>
        <h4>{{ feedbackTitle }}</h4>
        <p>{{ feedbackText }}</p>
        <RouterLink to="/assessment" class="reference-text-link">{{ feedbackReport ? "查看完整反馈" : "去完成测评" }} <ArrowRight :size="14" /></RouterLink>
      </section>

      <section class="reference-card recent-resources-card">
        <div class="reference-card-heading">
          <div>
            <p class="reference-eyebrow">RECENT RESOURCES</p>
            <h3>最近学习资源</h3>
          </div>
          <RouterLink to="/resources" class="reference-text-link">查看全部</RouterLink>
        </div>
        <div v-if="recentResources.length" class="recent-resource-list">
          <RouterLink v-for="resource in recentResources" :key="resource.title" to="/resources" class="recent-resource-row">
            <span class="recent-resource-icon"><component :is="resource.icon" :size="17" /></span>
            <span class="recent-resource-copy">
              <strong>{{ resource.title }}</strong>
              <small>{{ resource.meta }}</small>
            </span>
            <ArrowRight :size="16" class="recent-resource-arrow" />
          </RouterLink>
        </div>
        <div v-else class="reference-empty-state">
          <BookOpenCheck :size="20" />
          <p>生成学习路径后，这里会显示为你准备的讲解、练习和测评资源。</p>
          <RouterLink to="/learning-path" class="reference-text-link">查看学习路径 <ArrowRight :size="14" /></RouterLink>
        </div>
      </section>
    </div>
  </div>
</template>
