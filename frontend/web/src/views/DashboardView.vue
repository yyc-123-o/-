<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import {
  AlertTriangle,
  ArrowRight,
  BookOpenCheck,
  BrainCircuit,
  CheckCircle2,
  ChevronRight,
  Circle,
  ClipboardCheck,
  Database,
  FileSearch,
  GitBranch,
  Loader2,
  RefreshCw,
  Sparkles,
  Workflow,
} from "lucide-vue-next";
import GuideFigure from "@/components/illustrations/GuideFigure.vue";
import ProgressRing from "@/components/ProgressRing.vue";
import StateBlocks from "@/components/StateBlocks.vue";
import { api } from "@/api/client";
import { useDiagnosisStore } from "@/stores/diagnosis";
import { useLearnerStore } from "@/stores/learner";
import { useLearningPathStore } from "@/stores/learningPath";

type StageState = "done" | "current" | "waiting" | "review" | "risk";

interface ProcessStage {
  key: string;
  label: string;
  detail: string;
  route: string;
  state: StageState;
  metric: string;
}

type PendingItem = {
  label: string;
  tone: "warm" | "neutral";
  kind: "tag" | "notice";
};

const router = useRouter();
const learner = useLearnerStore();
const diagnosis = useDiagnosisStore();
const path = useLearningPathStore();
const healthLoading = ref(false);
const healthError = ref("");
const healthStatus = ref<"ok" | "unknown">("unknown");

const hasRealProfile = computed(() => learner.source === "real" && !!learner.profile);
const hasRun = computed(() => !!path.run);
const hasEvidenceGap = computed(() => !!path.run?.evidence_gap);
const currentNodeName = computed(() => path.currentNode?.title || path.currentNode?.name || path.currentNode?.concept_id || "当前推荐节点");
const weakPoints = computed(() => learner.weakPoints.slice(0, 3));
const profileMastery = computed(() => learner.mastery || 0);

const stageIndex = computed(() => {
  if (!learner.profile) return 3;
  if (!path.run) return 4;
  if (path.run.failure) return 5;
  if (hasEvidenceGap.value) return 5;
  if (path.run.resources) return 7;
  if (path.run.retrieval || path.run.handoff) return 6;
  if (path.run.planning) return 5;
  return 4;
});

const processStages = computed<ProcessStage[]>(() => {
  const base: Omit<ProcessStage, "state">[] = [
    { key: "materials", label: "资料接入", detail: "课程文档与资料准备", route: "/resources", metric: "待接入" },
    { key: "kb", label: "知识库", detail: "清洗、切分与索引", route: "/resources", metric: "候选证据" },
    { key: "graph", label: "知识图谱", detail: "概念节点与先修关系", route: "/learning-path", metric: `${path.nodes.length || 0} 节点` },
    { key: "diagnosis", label: "学情诊断", detail: "画像、掌握度与盲区", route: "/diagnosis", metric: learner.profile ? "已生成" : "未开始" },
    { key: "planning", label: "课程规划", detail: "CoursePlanner 生成路径", route: "/learning-path", metric: path.run?.planning ? "已规划" : "待规划" },
    { key: "retrieval", label: "证据检索", detail: "领域证据与 manifest", route: "/resources", metric: hasEvidenceGap.value ? "待审核" : path.run?.retrieval ? "已检索" : "等待" },
    { key: "resources", label: "资源生成", detail: "讲解、练习与测验", route: "/resources", metric: path.run?.resources ? "已生成" : "候选预览" },
    { key: "feedback", label: "反馈更新", detail: "测评、BKT 与再规划", route: "/assessment", metric: "待测评" },
  ];

  return base.map((item, index) => {
    let state: StageState = index < stageIndex.value ? "done" : index === stageIndex.value ? "current" : "waiting";
    if (path.run?.failure && index === stageIndex.value) state = "risk";
    if (hasEvidenceGap.value && item.key === "retrieval") state = "review";
    if (!hasRun.value && index < 3) state = "review";
    return { ...item, state };
  });
});

function processFill(stage: ProcessStage, index: number) {
  if (stage.state === "done") return 100;
  if (stage.state === "current") return 78;
  if (stage.state === "review") return 56;
  if (stage.state === "risk") return 30;
  return Math.max(24, 24 + index * 6);
}

const mainProgress = computed(() => {
  const done = processStages.value.filter((item) => item.state === "done").length;
  return done / processStages.value.length;
});

const currentTask = computed(() => {
  if (learner.error) {
    return {
      title: "接口连接异常，需要先恢复数据同步",
      module: "系统状态",
      reason: "暂时无法连接平台服务，学习者数据会在恢复后自动同步。",
      impact: "画像、诊断和课程规划都依赖接口数据。",
      progress: 0.1,
      action: "重新同步",
      route: "",
      handler: () => learner.loadLearners(),
      tone: "risk",
      source: "接口连接异常",
    };
  }
  if (!learner.profile) {
    return {
      title: "建议先完成学情诊断，建立学习者画像",
      module: "学情诊断 Agent",
      reason: "课程规划需要掌握度、学习目标和能力维度作为输入。",
      impact: "完成后 CoursePlanner 才能生成个性化课程路径。",
      progress: 0.18,
      action: "开始诊断",
      route: "/diagnosis",
      tone: "current",
      source: "真实状态",
    };
  }
  if (!path.run) {
    return {
      title: "学习者画像已就绪，可以生成课程规划",
      module: "CoursePlanner",
      reason: `${learner.learnerName} 的画像已经接入，当前缺少平台运行记录。`,
      impact: "生成后会串联知识图谱、证据检索和资源生成。",
      progress: 0.42,
      action: "生成课程规划",
      route: "/learning-path",
      tone: "current",
      source: hasRealProfile.value ? "真实画像数据" : "本地画像状态",
    };
  }
  if (path.run.failure) {
    return {
      title: "平台运行失败，需要查看失败阶段",
      module: path.run.steps?.find((step) => step.failure)?.stage || "Agent 工作流",
      reason: "平台运行暂时异常，建议重新尝试或查看失败阶段。",
      impact: "修复后可以重新运行规划与资源生成。",
      progress: 0.55,
      action: "查看工作流",
      route: "/learning-path",
      tone: "risk",
      source: "真实运行状态",
    };
  }
  if (hasEvidenceGap.value) {
    return {
      title: "证据检索存在缺口，需要审核候选证据",
      module: "Domain Retrieval Agent",
      reason: "检索结果不足会影响课程资源生成的可靠性。",
      impact: "处理后 Resource Generation Agent 才能生成正式资源。",
      progress: 0.62,
      action: "审核候选资源",
      route: "/resources",
      tone: "review",
      source: "真实运行状态",
    };
  }
  if (!path.run.resources) {
    return {
      title: `继续处理：${currentNodeName.value}`,
      module: "Resource Generation Agent",
      reason: "当前节点已进入规划链路，下一步需要生成或查看候选资源。",
      impact: "资源完成后可以进入测评反馈，更新掌握度。",
      progress: 0.72,
      action: "进入资源中心",
      route: "/resources",
      tone: "current",
      source: "真实运行状态",
    };
  }
  return {
    title: `对 ${currentNodeName.value} 提交测评反馈`,
    module: "测评与掌握度更新",
    reason: "学习资源已经生成，测评结果会写回当前路径状态。",
    impact: "系统会根据结果更新掌握度，并决定是否重新规划。",
    progress: 0.86,
    action: "完成测评",
    route: "/assessment",
    tone: "done",
    source: "真实运行状态",
  };
});

const agentStates = computed(() => [
  {
    name: "学情诊断 Agent",
    state: learner.profile ? "已完成" : diagnosis.submitting ? "运行中" : "等待输入",
    tone: learner.profile ? "done" : diagnosis.submitting ? "running" : "waiting",
  },
  {
    name: "CoursePlanner",
    state: path.run?.planning ? "已完成" : path.loading ? "运行中" : learner.profile ? "等待启动" : "缺少画像",
    tone: path.run?.planning ? "done" : path.loading ? "running" : "waiting",
  },
  {
    name: "Domain Retrieval Agent",
    state: hasEvidenceGap.value ? "需要审核" : path.run?.retrieval ? "已完成" : path.run?.planning ? "等待检索" : "空闲",
    tone: hasEvidenceGap.value ? "review" : path.run?.retrieval ? "done" : "waiting",
  },
  {
    name: "Resource Generation Agent",
    state: path.run?.resources ? "已完成" : path.run?.status === "generating" ? "运行中" : "等待证据",
    tone: path.run?.resources ? "done" : path.run?.status === "generating" ? "running" : "waiting",
  },
]);

const recentActivities = computed(() => {
  const records = [];
  if (learner.profile) records.push({ title: "学习者画像已载入", detail: learner.profile.diagnosis_summary?.short || "掌握度和知识盲区可用于课程规划", tone: "purple" });
  if (path.run?.planning) records.push({ title: "课程规划已生成", detail: `${path.nodes.length || 0} 个课程节点进入路径`, tone: "blue" });
  if (path.run?.retrieval) records.push({ title: "领域证据检索完成", detail: "检索结果已进入资源生成上下文", tone: "green" });
  if (path.run?.resources) records.push({ title: "课程资源已生成", detail: "讲解、示例、练习和测验可继续审核", tone: "green" });
  if (!records.length) records.push({ title: "等待第一次真实运行", detail: "完成诊断后，这里会显示最近的 Agent 结果", tone: "amber" });
  return records.slice(0, 4);
});

const pendingItems = computed<PendingItem[]>(() => {
  const items: PendingItem[] = [];
  if (!learner.profile) items.push({ label: "缺少学习者画像，CoursePlanner 暂不能运行", tone: "neutral", kind: "notice" });
  if (learner.profile && !path.run) items.push({ label: "画像已就绪，等待生成课程规划", tone: "neutral", kind: "notice" });
  if (hasEvidenceGap.value) items.push({ label: "候选证据存在缺口，需要人工确认", tone: "warm", kind: "notice" });
  if (path.run?.failure) items.push({ label: "运行失败：平台运行暂时异常", tone: "warm", kind: "notice" });
  weakPoints.value.forEach((point) => items.push({ label: point.name, tone: "warm", kind: "tag" }));
  return items.slice(0, 5);
});

const dataSourceLabel = computed(() => {
  if (path.run || hasRealProfile.value) return "真实接口数据";
  if (learner.error || healthError.value) return "接口异常";
  return "演示状态，等待真实运行数据";
});

async function checkHealth() {
  healthLoading.value = true;
  healthError.value = "";
  try {
    const result = await api.get<{ status: string }>("/api/v1/health");
    healthStatus.value = result.data.status === "ok" ? "ok" : "unknown";
  } catch (error) {
    healthStatus.value = "unknown";
    healthError.value = "暂时无法连接平台服务，请稍后重试。";
  } finally {
    healthLoading.value = false;
  }
}

function runPrimaryAction() {
  if (currentTask.value.handler) {
    void currentTask.value.handler();
    return;
  }
  if (currentTask.value.route) void router.push(currentTask.value.route);
}

onMounted(() => {
  void diagnosis.loadLearners();
  void checkHealth();
});
</script>

<template>
  <div class="platform-home">
    <section class="home-hero">
      <div class="home-hero__copy">
        <span class="home-kicker"><Workflow :size="15" /> AI 课程知识库治理与多智能体学习规划平台</span>
        <h2>下午好，<br />欢迎回到织知成径</h2>
        <p>课程资料、知识库、图谱、诊断与规划在同一条链路上推进。</p>
        <div class="home-status-row">
          <span class="status-pill" :class="{ 'status-pill-success': healthStatus === 'ok', 'status-pill-warning': healthStatus !== 'ok' }">
            {{ healthLoading ? "连接中" : healthStatus === "ok" ? "平台服务已连接" : "等待服务恢复" }}
          </span>
          <span class="source-note">{{ dataSourceLabel }}</span>
        </div>
      </div>

      <div class="home-hero__progress">
        <ProgressRing :value="mainProgress" label="平台进程" :size="118" />
        <div>
          <strong>{{ Math.round(mainProgress * 100) }}%</strong>
          <span>主线已完成</span>
          <small>当前阶段：{{ processStages[stageIndex]?.label || "等待输入" }}</small>
        </div>
      </div>
    </section>

    <section class="platform-layout">
      <div class="platform-main">
        <section class="process-panel">
          <div class="panel-heading">
            <div>
              <span class="eyebrow">MAIN PROCESS</span>
              <h2>平台智能进程</h2>
              <p>从课程资料进入知识库，再到规划、资源生成和反馈更新。</p>
            </div>
            <RouterLink to="/learning-path" class="text-link">查看课程规划 <ChevronRight :size="15" /></RouterLink>
          </div>

          <div class="process-map" aria-label="平台智能进程路径">
            <RouterLink
              v-for="(stage, index) in processStages"
              :key="stage.key"
              :to="stage.route"
              class="process-node"
              :class="`is-${stage.state}`"
              :style="{ '--stage-level': `${processFill(stage, index)}%` }"
            >
              <span class="process-node__index">
                <CheckCircle2 v-if="stage.state === 'done'" :size="18" />
                <AlertTriangle v-else-if="stage.state === 'risk' || stage.state === 'review'" :size="17" />
                <Loader2 v-else-if="stage.state === 'current'" :size="17" />
                <Circle v-else :size="16" />
              </span>
              <span class="process-node__copy">
                <b>{{ stage.label }}</b>
                <small>{{ stage.detail }}</small>
                <span class="process-node__metric">{{ stage.metric }}</span>
              </span>
              <span class="process-node__meter" aria-hidden="true"><i /></span>
              <i v-if="index < processStages.length - 1" class="process-connector" />
            </RouterLink>
          </div>
        </section>

        <section class="current-task-card" :class="`is-${currentTask.tone}`">
          <div class="task-main">
            <span class="home-kicker"><Sparkles :size="15" /> 当前最重要任务</span>
            <h2>{{ currentTask.title }}</h2>
            <p>{{ currentTask.reason }}</p>
            <div class="task-impact">
              <span>来源模块：{{ currentTask.module }}</span>
              <span>预计影响：{{ currentTask.impact }}</span>
              <span>数据来源：{{ currentTask.source }}</span>
            </div>
            <div class="progress-track task-progress">
              <span :style="{ width: `${Math.round(currentTask.progress * 100)}%` }" />
            </div>
            <button class="button button-primary button-large" @click="runPrimaryAction">
              {{ currentTask.action }} <ArrowRight :size="17" />
            </button>
          </div>

          <div class="ai-guide">
            <GuideFigure :size="118" />
            <div class="ai-guide__bubble">
              <strong>多智能体协作助手</strong>
              <p v-if="hasEvidenceGap">我发现证据检索存在缺口，建议先确认候选证据，再生成正式资源。</p>
              <p v-else-if="path.currentNode">我正在围绕“{{ currentNodeName }}”整理资源、证据和下一步测评。</p>
              <p v-else-if="learner.profile">画像已经准备好，下一步可以让 CoursePlanner 生成课程路径。</p>
              <p v-else>先完成学情诊断，我就能把你的画像交给课程规划链路。</p>
            </div>
          </div>
        </section>

        <div class="support-grid">
          <section class="panel profile-mini">
            <div class="panel-heading">
              <div>
                <span class="eyebrow">LEARNER PROFILE</span>
                <h2>学习者画像摘要</h2>
              </div>
              <RouterLink to="/profile" class="text-link">完整画像 <ChevronRight :size="15" /></RouterLink>
            </div>
            <template v-if="learner.profile">
              <div class="profile-mini__top">
                <ProgressRing :value="profileMastery" label="掌握度" :size="86" />
                <div>
                  <strong>{{ learner.profile.learner.name }}</strong>
                  <span>{{ learner.profile.learner.education?.major || "专业未填写" }} · {{ learner.profile.ability_level?.overall || "能力待评估" }}</span>
                  <p>{{ learner.profile.diagnosis_summary?.short || "画像已载入，可用于课程路径规划。" }}</p>
                </div>
              </div>
              <div class="tag-list">
                <span v-for="point in weakPoints" :key="point.name" class="tag">{{ point.name }}</span>
                <span v-if="!weakPoints.length" class="tag">暂无高优先级盲区</span>
              </div>
            </template>
            <StateBlocks v-else type="empty" title="还没有画像" message="完成学情诊断后，这里会显示掌握度、盲区和学习偏好。" />
          </section>

          <section id="agents" class="panel agent-panel">
            <div class="panel-heading">
              <div>
                <span class="eyebrow">AGENTS</span>
                <h2>Agent 工作状态</h2>
              </div>
              <Workflow :size="20" class="icon-purple" />
            </div>
            <div class="agent-list">
              <div v-for="agent in agentStates" :key="agent.name" class="agent-row" :class="`is-${agent.tone}`">
                <span class="agent-dot" />
                <strong>{{ agent.name }}</strong>
                <em>{{ agent.state }}</em>
              </div>
            </div>
          </section>
        </div>
      </div>

      <aside class="platform-aside">
        <section class="panel pending-card">
          <div class="panel-heading">
            <div>
              <span class="eyebrow">ACTIONABLE</span>
              <h3>待处理事项</h3>
            </div>
            <ClipboardCheck :size="18" class="icon-blue" />
          </div>
          <div v-if="pendingItems.length" class="pending-list">
            <RouterLink
              v-for="item in pendingItems"
              :key="item.label"
              :to="learner.profile ? '/learning-path' : '/diagnosis'"
              class="pending-item"
              :class="item.kind"
            >
              <AlertTriangle :size="15" />
              <span>{{ item.label }}</span>
            </RouterLink>
          </div>
          <StateBlocks v-else title="暂无待处理事项" message="当前链路没有需要人工处理的阻塞。" />
        </section>

        <section class="panel activity-panel">
          <div class="panel-heading">
            <div>
              <span class="eyebrow">RECENT</span>
              <h3>最近活动</h3>
            </div>
            <RouterLink to="/history" class="text-link">全部 <ChevronRight :size="15" /></RouterLink>
          </div>
          <div class="activity-list">
            <div v-for="record in recentActivities" :key="record.title" class="activity-row">
              <span class="activity-dot" :class="record.tone" />
              <div>
                <strong>{{ record.title }}</strong>
                <small>{{ record.detail }}</small>
              </div>
            </div>
          </div>
        </section>

        <section class="panel run-card">
          <div class="panel-heading">
            <div>
              <span class="eyebrow">RUN STATE</span>
              <h3>运行记录</h3>
            </div>
            <FileSearch :size="18" class="icon-muted" />
          </div>
          <div class="run-facts">
            <span><b>Run ID</b><em>{{ path.run?.run_id?.slice(0, 18) || "暂无" }}</em></span>
            <span><b>状态</b><em>{{ path.run?.status || "等待运行" }}</em></span>
            <span><b>步骤</b><em>{{ path.run?.steps?.length || 0 }} 条</em></span>
            <span><b>执行模式</b><em>{{ path.run ? "candidate preview / strict" : "未启动" }}</em></span>
          </div>
          <button class="button button-secondary button-full" :disabled="path.loading" @click="path.generate">
            <RefreshCw :size="16" /> {{ path.loading ? "运行中..." : "重新运行规划链路" }}
          </button>
        </section>
      </aside>
    </section>

    <section v-if="healthError" class="inline-error">
      当前暂时无法连接平台服务，数据会在恢复后自动加载。
      <button class="text-link" @click="checkHealth">重新连接</button>
    </section>
  </div>
</template>

