<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import {
  ArrowRight,
  Database,
  FileText,
  GitBranch,
  GraduationCap,
  Library,
  ChevronRight,
  Route,
  School,
  ShieldCheck,
  Sparkles,
  Workflow,
  BrainCircuit,
  FileSearch,
  Layers3,
  MoveRight,
  RefreshCw,
} from "lucide-vue-next";
import HomeNavbar from "@/components/layout/HomeNavbar.vue";
import BrandWordmark from "@/components/layout/BrandWordmark.vue";
import GuideFigure from "@/components/illustrations/GuideFigure.vue";
import mountainPath from "@/assets/landing/hero-mountain-path.webp";

type RoleKey = "builder" | "teacher" | "learner" | "institution";
type StepKey = "materials" | "organize" | "understand" | "plan" | "generate" | "feedback";

interface RoleCard {
  key: RoleKey;
  title: string;
  subtitle: string;
  description: string;
  badge: string;
  previewTitle: string;
  previewItems: string[];
  icon: typeof Library;
}

interface WorkflowStep {
  key: StepKey;
  title: string;
  summary: string;
  detail: string;
  badge: string;
  previewTitle: string;
  previewLines: string[];
  icon: typeof FileText;
}

interface HomeScene {
  id: string;
  image: string;
  alt: string;
  top: string;
  height: string;
  position: string;
  scale: number;
  opacity: number;
  loading: "eager" | "lazy";
  fetchPriority?: "high" | "low" | "auto";
}

const heroTags = ["知识库治理", "智能课程规划", "多智能体协作"];

const HOME_SCENES: HomeScene[] = [
  {
    id: "hero",
    image: mountainPath,
    alt: "",
    top: "0vh",
    height: "138vh",
    position: "68% center",
    scale: 1.02,
    opacity: 1,
    loading: "eager",
    fetchPriority: "high",
  },
  {
    id: "knowledge",
    image: mountainPath,
    alt: "",
    top: "96vh",
    height: "142vh",
    position: "58% center",
    scale: 1.06,
    opacity: 0.96,
    loading: "lazy",
  },
  {
    id: "learner",
    image: mountainPath,
    alt: "",
    top: "198vh",
    height: "146vh",
    position: "62% center",
    scale: 1.07,
    opacity: 0.94,
    loading: "lazy",
  },
  {
    id: "route",
    image: mountainPath,
    alt: "",
    top: "304vh",
    height: "148vh",
    position: "66% center",
    scale: 1.05,
    opacity: 0.95,
    loading: "lazy",
  },
  {
    id: "feedback",
    image: mountainPath,
    alt: "",
    top: "414vh",
    height: "146vh",
    position: "58% center",
    scale: 1.06,
    opacity: 0.94,
    loading: "lazy",
  },
  {
    id: "ending",
    image: mountainPath,
    alt: "",
    top: "520vh",
    height: "160vh",
    position: "64% bottom",
    scale: 1.03,
    opacity: 0.98,
    loading: "lazy",
  },
];

const roleCards: RoleCard[] = [
  {
    key: "builder",
    title: "课程建设者",
    subtitle: "先把课程资料整理成可信知识资产",
    description: "管理课程资料、维护知识图谱、追踪来源与审核状态，让后续规划建立在可追溯证据上。",
    badge: "知识库与证据",
    previewTitle: "课程建设者看到的界面",
    previewItems: ["课程文档切分与索引", "知识单元与先修关系", "正式证据 / 候选证据", "审核状态与引用来源"],
    icon: Library,
  },
  {
    key: "teacher",
    title: "教师与教学管理者",
    subtitle: "快速判断哪里该讲、哪里该补",
    description: "通过学情诊断、知识盲区和课程建议，把教学关注点从“内容堆叠”转向“重点补救”。",
    badge: "学情与课堂",
    previewTitle: "教师侧重点",
    previewItems: ["学习者画像摘要", "薄弱知识点提醒", "路径推荐与讲解建议", "练习与测评生成"],
    icon: GraduationCap,
  },
  {
    key: "learner",
    title: "学习者",
    subtitle: "得到真正适合自己的下一步",
    description: "学习路径会根据掌握情况动态变化，已会的可以跳过，不会的自动进入补救队列。",
    badge: "个性化路径",
    previewTitle: "学习者看到的路径",
    previewItems: ["基础知识补救", "核心概念推进", "练习与反馈闭环", "掌握度持续更新"],
    icon: Route,
  },
  {
    key: "institution",
    title: "学校与教育机构",
    subtitle: "统一管理课程资产和教学质量",
    description: "从课程资产治理到运行质量追踪，平台支持规模化的智能教学服务与资源协同。",
    badge: "规模化治理",
    previewTitle: "机构视角",
    previewItems: ["课程资产统一管理", "知识图谱协同维护", "Agent 运行状态", "教学效果持续追踪"],
    icon: School,
  },
];

const workflowSteps: WorkflowStep[] = [
  {
    key: "materials",
    title: "资料进入",
    summary: "接入 PDF、HTML 和课程文档",
    detail: "把分散的课程材料统一接入平台，形成可处理、可追溯、可再利用的知识来源。",
    badge: "输入层",
    previewTitle: "资料接入预览",
    previewLines: ["PDF 教材", "HTML 教案", "课堂讲义", "资源链接"],
    icon: FileText,
  },
  {
    key: "organize",
    title: "知识被组织",
    summary: "清洗、切分、索引并构建知识图谱",
    detail: "系统保留来源、定位和审核状态，让知识单元不是孤立文本，而是可治理的结构化资产。",
    badge: "组织层",
    previewTitle: "知识库视图",
    previewLines: ["知识单元切分", "来源与引用", "正式证据", "候选证据"],
    icon: Database,
  },
  {
    key: "understand",
    title: "学情被理解",
    summary: "诊断与画像形成学习状态",
    detail: "通过测评、学习行为和掌握度数据，系统理解当前学到哪一步、卡在哪一步。",
    badge: "诊断层",
    previewTitle: "学习者画像",
    previewLines: ["掌握度趋势", "知识盲区", "学习目标", "置信度状态"],
    icon: BrainCircuit,
  },
  {
    key: "plan",
    title: "路径被规划",
    summary: "CoursePlanner 生成个性化课程路径",
    detail: "先修关系和学习状态共同决定学习顺序，已掌握内容可以跳过，缺口内容自动补救。",
    badge: "规划层",
    previewTitle: "课程路径",
    previewLines: ["基础知识", "核心概念", "实践应用", "综合能力"],
    icon: Route,
  },
  {
    key: "generate",
    title: "资源被生成",
    summary: "讲义、练习、测验与项目任务",
    detail: "课程节点、证据和画像共同决定资源深度，让生成内容有依据，也更贴近当前需求。",
    badge: "生成层",
    previewTitle: "资源输出",
    previewLines: ["讲解卡片", "练习任务", "测验题目", "项目单元"],
    icon: Layers3,
  },
  {
    key: "feedback",
    title: "反馈推动下一次规划",
    summary: "测评结果回流到掌握度更新",
    detail: "学习结果不会停在一次操作里，而是继续影响下一轮路径和资源建议。",
    badge: "闭环层",
    previewTitle: "反馈闭环",
    previewLines: ["测评提交", "掌握度更新", "路径重算", "下一步建议"],
    icon: RefreshCw,
  },
];

const activeRoleKey = ref<RoleKey>("builder");
const activeStepKey = ref<StepKey>("organize");
const homeRoot = ref<HTMLElement | null>(null);
const revealCleanup: Array<() => void> = [];
let scrollCleanup: (() => void) | null = null;
let knowledgePreloadLink: HTMLLinkElement | null = null;
let scrollFrame = 0;

const activeRole = computed(() => roleCards.find((item) => item.key === activeRoleKey.value) || roleCards[0]);
const activeStep = computed(() => workflowSteps.find((item) => item.key === activeStepKey.value) || workflowSteps[0]);

const agentFlow = [
  { title: "测评完成", detail: "记录掌握度变化", tone: "done" },
  { title: "识别盲区", detail: "定位需要补救的先修知识", tone: "review" },
  { title: "调整路径", detail: "CoursePlanner 重算下一步", tone: "current" },
  { title: "检索证据", detail: "Domain Retrieval Agent 查找依据", tone: "support" },
  { title: "生成资源", detail: "Resource Generation Agent 输出内容", tone: "support" },
  { title: "更新状态", detail: "反馈写回学习画像", tone: "done" },
];

const governanceColumns = [
  {
    title: "课程资料",
    items: ["PDF 教材", "HTML 讲义", "课堂笔记", "资源链接"],
  },
  {
    title: "知识图谱",
    items: ["知识单元", "先修关系", "知识缺口", "路径约束"],
  },
  {
    title: "证据状态",
    items: ["正式证据", "候选证据", "许可证", "审核结果"],
  },
];

const planningCards = [
  {
    learner: "学习者 A",
    title: "基础已掌握，直接进入核心概念",
    chips: ["基础知识", "核心概念", "实践任务"],
    state: ["已掌握", "进行中", "待学习"],
  },
  {
    learner: "学习者 B",
    title: "先补先修知识，再进入主路径",
    chips: ["补救队列", "引导练习", "核心概念", "测评反馈"],
    state: ["待补救", "进行中", "待学习", "反馈更新"],
  },
];

function setActiveRole(key: RoleKey) {
  activeRoleKey.value = key;
}

function setActiveStep(key: StepKey) {
  activeStepKey.value = key;
}

onMounted(() => {
  if (typeof document !== "undefined") {
    knowledgePreloadLink = document.createElement("link");
    knowledgePreloadLink.rel = "preload";
    knowledgePreloadLink.as = "image";
    knowledgePreloadLink.href = mountainPath;
    document.head.appendChild(knowledgePreloadLink);
  }

  if (typeof window !== "undefined") {
    const updateBackgroundShift = () => {
      scrollFrame = 0;
      const root = homeRoot.value;
      if (!root) return;
      const rect = root.getBoundingClientRect();
      const total = Math.max(1, rect.height - window.innerHeight);
      const progress = Math.min(1, Math.max(0, -rect.top / total));
      root.style.setProperty("--home-bg-shift", `${Math.round(progress * -54)}px`);
    };
    const requestBackgroundShift = () => {
      if (scrollFrame) return;
      scrollFrame = window.requestAnimationFrame(updateBackgroundShift);
    };
    updateBackgroundShift();
    window.addEventListener("scroll", requestBackgroundShift, { passive: true });
    window.addEventListener("resize", requestBackgroundShift);
    scrollCleanup = () => {
      window.removeEventListener("scroll", requestBackgroundShift);
      window.removeEventListener("resize", requestBackgroundShift);
      if (scrollFrame) window.cancelAnimationFrame(scrollFrame);
    };
  }

  if (typeof document === "undefined" || typeof IntersectionObserver === "undefined") return;
  const sections = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal]"));
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) entry.target.classList.add("is-visible");
      });
    },
    { threshold: 0.14, rootMargin: "0px 0px -10% 0px" },
  );
  sections.forEach((section) => {
    observer.observe(section);
    revealCleanup.push(() => observer.unobserve(section));
  });
  revealCleanup.push(() => observer.disconnect());
});

onBeforeUnmount(() => {
  revealCleanup.forEach((cleanup) => cleanup());
  scrollCleanup?.();
  knowledgePreloadLink?.remove();
});
</script>

<template>
  <div ref="homeRoot" class="product-home">
    <div class="home-background" aria-hidden="true">
      <div
        v-for="scene in HOME_SCENES"
        :key="scene.id"
        class="home-background__scene"
        :class="`home-background__scene--${scene.id}`"
        :style="{
          '--scene-top': scene.top,
          '--scene-height': scene.height,
          '--scene-position': scene.position,
          '--scene-scale': scene.scale,
          '--scene-opacity': scene.opacity,
        }"
      >
        <img
          :src="scene.image"
          :alt="scene.alt"
          :loading="scene.loading"
          :fetchpriority="scene.fetchPriority"
          decoding="async"
        />
        <span class="home-background__transition" />
      </div>
    </div>

    <HomeNavbar />

    <main>
      <section class="hero product-home__container">
        <div class="hero-copy" data-reveal>
          <span class="eyebrow"><Sparkles :size="16" /> AI 课程知识库治理与智能规划平台</span>
          <h1>从课程知识库，到每个人的智能学习路径</h1>
          <p>
            织知成径把课程资料、知识图谱、学习者画像和多智能体能力连接起来，
            让课程建设、学情理解和资源生成在同一条工作链路上持续推进。
          </p>
          <div class="hero-actions">
            <RouterLink to="/register" class="button button-primary">
              开始使用 <ArrowRight :size="17" />
            </RouterLink>
            <a href="#workflow" class="button button-secondary">了解平台如何工作</a>
          </div>
          <div class="hero-tags">
            <span v-for="tag in heroTags" :key="tag">{{ tag }}</span>
          </div>
          <div class="hero-notes">
            <span><ShieldCheck :size="15" /> 知识库可追溯</span>
            <span><Workflow :size="15" /> Agent 协同</span>
            <span><FileSearch :size="15" /> 证据优先</span>
          </div>
        </div>

        <div class="hero-visual" data-reveal>
          <div class="scene-card scene-card--wide">
            <div class="scene-card__top">
              <span>平台正在运行的界面预览</span>
              <strong>课程知识、路径与反馈同步工作</strong>
            </div>
            <div class="scene-grid">
              <div class="scene-column scene-column--left">
                <div class="mini-panel">
                  <span>课程知识库</span>
                  <strong>知识单元 / 来源 / 审核</strong>
                </div>
                <div class="mini-panel mini-panel--soft">
                  <span>学习者画像</span>
                  <strong>掌握度 72% · 重点补救 3 项</strong>
                </div>
              </div>

              <div class="scene-core">
                <div class="scene-core__glow" />
                <GuideFigure :size="190" />
                <div class="scene-core__caption">
                  <span>课程规划智能体</span>
                  <strong>正在连接知识、学习与证据</strong>
                </div>
              </div>

              <div class="scene-column scene-column--right">
                <div class="mini-panel mini-panel--accent">
                  <span>当前 Agent</span>
                  <strong>CoursePlanner</strong>
                </div>
                <div class="mini-panel">
                  <span>证据卡片</span>
                  <strong>正式证据 / 候选证据 / 许可证</strong>
                </div>
              </div>
            </div>
            <div class="scene-flow">
              <span>知识</span>
              <MoveRight :size="15" />
              <span>图谱</span>
              <MoveRight :size="15" />
              <span>诊断</span>
              <MoveRight :size="15" />
              <span>规划</span>
              <MoveRight :size="15" />
              <span>资源</span>
              <MoveRight :size="15" />
              <span>反馈</span>
            </div>
          </div>
        </div>
      </section>

      <section id="capability" class="section section--soft">
        <div class="product-home__container section-grid" data-reveal>
          <div class="section-copy section-copy--hero">
            <span class="eyebrow">产品核心价值</span>
            <h2>不是普通课程管理工具，而是让课程知识真正流动起来的平台。</h2>
            <p>
              课程资料、知识图谱、学情诊断、多智能体协作和资源生成不再彼此割裂，而是形成一条连续的产品链路。
            </p>
          </div>

          <div class="capability-grid">
            <article class="capability-card capability-card--large">
              <span class="capability-card__icon"><Database :size="20" /></span>
              <h3>课程资料变成可信知识库</h3>
              <p>把分散的文档整理成可追溯的知识资产，明确来源、定位、许可证和审核状态。</p>
              <div class="capability-mini">
                <b>PDF 教材</b>
                <b>HTML 讲义</b>
                <b>正式证据</b>
              </div>
            </article>

            <article class="capability-card capability-card--mid">
              <span class="capability-card__icon"><GitBranch :size="20" /></span>
              <h3>知识图谱约束学习路径</h3>
              <p>先修关系、知识缺口和当前掌握度一起决定下一步，而不是简单推荐内容列表。</p>
              <div class="capability-graph">
                <span>基础</span>
                <i />
                <span>核心</span>
                <i />
                <span>实践</span>
              </div>
            </article>

            <article class="capability-card capability-card--mid">
              <span class="capability-card__icon"><Workflow :size="20" /></span>
              <h3>多个 Agent 协同完成规划</h3>
              <p>诊断、检索、规划和生成分工明确，结果汇总到同一条闭环链路里。</p>
              <div class="agent-strip">
                <span>诊断</span>
                <span>规划</span>
                <span>检索</span>
                <span>生成</span>
              </div>
            </article>
          </div>
        </div>
      </section>

      <section id="scenarios" class="section">
        <div class="product-home__container" data-reveal>
          <div class="section-grid section-grid--roles">
            <div class="section-copy">
              <span class="eyebrow">平台服务对象</span>
              <h2>面向课程建设者、教师、学习者和学校机构。</h2>
              <p>同一个平台，不同角色看到的重点不同，但都围绕课程知识库、学情和规划协同工作。</p>
            </div>

            <div class="roles-layout">
              <div class="role-tabs">
                <button
                  v-for="role in roleCards"
                  :key="role.key"
                  class="role-tab"
                  :class="{ 'is-active': activeRoleKey === role.key }"
                  type="button"
                  @click="setActiveRole(role.key)"
                >
                  <component :is="role.icon" :size="18" />
                  <span>{{ role.title }}</span>
                </button>
              </div>

              <div class="role-preview">
                <div class="role-preview__head">
                  <span>{{ activeRole.badge }}</span>
                  <strong>{{ activeRole.previewTitle }}</strong>
                </div>
                <h3>{{ activeRole.title }}</h3>
                <p>{{ activeRole.description }}</p>
                <div class="role-preview__list">
                  <span v-for="item in activeRole.previewItems" :key="item">{{ item }}</span>
                </div>
                <RouterLink :to="activeRole.key === 'learner' ? '/diagnosis' : '/app'" class="text-link">
                  了解更多 <ChevronRight :size="15" />
                </RouterLink>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="workflow" class="section section--soft">
        <div class="product-home__container" data-reveal>
          <div class="section-copy section-copy--center">
            <span class="eyebrow">平台如何工作</span>
            <h2>资料进入、知识组织、学情理解、路径规划、资源生成、反馈更新。</h2>
            <p>把复杂系统讲清楚，不靠空泛口号，而靠一条用户能看懂的连续工作流。</p>
          </div>

          <div class="workflow-layout">
            <div class="workflow-track">
              <button
                v-for="step in workflowSteps"
                :key="step.key"
                class="workflow-step"
                :class="{ 'is-active': activeStepKey === step.key }"
                type="button"
                @click="setActiveStep(step.key)"
              >
                <span class="workflow-step__badge">{{ step.badge }}</span>
                <strong>{{ step.title }}</strong>
                <small>{{ step.summary }}</small>
              </button>
            </div>

            <div class="workflow-preview">
              <div class="workflow-preview__main">
                <span class="eyebrow">{{ activeStep.badge }}</span>
                <h3>{{ activeStep.previewTitle }}</h3>
                <p>{{ activeStep.detail }}</p>
                <div class="workflow-preview__chips">
                  <span v-for="line in activeStep.previewLines" :key="line">{{ line }}</span>
                </div>
              </div>
              <div class="workflow-preview__aside">
                <div>
                  <span>当前节点</span>
                  <strong>{{ activeStep.title }}</strong>
                </div>
                <div>
                  <span>动作</span>
                  <strong>{{ activeStep.summary }}</strong>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="agents" class="section">
        <div class="product-home__container" data-reveal>
          <div class="section-grid section-grid--agents">
            <div class="section-copy">
              <span class="eyebrow">多智能体协作</span>
              <h2>学情一变化，平台就自动触发新的课程规划链路。</h2>
              <p>这不是架构图，而是一段真实可理解的产品过程：测评结果会推动诊断、规划、检索、生成和反馈更新。</p>
            </div>

            <div class="agents-story">
              <div class="agents-story__left">
                <GuideFigure :size="126" />
                <div class="agents-story__bubble">
                  <strong>当前学习反馈</strong>
                  <p>发现“先修概念”还有两个空缺，建议先补补再进入新路径。</p>
                </div>
              </div>

              <div class="agents-story__right">
                <div v-for="(item, index) in agentFlow" :key="item.title" class="agent-flow-item" :class="item.tone">
                  <span class="agent-flow-item__index">{{ String(index + 1).padStart(2, "0") }}</span>
                  <div>
                    <strong>{{ item.title }}</strong>
                    <p>{{ item.detail }}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="governance" class="section section--soft">
        <div class="product-home__container" data-reveal>
          <div class="section-grid section-grid--governance">
            <div class="section-copy">
              <span class="eyebrow">知识库与证据治理</span>
              <h2>每一份课程资源，都有可追溯的知识依据。</h2>
              <p>平台不是简单生成内容，而是先管理来源、审核状态、证据定位和知识关系，再进入资源生成。</p>
            </div>

            <div class="governance-board">
              <div v-for="column in governanceColumns" :key="column.title" class="governance-board__column">
                <strong>{{ column.title }}</strong>
                <span v-for="item in column.items" :key="item">{{ item }}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="planning" class="section">
        <div class="product-home__container" data-reveal>
          <div class="section-grid section-grid--planning">
            <div class="section-copy">
              <span class="eyebrow">个性化课程规划</span>
              <h2>同一门课程，不同学习者应该得到不同路径。</h2>
              <p>已掌握内容可以跳过，缺失先修会进入补救队列，反馈结果会继续影响下一次规划。</p>
              <RouterLink to="/learning-path" class="text-link">
                查看课程规划 <ChevronRight :size="15" />
              </RouterLink>
            </div>

            <div class="planning-grid">
              <article v-for="card in planningCards" :key="card.learner" class="planning-card">
                <span>{{ card.learner }}</span>
                <h3>{{ card.title }}</h3>
                <div class="planning-path">
                  <b v-for="(chip, index) in card.chips" :key="chip" :class="`state-${card.state[index] || 'neutral'}`">
                    {{ chip }}
                  </b>
                </div>
              </article>
            </div>
          </div>
        </div>
      </section>

      <section id="about" class="cta-section">
        <div class="product-home__container cta-section__inner" data-reveal>
          <div>
            <span class="eyebrow">开始体验</span>
            <h2>让课程内容真正连接起来，让每一次学习都成为下一次规划的依据。</h2>
          </div>
          <div class="cta-section__actions">
            <RouterLink to="/register" class="button button-primary">
              开始使用 <ArrowRight :size="17" />
            </RouterLink>
            <RouterLink to="/login" class="button button-secondary">登录</RouterLink>
          </div>
        </div>
      </section>
    </main>

    <footer class="footer">
      <div class="product-home__container footer__inner">
        <BrandWordmark compact />
        <nav aria-label="页脚导航">
          <a href="#capability">产品能力</a>
          <a href="#workflow">工作流程</a>
          <a href="#agents">多智能体</a>
          <RouterLink to="/login">登录</RouterLink>
        </nav>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.product-home {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  color: #172b4d;
  background:
    radial-gradient(circle at 80% 18%, rgba(105, 185, 255, 0.1), transparent 34%),
    radial-gradient(circle at 12% 62%, rgba(38, 183, 165, 0.07), transparent 32%),
    linear-gradient(180deg, #f9fcff 0%, #f4f9fd 48%, #f8fbfd 100%);
  isolation: isolate;
}

.product-home::after {
  position: absolute;
  inset: 0;
  z-index: 1;
  content: "";
  background:
    linear-gradient(90deg, rgba(249, 252, 255, 0.7) 0%, rgba(249, 252, 255, 0.32) 42%, rgba(249, 252, 255, 0.1) 100%),
    linear-gradient(180deg, rgba(249, 252, 255, 0.1) 0%, rgba(244, 249, 253, 0.22) 52%, rgba(248, 251, 253, 0.12) 100%);
  pointer-events: none;
}

.product-home > :not(.home-background) {
  position: relative;
  z-index: 2;
}

.home-background {
  position: absolute;
  inset: 0;
  z-index: 0;
  min-height: 680vh;
  overflow: hidden;
  pointer-events: none;
  transform: translateZ(0);
  backface-visibility: hidden;
}

.home-background__scene {
  position: absolute;
  top: var(--scene-top);
  left: 0;
  right: 0;
  height: var(--scene-height);
  overflow: visible;
}

.home-background__scene img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: var(--scene-position);
  opacity: var(--scene-opacity);
  transform: translate3d(0, var(--home-bg-shift, 0px), 0) scale(var(--scene-scale));
  transform-origin: center;
  backface-visibility: hidden;
}

.home-background__scene:not(.home-background__scene--hero):not(.home-background__scene--ending) img {
  -webkit-mask-image: linear-gradient(to bottom, transparent 0%, #000 13%, #000 87%, transparent 100%);
  mask-image: linear-gradient(to bottom, transparent 0%, #000 13%, #000 87%, transparent 100%);
}

.home-background__scene--hero img {
  -webkit-mask-image: linear-gradient(to bottom, #000 0%, #000 82%, transparent 100%);
  mask-image: linear-gradient(to bottom, #000 0%, #000 82%, transparent 100%);
}

.home-background__scene--ending img {
  -webkit-mask-image: linear-gradient(to bottom, transparent 0%, #000 14%, #000 100%);
  mask-image: linear-gradient(to bottom, transparent 0%, #000 14%, #000 100%);
}

.home-background__transition {
  position: absolute;
  left: 0;
  right: 0;
  bottom: -15vh;
  z-index: 1;
  height: 30vh;
  background: linear-gradient(
    to bottom,
    transparent,
    rgba(247, 251, 255, 0.18),
    rgba(247, 251, 255, 0.38),
    transparent
  );
}

.product-home__container {
  width: min(1240px, calc(100% - 48px));
  margin: 0 auto;
}

.product-home main > section[id] {
  scroll-margin-top: 104px;
}

.hero {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(420px, 1.05fr);
  gap: 56px;
  align-items: center;
  min-height: 108svh;
  padding: 72px 0 72px;
  overflow: hidden;
  isolation: isolate;
}

.hero::before {
  position: absolute;
  inset: -72px calc((100vw - min(1240px, calc(100vw - 48px))) / -2);
  z-index: 0;
  content: "";
  background:
    radial-gradient(circle at 82% 20%, rgba(255, 255, 255, 0.18), transparent 28%),
    linear-gradient(90deg, rgba(248, 251, 255, 0.1) 0%, rgba(248, 251, 255, 0.04) 54%, transparent 100%);
  opacity: 0.34;
  pointer-events: none;
}

.hero::after {
  position: absolute;
  inset: auto calc((100vw - min(1240px, calc(100vw - 48px))) / -2) -1px;
  z-index: 1;
  height: 150px;
  content: "";
  background: linear-gradient(180deg, transparent, rgba(248, 251, 255, 0.98));
  pointer-events: none;
}

.hero > * {
  position: relative;
  z-index: 2;
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #356ae6;
  font-size: 13px;
  font-weight: 850;
  letter-spacing: 0;
}

.hero-copy h1,
.section-copy h2,
.cta-section h2 {
  margin: 16px 0 12px;
  letter-spacing: 0;
}

.hero-copy h1 {
  max-width: 10ch;
  font-size: clamp(48px, 5vw, 68px);
  line-height: 1.03;
  color: #12223c;
  text-wrap: balance;
}

.hero-copy p,
.section-copy p {
  max-width: 640px;
  margin: 0;
  color: #5f718a;
  font-size: 16px;
  line-height: 1.82;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 26px;
}

.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 48px;
  padding: 0 20px;
  border: 1px solid transparent;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 850;
  transition: transform 0.18s ease, box-shadow 0.18s ease, background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

.button:hover {
  transform: translateY(-2px);
}

.button-primary {
  color: #fff;
  background: #356ae6;
  box-shadow: 0 12px 24px rgba(53, 106, 230, 0.18);
}

.button-primary:hover {
  background: #285acb;
  box-shadow: 0 16px 30px rgba(53, 106, 230, 0.24);
}

.button-secondary {
  color: #172b4d;
  background: #fff;
  border-color: #dfe8f3;
}

.button-secondary:hover {
  color: #356ae6;
  background: #edf4ff;
  border-color: #c5d7f7;
}

.hero-tags,
.hero-notes,
.capability-mini,
.capability-graph,
.agent-strip,
.workflow-preview__chips,
.role-preview__list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.hero-tags {
  margin-top: 22px;
}

.hero-tags span,
.hero-notes span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  padding: 0 12px;
  color: #4f6480;
  background: #fff;
  border: 1px solid #dfe8f3;
  border-radius: 999px;
  font-size: 12px;
}

.hero-notes {
  margin-top: 18px;
  color: #6c7f98;
}

.hero-notes svg {
  color: #1da35f;
}

.hero-visual {
  position: relative;
  padding-top: 14px;
}

.hero-visual::before {
  position: absolute;
  inset: 28px 20px 12px 18px;
  content: "";
  background:
    radial-gradient(circle at 22% 28%, rgba(53, 106, 230, 0.14), transparent 20%),
    radial-gradient(circle at 80% 20%, rgba(24, 167, 160, 0.12), transparent 18%),
    radial-gradient(circle at 60% 78%, rgba(120, 86, 217, 0.09), transparent 22%);
  filter: blur(14px);
  opacity: 0.9;
}

.hero-visual::after {
  position: absolute;
  inset: 48px 0 0 0;
  content: "";
  border-radius: 34px;
  border: 1px solid rgba(223, 232, 243, 0.5);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.45), rgba(255, 255, 255, 0.08));
}

.hero-visual > * {
  position: relative;
  z-index: 1;
}

.scene-card--wide {
  position: relative;
  padding: 22px;
  overflow: hidden;
  background:
    radial-gradient(circle at 26% 18%, rgba(53, 106, 230, 0.12), transparent 28%),
    radial-gradient(circle at 76% 22%, rgba(24, 167, 160, 0.12), transparent 24%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.99), rgba(242, 247, 255, 0.98));
  border: 1px solid #d5e0ee;
  border-radius: 32px;
  box-shadow: 0 30px 70px rgba(39, 72, 112, 0.16);
}

.scene-card__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e5edf7;
}

.scene-card__top span,
.scene-card__top strong {
  display: block;
}

.scene-card__top span {
  color: #6d7f96;
  font-size: 11px;
}

.scene-card__top strong {
  color: #172b4d;
  font-size: 14px;
}

.scene-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.44fr) minmax(280px, 1fr) minmax(0, 0.44fr);
  gap: 16px;
  align-items: center;
}

.scene-column {
  display: grid;
  gap: 14px;
}

.mini-panel {
  padding: 16px;
  background: #fff;
  border: 1px solid #dde6f2;
  border-radius: 20px;
  box-shadow: 0 12px 28px rgba(39, 72, 112, 0.08);
}

.mini-panel span {
  display: block;
  color: #6d7f96;
  font-size: 11px;
}

.mini-panel strong {
  display: block;
  margin-top: 6px;
  font-size: 14px;
  line-height: 1.5;
}

.mini-panel--soft {
  background: linear-gradient(180deg, #f4f8ff, #edf3ff);
}

.mini-panel--accent {
  background: linear-gradient(180deg, #edf4ff, #e5efff);
  border-color: #c8dbff;
}

.scene-core {
  position: relative;
  display: grid;
  justify-items: center;
  align-items: center;
  padding: 12px 0 16px;
}

.scene-core__glow {
  position: absolute;
  inset: 18px 38px;
  background:
    radial-gradient(circle at 50% 45%, rgba(53, 106, 230, 0.18), transparent 42%),
    radial-gradient(circle at 50% 60%, rgba(24, 167, 160, 0.14), transparent 46%);
  filter: blur(6px);
}

.scene-core__caption {
  position: relative;
  margin-top: 6px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.86);
  border: 1px solid #e1e9f4;
  border-radius: 16px;
  text-align: center;
  box-shadow: 0 12px 24px rgba(39, 72, 112, 0.08);
}

.scene-core__caption span,
.scene-core__caption strong {
  display: block;
}

.scene-core__caption span {
  color: #6d7f96;
  font-size: 11px;
}

.scene-core__caption strong {
  margin-top: 4px;
  font-size: 14px;
}

.scene-flow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 16px;
  padding: 14px 16px;
  color: #5f718a;
  background: linear-gradient(180deg, #f8fbff, #f2f7ff);
  border: 1px solid #dfe8f4;
  border-radius: 18px;
  font-size: 12px;
  font-weight: 700;
}

.section {
  position: relative;
  min-height: 86svh;
  padding: 86px 0;
  overflow: hidden;
  isolation: isolate;
}

.section + .section {
  margin-top: -84px;
}

.section::before {
  position: absolute;
  inset: -9% 0;
  z-index: 0;
  content: "";
  background:
    radial-gradient(circle at 15% 22%, rgba(255, 255, 255, 0.1), transparent 25%),
    radial-gradient(circle at 86% 58%, rgba(255, 255, 255, 0.08), transparent 28%);
  opacity: 0.24;
  pointer-events: none;
  -webkit-mask-image: linear-gradient(180deg, transparent 0%, #000 18%, #000 82%, transparent 100%);
  mask-image: linear-gradient(180deg, transparent 0%, #000 18%, #000 82%, transparent 100%);
}

.section::after {
  position: absolute;
  inset: 0;
  z-index: 1;
  content: "";
  background:
    linear-gradient(90deg, rgba(248, 251, 255, 0.38), rgba(248, 251, 255, 0.12) 48%, rgba(248, 251, 255, 0.22)),
    radial-gradient(circle at 16% 20%, rgba(53, 106, 230, 0.08), transparent 26%),
    radial-gradient(circle at 86% 72%, rgba(24, 167, 160, 0.08), transparent 24%);
  pointer-events: none;
}

.section > .product-home__container {
  position: relative;
  z-index: 2;
}

.section--soft {
  background: rgba(255, 255, 255, 0.08);
  border-top: 1px solid rgba(223, 241, 246, 0.46);
  border-bottom: 1px solid rgba(223, 241, 246, 0.46);
}

.section-grid {
  display: grid;
  gap: 30px;
  align-items: start;
}

.section-grid--roles,
.section-grid--agents,
.section-grid--governance,
.section-grid--planning {
  grid-template-columns: minmax(0, 0.88fr) minmax(0, 1.12fr);
}

.section-copy--hero h2 {
  max-width: 14ch;
}

.section-copy--center {
  max-width: 820px;
  margin: 0 auto 28px;
  text-align: center;
}

.section-copy h2 {
  font-size: clamp(30px, 3.8vw, 48px);
  line-height: 1.12;
}

.capability-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 0.85fr);
  gap: 16px;
}

.capability-card {
  padding: 22px;
  background: #fff;
  border: 1px solid #dfe8f3;
  border-radius: 24px;
  box-shadow: 0 14px 32px rgba(39, 72, 112, 0.07);
}

.capability-card--large {
  grid-row: span 2;
  min-height: 284px;
}

.capability-card--mid {
  min-height: 134px;
}

.capability-card__icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  color: #356ae6;
  background: #edf4ff;
  border-radius: 14px;
}

.capability-card h3,
.role-preview h3,
.workflow-preview__main h3,
.planning-card h3 {
  margin: 16px 0 8px;
  font-size: 20px;
}

.capability-card p,
.role-preview p,
.workflow-preview__main p {
  color: #667994;
  font-size: 14px;
  line-height: 1.7;
}

.capability-mini {
  margin-top: 18px;
}

.capability-mini b,
.agent-strip span {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 0 12px;
  color: #2f6fec;
  background: #edf4ff;
  border: 1px solid #cfe0ff;
  border-radius: 999px;
  font-size: 12px;
}

.capability-graph {
  align-items: center;
  margin-top: 18px;
}

.capability-graph span {
  display: inline-flex;
  align-items: center;
  min-height: 36px;
  padding: 0 12px;
  color: #356ae6;
  background: #f3f7ff;
  border: 1px solid #d7e4ff;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 700;
}

.capability-graph i {
  width: 22px;
  height: 2px;
  background: linear-gradient(90deg, #c8d6ea, #356ae6);
  border-radius: 99px;
}

.roles-layout {
  display: grid;
  grid-template-columns: minmax(250px, 0.7fr) minmax(0, 1.3fr);
  gap: 16px;
}

.role-tabs {
  display: grid;
  gap: 12px;
}

.role-tab {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  min-height: 58px;
  padding: 0 16px;
  color: #4f6480;
  background: #fff;
  border: 1px solid #dfe8f3;
  border-radius: 18px;
  font-size: 14px;
  font-weight: 700;
  text-align: left;
  transition: transform 0.18s ease, border-color 0.18s ease, background-color 0.18s ease, color 0.18s ease;
}

.role-tab:hover,
.role-tab.is-active {
  color: #356ae6;
  background: #edf4ff;
  border-color: #cfe0ff;
  transform: translateY(-2px);
}

.role-preview {
  padding: 24px;
  background:
    radial-gradient(circle at top right, rgba(53, 106, 230, 0.08), transparent 24%),
    #fff;
  border: 1px solid #dfe8f3;
  border-radius: 24px;
  box-shadow: 0 16px 34px rgba(39, 72, 112, 0.08);
}

.role-preview__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.role-preview__head span {
  color: #356ae6;
  font-size: 12px;
  font-weight: 800;
}

.role-preview__head strong {
  color: #8b9fb8;
  font-size: 12px;
}

.role-preview__list {
  margin-top: 18px;
}

.role-preview__list span,
.workflow-preview__chips span {
  display: inline-flex;
  align-items: center;
  min-height: 36px;
  padding: 0 12px;
  color: #5f718a;
  background: #f7f9fc;
  border: 1px solid #e7edf5;
  border-radius: 12px;
  font-size: 12px;
}

.workflow-layout {
  display: grid;
  gap: 18px;
}

.workflow-track {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.workflow-step {
  padding: 16px;
  text-align: left;
  background: #fff;
  border: 1px solid #dfe8f3;
  border-radius: 20px;
  box-shadow: 0 12px 28px rgba(39, 72, 112, 0.06);
  transition: transform 0.18s ease, border-color 0.18s ease, background-color 0.18s ease;
}

.workflow-step:hover,
.workflow-step.is-active {
  border-color: #cfe0ff;
  background: #f5f9ff;
  transform: translateY(-3px);
}

.workflow-step__badge {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  color: #356ae6;
  background: #edf4ff;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
}

.workflow-step strong {
  display: block;
  margin: 12px 0 6px;
  font-size: 16px;
}

.workflow-step small {
  color: #667994;
  font-size: 12px;
  line-height: 1.6;
}

.workflow-preview {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(250px, 0.8fr);
  gap: 16px;
}

.workflow-preview__main,
.workflow-preview__aside {
  padding: 24px;
  background: #fff;
  border: 1px solid #dfe8f3;
  border-radius: 24px;
  box-shadow: 0 14px 32px rgba(39, 72, 112, 0.07);
}

.workflow-preview__aside {
  display: grid;
  gap: 14px;
}

.workflow-preview__aside span {
  display: block;
  color: #8b9fb8;
  font-size: 11px;
}

.workflow-preview__aside strong {
  display: block;
  margin-top: 4px;
  font-size: 14px;
  line-height: 1.5;
}

.agents-story {
  display: grid;
  grid-template-columns: minmax(0, 0.82fr) minmax(0, 1.18fr);
  gap: 16px;
}

.agents-story__left {
  display: grid;
  gap: 14px;
  align-content: start;
}

.agents-story__bubble {
  padding: 18px;
  background: #f3f0ff;
  border: 1px solid #e2d9fb;
  border-radius: 22px;
}

.agents-story__bubble strong {
  display: block;
  margin-bottom: 8px;
  color: #5b4a88;
  font-size: 13px;
}

.agents-story__bubble p {
  margin: 0;
  color: #62528d;
  font-size: 13px;
  line-height: 1.7;
}

.agents-story__right {
  display: grid;
  gap: 12px;
}

.agent-flow-item {
  display: grid;
  grid-template-columns: 46px minmax(0, 1fr);
  gap: 12px;
  align-items: center;
  padding: 16px;
  background: #fff;
  border: 1px solid #dfe8f3;
  border-radius: 20px;
  box-shadow: 0 12px 28px rgba(39, 72, 112, 0.06);
}

.agent-flow-item__index {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  color: #356ae6;
  background: #edf4ff;
  border-radius: 16px;
  font-size: 12px;
  font-weight: 850;
}

.agent-flow-item strong {
  display: block;
  font-size: 15px;
}

.agent-flow-item p {
  margin: 4px 0 0;
  color: #667994;
  font-size: 13px;
  line-height: 1.6;
}

.agent-flow-item.done .agent-flow-item__index { color: #1d9c5e; background: #eaf8f0; }
.agent-flow-item.review .agent-flow-item__index { color: #bd7d18; background: #fff5df; }
.agent-flow-item.current .agent-flow-item__index { color: #fff; background: #356ae6; }
.agent-flow-item.support .agent-flow-item__index { color: #0b91ac; background: #ecfbfd; }

.governance-board {
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.1fr) minmax(0, 0.95fr);
  gap: 14px;
}

.governance-board__column {
  display: grid;
  gap: 10px;
  padding: 20px;
  background: #fff;
  border: 1px solid #dfe8f3;
  border-radius: 24px;
  box-shadow: 0 14px 30px rgba(39, 72, 112, 0.06);
}

.governance-board__column strong {
  margin-bottom: 4px;
  font-size: 16px;
}

.governance-board__column span {
  display: grid;
  place-items: center;
  min-height: 42px;
  padding: 10px 12px;
  color: #5f718a;
  background: #f7f9fc;
  border: 1px solid #e7edf5;
  border-radius: 14px;
  font-size: 12px;
}

.planning-grid {
  display: grid;
  gap: 16px;
}

.planning-card {
  padding: 22px;
  background: #fff;
  border: 1px solid #dfe8f3;
  border-radius: 24px;
  box-shadow: 0 14px 30px rgba(39, 72, 112, 0.07);
}

.planning-card > span {
  color: #7856d9;
  font-size: 12px;
  font-weight: 800;
}

.planning-card h3 {
  max-width: 18ch;
}

.planning-path {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(92px, 1fr));
  gap: 10px;
}

.planning-path b {
  display: grid;
  place-items: center;
  min-height: 44px;
  padding: 8px;
  border-radius: 14px;
  border: 1px solid #dfe6ef;
  background: #f5f7fa;
  color: #6b7d94;
  font-size: 12px;
  text-align: center;
}

.planning-path .state-已掌握,
.planning-path .state-done {
  color: #1d9c5e;
  background: #eaf8f0;
  border-color: #b9e7ca;
}

.planning-path .state-进行中,
.planning-path .state-current {
  color: #fff;
  background: #356ae6;
  border-color: #356ae6;
}

.planning-path .state-待学习,
.planning-path .state-neutral {
  color: #6b7d94;
  background: #f5f7fa;
}

.planning-path .state-待补救,
.planning-path .state-review,
.planning-path .state-反馈更新 {
  color: #bd7d18;
  background: #fff5df;
  border-color: #edd39f;
}

.text-link {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin-top: 20px;
  color: #356ae6;
  font-size: 14px;
  font-weight: 850;
}

.cta-section {
  position: relative;
  padding: 78px 0;
  overflow: hidden;
  background: #172b4d;
  isolation: isolate;
}

.cta-section::before {
  position: absolute;
  inset: -18% 0;
  z-index: 0;
  content: "";
  background:
    linear-gradient(90deg, rgba(23, 43, 77, 0.9), rgba(23, 43, 77, 0.62));
  opacity: 0.92;
  pointer-events: none;
}

.cta-section::after {
  position: absolute;
  inset: 0;
  z-index: 1;
  content: "";
  background:
    radial-gradient(circle at 78% 26%, rgba(87, 160, 255, 0.24), transparent 28%),
    radial-gradient(circle at 12% 90%, rgba(38, 183, 165, 0.16), transparent 24%);
  pointer-events: none;
}

.cta-section__inner {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 28px;
}

.cta-section h2 {
  max-width: 740px;
  margin-bottom: 0;
  color: #fff;
  font-size: clamp(30px, 3.6vw, 46px);
  line-height: 1.14;
}

.cta-section__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.footer {
  background: #fff;
  border-top: 1px solid #edf1f6;
}

.footer__inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 24px 0;
}

.footer__inner strong,
.footer__inner small {
  display: block;
}

.footer__inner small {
  margin-top: 4px;
  color: #667994;
  font-size: 11px;
}

.footer nav {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  font-size: 12px;
}

.footer a {
  color: #5e718a;
}

.product-home [data-reveal] {
  opacity: 1;
  transform: translateY(14px);
  transition: opacity 0.56s ease, transform 0.56s ease;
}

.product-home [data-reveal].is-visible {
  opacity: 1;
  transform: translateY(0);
}

@media (max-width: 1120px) {
  .hero,
  .section-grid--roles,
  .section-grid--agents,
  .section-grid--governance,
  .section-grid--planning {
    grid-template-columns: 1fr;
  }

  .hero {
    min-height: auto;
  }

  .roles-layout {
    grid-template-columns: 1fr;
  }

  .workflow-track {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 780px) {
  .product-home__container {
    width: min(100% - 32px, 1240px);
  }

  .product-home::after {
    background:
      linear-gradient(90deg, rgba(249, 252, 255, 0.78) 0%, rgba(249, 252, 255, 0.42) 56%, rgba(249, 252, 255, 0.2) 100%),
      linear-gradient(180deg, rgba(249, 252, 255, 0.12) 0%, rgba(244, 249, 253, 0.26) 52%, rgba(248, 251, 253, 0.18) 100%);
  }

  .home-background {
    min-height: 720vh;
  }

  .home-background__scene {
    left: -18vw;
    right: -40vw;
  }

  .home-background__scene img {
    object-position: 62% center;
    opacity: 0.76;
    transform: translate3d(0, var(--home-bg-shift, 0px), 0) scale(1.18);
  }

  .home-background__scene--hero img {
    object-position: 64% center;
  }

  .home-background__scene--knowledge img,
  .home-background__scene--feedback img {
    object-position: 56% center;
  }

  .home-background__scene--ending img {
    object-position: 58% bottom;
  }

  .hero {
    gap: 28px;
    padding: 34px 0 52px;
  }

  .hero::before {
    inset: -34px -16px;
    background:
      radial-gradient(circle at 58% 24%, rgba(255, 255, 255, 0.26), transparent 30%),
      linear-gradient(180deg, rgba(248, 251, 255, 0.58) 0%, rgba(248, 251, 255, 0.36) 46%, rgba(248, 251, 255, 0.72) 100%);
    opacity: 0.7;
  }

  .section::before {
    inset: -5% -18%;
    background-position: var(--section-bg-position-mobile, center bottom);
    background-size: var(--section-bg-size-mobile, auto 70%);
    opacity: var(--section-bg-opacity-mobile, 0.18);
  }

  .section::after {
    background: linear-gradient(180deg, rgba(248, 251, 255, 0.58), rgba(248, 251, 255, 0.72));
  }

  .section + .section {
    margin-top: -54px;
  }

  .cta-section::before {
    background: linear-gradient(180deg, rgba(23, 43, 77, 0.92), rgba(23, 43, 77, 0.72));
  }

  .hero-copy h1 {
    max-width: 100%;
    font-size: 38px;
  }

  .hero-copy p,
  .section-copy p {
    font-size: 15px;
  }

  .hero-actions {
    display: grid;
    grid-template-columns: 1fr;
  }

  .button {
    width: 100%;
  }

  .scene-grid {
    grid-template-columns: 1fr;
  }

  .scene-core {
    padding: 10px 0 0;
  }

  .capability-grid {
    grid-template-columns: 1fr;
  }

  .capability-card--large {
    grid-row: auto;
  }

  .workflow-track {
    grid-template-columns: 1fr;
  }

  .workflow-preview {
    grid-template-columns: 1fr;
  }

  .agents-story {
    grid-template-columns: 1fr;
  }

  .governance-board {
    grid-template-columns: 1fr;
  }

  .cta-section__inner,
  .footer__inner {
    align-items: flex-start;
    flex-direction: column;
  }
}

@media (max-width: 460px) {
  .product-home__container {
    width: min(100% - 24px, 1240px);
  }

  .hero-copy h1 {
    font-size: 34px;
  }

  .section-copy h2,
  .cta-section h2 {
    font-size: 28px;
  }

  .scene-card--wide {
    padding: 16px;
    border-radius: 24px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .product-home *,
  .product-home *::before,
  .product-home *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }

  .product-home [data-reveal] {
    opacity: 1;
    transform: none;
  }
}
</style>
