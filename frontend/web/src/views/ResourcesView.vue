<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import MarkdownIt from "markdown-it";
import markdownItKatex from "markdown-it-katex";
import "katex/dist/katex.min.css";
import { BookOpen, CheckCircle2, Code2, Dumbbell, FileCheck2, MessageCircle, RefreshCw, Sparkles } from "lucide-vue-next";
import { useRouter } from "vue-router";
import ResourceCard from "@/components/ResourceCard.vue";
import AICoachPanel from "@/components/AICoachPanel.vue";
import StateBlocks from "@/components/StateBlocks.vue";
import { assessmentApi } from "@/api/assessment";
import { useLearningPathStore } from "@/stores/learningPath";

const router = useRouter();
const path = useLearningPathStore();
const active = ref("lecture");
const md = new MarkdownIt({ html: false, breaks: true }).use(markdownItKatex);

function normalizeMath(value: string): string {
  const protectedParts: string[] = [];
  const protectedText = String(value).replace(
    /```[\s\S]*?```|`[^`\n]*`|\$\$[\s\S]*?\$\$|\$(?:\\.|[^$\n])+\$/g,
    (part) => {
      const index = protectedParts.push(part) - 1;
      return `\uE000${index}\uE001`;
    },
  );
  let normalized = protectedText
    .replace(/\bfloor\(\(([^)\n]+)\)\s*\/\s*([^)]+)\)\s*\+\s*1\b/g, (_, numerator, denominator) =>
      `$\\left\\lfloor\\frac{${numerator}}{${denominator}}\\right\\rfloor+1$`,
    )
    .replace(/\b(\d+(?:\.\d+)?(?:\s*[×x]\s*\d+){1,3})\b/g, (_, dimensions) => `$${dimensions.replaceAll("×", "\\times")}$`)
    .replace(/\b([A-Za-z][A-Za-z0-9_']*)\s*(=|<|>)\s*(-?\d+(?:\.\d+)?)\b/g, (_, name, operator, number) => `$${name}${operator}${number}$`)
    .replace(/\b([A-Za-z][A-Za-z0-9_']*)\s*([·Σ×])\s*([A-Za-z][A-Za-z0-9_]*)\b/g, (_, left, operator, right) =>
      `$${left}${operator === "Σ" ? "\\sum" : "\\cdot"}${right}$`,
    );
  return normalized.replace(/\uE000(\d+)\uE001/g, (_, index) => protectedParts[Number(index)]);
}
const resources = computed(() => path.run?.resources as Record<string, any> | null);
const currentConceptTitle = computed(() => {
  const pathTitle = path.currentNode?.title || path.currentNode?.name;
  if (pathTitle) return pathTitle;
  const conceptId = resources.value?.concept_id || path.run?.profile?.knowledge_mastery?.[0]?.concept_id;
  if (!conceptId) return "当前推荐知识点";
  const labels: Record<string, string> = { scalar: "标量", vector: "向量", matrix: "矩阵", tensor: "张量", "hyperparameter-tuning": "超参数调优", "feature-label": "特征与标签", "backpropagation": "反向传播", "gradient-descent": "梯度下降", convolution: "卷积运算", pooling: "池化", embedding: "嵌入表示" };
  const slug = String(conceptId).split(".").at(-1) || String(conceptId);
  return labels[slug] || slug.replaceAll("-", " ");
});
const draft = computed(() => {
  const resourceResult = resources.value;
  return resourceResult?.formal_package?.draft || resourceResult?.preview_package?.draft || resourceResult?.draft || null;
});
const resourceStatus = computed(() => resources.value?.formal_package ? "正式资源" : "候选预览");
const quizResponses = ref<Record<string, number>>({});
const quizSubmitting = ref(false);
const quizSubmitted = ref(false);
const quizError = ref("");
const quizRefreshing = ref(false);
const learningNotice = ref("");
const quizStartedAt = Date.now();
const quizItems = computed(() => draft.value?.student_quiz?.items || []);
const quizReady = computed(() => quizItems.value.length > 0 && quizItems.value.every((item: { question_id: string }) => Number.isInteger(quizResponses.value[item.question_id])));

function renderBlocks(blocks: Array<{ title?: string; body?: string; code?: string }> = []) {
  return blocks.map((block) => [
    block.title ? `### ${block.title}` : "",
    block.body || "",
    block.code ? `\`\`\`python\n${block.code}\n\`\`\`` : "",
  ].filter(Boolean).join("\n\n")).join("\n\n");
}

const content = computed(() => {
  const lesson = draft.value;
  if (!lesson) return "## 资源准备中\n\n当前节点暂未生成资源包，请返回学习路径重新规划。";

  if (active.value === "lecture") {
    const lecture = lesson.lecture;
    if (!lecture) return "## 知识讲解\n\n当前资源包未包含讲解内容。";
    return [`## ${lecture.title || "知识讲解"}`, ...(lecture.sections || []), renderBlocks(lecture.blocks)].filter(Boolean).join("\n\n");
  }

  if (active.value === "example") {
    const examples = (lesson.lecture?.blocks || []).filter((block: { kind?: string }) => block.kind === "example");
    const protocol = lesson.practical_guide?.experiment_protocol || [];
    return ["## 示例演示", renderBlocks(examples), protocol.length ? "### 可复现实验\n" + protocol.map((item: string) => `- ${item}`).join("\n") : ""].filter(Boolean).join("\n\n");
  }

  if (active.value === "practice") {
    const guide = lesson.practical_guide;
    if (!guide) return "## 实践练习\n\n当前资源包未包含练习内容。";
    const exercise = guide.exercise;
    return [
      "## 实践练习",
      ...(guide.learning_steps || []).map((step: string, index: number) => `${index + 1}. ${step}`),
      exercise?.task ? `### 基础教学代码：最小可运行示例\n${exercise.task}` : "",
      exercise?.starter_code ? `\`\`\`python\n${exercise.starter_code}\n\`\`\`` : "",
      exercise?.checks?.length ? `#### 基础代码检查\n${exercise.checks.map((item: string) => `- ${item}`).join("\n")}` : "",
      guide.project_exercise?.task ? `### 项目练习代码：综合任务\n${guide.project_exercise.task}` : "",
      guide.project_exercise?.starter_code ? `\`\`\`python\n${guide.project_exercise.starter_code}\n\`\`\`` : "",
      guide.project_exercise?.checks?.length ? `#### 项目代码检查\n${guide.project_exercise.checks.map((item: string) => `- ${item}`).join("\n")}` : "",
    ].filter(Boolean).join("\n\n");
  }

  const quiz = lesson.student_quiz;
  if (!quiz?.items?.length) return "## 小测验\n\n当前资源包未包含测验内容。";
    return ["## 小测验", quiz.instructions || "完成以下题目，检查当前知识点掌握情况。", ...quiz.items.map((item: { prompt?: string; choices?: string[] }, index: number) => [
    `### 第 ${index + 1} 题`, item.prompt || "", ...(item.choices || []).map((choice: string, choiceIndex: number) => `${String.fromCharCode(65 + choiceIndex)}. ${choice}`),
  ].filter(Boolean).join("\n\n"))].join("\n\n");
});
const resourceCards = [
  { key: "lecture", title: "知识讲解", description: "从直觉、公式到关键概念，分步建立理解。", kind: "讲解" },
  { key: "example", title: "示例演示", description: "用一个完整例子把知识点放进真实问题。", kind: "示例" },
  { key: "practice", title: "实践练习", description: "动手完成一个小任务，巩固迁移能力。", kind: "练习" },
  { key: "quiz", title: "小测验", description: "用几道题检查是否真的掌握。", kind: "测验" },
];
function ask(value: string) { window.localStorage.setItem("zhijing.last-question", value); }

async function submitQuiz() {
  if (!path.run?.run_id || !path.currentNode || !quizReady.value || quizSubmitting.value) return;
  const submittedConceptId = path.currentNode.concept_id;
  quizSubmitting.value = true;
  quizError.value = "";
  learningNotice.value = "";
  try {
    const updated = await assessmentApi.submit(path.run.run_id, {
      assessment_id: `candidate-quiz-${Date.now()}`,
      concept_id: path.currentNode.concept_id,
      score: 0,
      responses: quizResponses.value,
      response_time_ms: Math.max(1_000, Date.now() - quizStartedAt),
      hint_count: 0,
      attempt_count: 1,
      passing_score: 0.6,
    });
    path.setRun(updated);
    const nextConceptId = updated?.planning?.current_node?.concept_id;
    const advanced = Boolean(nextConceptId && nextConceptId !== submittedConceptId);
    learningNotice.value = advanced
      ? "本次小测已通过，已切换到下一知识点的学习内容。"
      : "本次小测已记录，建议复习当前内容后再试一次。";
    quizResponses.value = {};
    quizSubmitted.value = false;
    active.value = advanced ? "lecture" : "quiz";
  } catch (reason) {
    quizError.value = reason instanceof Error ? reason.message : "小测验提交失败";
  } finally {
    quizSubmitting.value = false;
  }
}

async function refreshQuiz() {
  if (!path.run?.run_id || quizRefreshing.value) return;
  quizRefreshing.value = true;
  quizError.value = "";
  learningNotice.value = "";
  try {
    const updated = await assessmentApi.refreshResources(path.run.run_id);
    path.setRun(updated);
    quizResponses.value = {};
    quizSubmitted.value = false;
    learningNotice.value = "已按当前知识点重新生成学习材料和小测题目。";
  } catch (reason) {
    quizError.value = reason instanceof Error ? reason.message : "小测验重新生成失败";
  } finally {
    quizRefreshing.value = false;
  }
}

async function refreshLesson() {
  if (!path.run?.run_id || quizRefreshing.value) return;
  quizRefreshing.value = true;
  quizError.value = "";
  learningNotice.value = "";
  try {
    const updated = await assessmentApi.refreshResources(path.run.run_id);
    path.setRun(updated);
    quizResponses.value = {};
    quizSubmitted.value = false;
    learningNotice.value = "已按最新学习画像重新生成本节教案、练习和小测。";
  } catch (reason) {
    quizError.value = reason instanceof Error ? reason.message : "教案重新生成失败";
  } finally {
    quizRefreshing.value = false;
  }
}

onMounted(() => {
  if (path.run?.run_id && !String(draft.value?.lecture?.sections?.[0] || "").includes("个性化起点")) refreshLesson();
});
</script>

<template>
  <div class="page-stack">
    <div class="page-intro"><div><span class="eyebrow">LEARNING RESOURCES</span><h2>把知识学进去，而不是只看完</h2><p>当前资源围绕推荐知识点组织，支持讲解、示例、练习和测验的连续学习。</p></div><span class="status-pill status-pill-purple"><Sparkles :size="14" /> AI 辅助学习</span></div>
    <section v-if="!path.run" class="panel"><StateBlocks type="empty" title="还没有当前学习资源" message="生成学习路径后，系统会为当前推荐节点准备资源。" /><button class="button button-primary" @click="router.push('/learning-path')">查看学习路径</button></section>
    <template v-else>
      <section class="resource-context"><div class="resource-context-icon"><Code2 :size="22" /></div><div><span class="eyebrow">CURRENT NODE</span><h2>{{ currentConceptTitle }}</h2><p>{{ path.currentNode?.summary || "围绕当前推荐节点完成一次讲解、练习和测评。" }}</p></div><span class="status-pill" :class="{ 'status-pill-success': resourceStatus === '正式资源' }">{{ resourceStatus }}</span><button class="button button-secondary compact-button" :disabled="quizRefreshing" @click="refreshLesson"><RefreshCw :size="15" /> {{ quizRefreshing ? "正在生成…" : "按最新画像生成教案" }}</button></section>
      <p v-if="learningNotice" class="learning-notice">{{ learningNotice }}</p>
      <div class="resource-card-grid"><ResourceCard v-for="item in resourceCards" :key="item.key" :title="item.title" :description="item.description" :kind="item.kind" :status="resourceStatus" @open="active = item.key" /></div>
  <div class="content-grid content-grid-main"><section class="panel learning-reader"><div class="reader-tabs"><button v-for="item in resourceCards" :key="item.key" :class="{ active: active === item.key }" @click="active = item.key">{{ item.title }}</button></div><article v-if="active !== 'quiz'" class="markdown-content" v-html="md.render(normalizeMath(content))" /><section v-else class="quiz-reader"><div><span class="eyebrow">KNOWLEDGE CHECK</span><h2>小测验</h2><p v-html="md.renderInline(normalizeMath(draft?.student_quiz?.instructions || '完成所有题目后提交，结果会更新当前知识点掌握度。'))" /></div><div v-if="!quizItems.length" class="state-block"><strong>测验准备中</strong><p>当前资源包未包含可作答的小测验。</p></div><form v-else class="quiz-form" @submit.prevent="submitQuiz"><fieldset v-for="(question, questionIndex) in quizItems" :key="question.question_id" class="quiz-question" :disabled="quizSubmitting || quizSubmitted || quizRefreshing"><legend>第 {{ questionIndex + 1 }} 题</legend><p v-html="md.renderInline(normalizeMath(question.prompt || ''))" /><label v-for="(choice, choiceIndex) in question.choices" :key="choiceIndex" class="quiz-option" :class="{ selected: quizResponses[question.question_id] === choiceIndex }"><input v-model="quizResponses[question.question_id]" type="radio" :name="question.question_id" :value="choiceIndex" /><span>{{ String.fromCharCode(65 + choiceIndex) }}</span><b v-html="md.renderInline(normalizeMath(choice))" /></label></fieldset><p v-if="quizError" class="inline-error">{{ quizError }}</p><p v-if="quizSubmitted" class="quiz-success">答案已提交，学习路径已按测验结果更新。</p><div class="quiz-actions"><button class="button button-primary" type="submit" :disabled="!quizReady || quizSubmitting || quizSubmitted || quizRefreshing">{{ quizSubmitting ? "正在评分…" : quizSubmitted ? "已提交" : `提交 ${quizItems.length} 题并更新路径` }}</button><button class="button button-secondary" type="button" :disabled="quizSubmitting || quizRefreshing" @click="refreshQuiz"><RefreshCw :size="16" /> {{ quizRefreshing ? "正在重新生成…" : "重新生成本节小测" }}</button></div></form></section><div class="reader-actions"><button class="button button-secondary" @click="router.push('/assessment')"><FileCheck2 :size="16" /> 去完成测评</button><button class="button button-primary" @click="path.completeNode"><CheckCircle2 :size="16" /> 标记已完成</button></div></section><aside class="page-stack"><AICoachPanel @send="ask" /><section class="panel source-panel"><div class="panel-heading"><div><span class="eyebrow">EVIDENCE MANIFEST</span><h3>知识来源</h3></div><BookOpen :size="18" class="icon-muted" /></div><p>资源生成会区分正式依据和 candidate preview，当前结果以服务端返回的状态为准。</p><div class="source-status"><span class="online-dot" /> 已连接知识检索服务</div></section></aside></div>
    </template>
  </div>
</template>
