<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { BookOpen, CheckCircle2, Code2, FileCheck2, RefreshCw, Send, Sparkles } from "lucide-vue-next";
import { renderMarkdown } from "@/utils/math";
import { assessmentApi } from "@/api/assessment";
import { planningApi } from "@/api/planning";
import { useLearnerStore } from "@/stores/learner";
import { useLearningPathStore } from "@/stores/learningPath";
import { useLearningRecordsStore } from "@/stores/learningRecords";
import { courseIdFromProfile, courseTitle, knowledgeTitle } from "@/utils/knowledgeGraph";

type ReaderTab = "lecture" | "example" | "practice" | "assessment";

const props = defineProps<{
  conceptId: string;
  nodeTitle: string;
  initialTab?: ReaderTab;
}>();

const path = useLearningPathStore();
const learner = useLearnerStore();
const records = useLearningRecordsStore();
const activeTab = ref<ReaderTab>(props.initialTab || "lecture");
const busy = ref(false);
const error = ref("");
const notice = ref("");
const coachQuestion = ref("");
const coachAnswer = ref("");
const coachBusy = ref(false);
const practiceKind = ref<"basic" | "project">("basic");
const practiceSource = ref("");
const practiceResult = ref<any>(null);
const quizResponses = ref<Record<string, number>>({});
const quizResult = ref<any>(null);

const resources = computed(() => path.run?.resources as Record<string, any> | null);
const currentNode = computed(() => path.currentNode?.concept_id === props.conceptId ? path.currentNode : null);
const resourceReady = computed(() => currentNode.value?.concept_id === props.conceptId);
const draft = computed(() => {
  if (!resourceReady.value) return null;
  return resources.value?.formal_package?.draft || resources.value?.preview_package?.draft || resources.value?.draft || null;
});
const guide = computed(() => draft.value?.practical_guide || null);
const exercise = computed(() => practiceKind.value === "project" ? guide.value?.project_exercise || guide.value?.exercise : guide.value?.exercise);
const quizItems = computed(() => draft.value?.student_quiz?.items || []);
const progress = computed(() => path.run?.learning_progress?.concept_id === props.conceptId ? path.run.learning_progress : null);
const evidenceLabel = computed(() => resources.value?.formal_package ? "正式依据" : "候选依据");
const coachContext = computed(() => ({
  concept: props.nodeTitle,
  depth: currentNode.value?.depth || "当前深度未标注",
  mastery: currentNode.value?.mastery_score == null ? "待评估" : `${Math.round(currentNode.value.mastery_score * 100)}%`,
  evidence: evidenceLabel.value,
}));

function renderBlocks(blocks: Array<{ title?: string; body?: string; code?: string }> = []) {
  return blocks.map((block) => [
    block.title ? `### ${block.title}` : "",
    block.body || "",
    block.code ? `\`\`\`python\n${block.code}\n\`\`\`` : "",
  ].filter(Boolean).join("\n\n")).join("\n\n");
}

const content = computed(() => {
  if (!draft.value) return "## 资源准备中\n\n进入当前知识点后，平台会生成个性化讲解、实践和测评。";
  if (activeTab.value === "lecture") {
    const lecture = draft.value.lecture;
    return [`## ${lecture?.title || `${props.nodeTitle}讲解`}`, ...(lecture?.sections || []), renderBlocks(lecture?.blocks || [])].filter(Boolean).join("\n\n");
  }
  if (activeTab.value === "example") {
    const examples = (draft.value.lecture?.blocks || []).filter((block: { kind?: string }) => block.kind === "example");
    return ["## 示例演示", renderBlocks(examples), ...(guide.value?.experiment_protocol || []).map((item: string) => `- ${item}`)].filter(Boolean).join("\n\n");
  }
  if (activeTab.value === "practice") {
    return ["## 实践任务", ...(guide.value?.learning_steps || []).map((step: string, index: number) => `${index + 1}. ${step}`), exercise.value?.task ? `### ${practiceKind.value === "project" ? "项目练习" : "基础练习"}\n${exercise.value.task}` : ""].filter(Boolean).join("\n\n");
  }
  return `## 小测验\n\n${draft.value.student_quiz?.instructions || "完成以下题目，检查当前知识点掌握情况。"}`;
});

function record(type: "resource_started" | "resource_completed" | "review_completed" | "assessment_completed", title: string, description: string, extra: Record<string, unknown> = {}) {
  const occurredAt = new Date().toISOString();
  const courseId = courseIdFromProfile(learner.profile) || path.run?.handoff?.chapter_id || "current-course";
  records.upsert({
    id: `${path.run?.run_id || "local"}:${props.conceptId}:${type}:${Math.floor(Date.now() / 1000)}`,
    learnerId: learner.profile?.learner_id || "current-learner",
    courseId,
    courseTitle: courseTitle(courseId),
    knowledgeNodeId: props.conceptId,
    knowledgeNodeTitle: props.nodeTitle || knowledgeTitle(props.conceptId),
    resourceId: `${path.run?.run_id || "local"}:${props.conceptId}:resource`,
    resourceTitle: `${props.nodeTitle}学习资源`,
    assessmentId: null,
    attemptId: null,
    type,
    title,
    description,
    durationSeconds: null,
    completionRate: progress.value?.lecture_progress ?? null,
    previousMastery: null,
    currentMastery: currentNode.value?.mastery_score ?? null,
    assessmentScore: null,
    assessmentAccuracy: null,
    previousRecommendedNodeId: props.conceptId,
    currentRecommendedNodeId: path.run?.planning?.current_node?.concept_id || null,
    unlockedNodeIds: [],
    occurredAt,
    createdAt: occurredAt,
    source: "local-event",
    metadata: { runId: path.run?.run_id, ...extra },
  });
}

async function askCoach() {
  if (!coachQuestion.value.trim() || !path.run?.run_id || coachBusy.value) return;
  coachBusy.value = true;
  coachAnswer.value = "";
  error.value = "";
  try {
    const reply = await assessmentApi.coach(path.run.run_id, { concept_id: props.conceptId, question: coachQuestion.value.trim() });
    coachAnswer.value = String(reply?.answer || "AI 顾问暂未返回回答。");
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "AI 顾问暂时不可用";
  } finally {
    coachBusy.value = false;
  }
}

async function saveLectureProgress() {
  if (!path.run?.run_id || busy.value) return;
  busy.value = true;
  error.value = "";
  const current = progress.value?.lecture_progress || 0;
  try {
    const updated = await planningApi.recordLectureProgress(path.run.run_id, props.conceptId, Math.min(1, current + 0.25));
    path.setRun(updated);
    const nextProgress = updated.learning_progress?.lecture_progress || 0;
    record(nextProgress >= 1 ? "resource_completed" : "resource_started", "讲义阅读进度更新", `${props.nodeTitle} 已记录到 ${Math.round(nextProgress * 100)}%。`);
    notice.value = "讲义进度已写入学习成长记录。";
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "讲义进度保存失败";
  } finally {
    busy.value = false;
  }
}

async function submitPractice() {
  if (!path.run?.run_id || !practiceSource.value.trim() || busy.value) return;
  busy.value = true;
  practiceResult.value = null;
  try {
    practiceResult.value = await assessmentApi.practiceReview(path.run.run_id, { concept_id: props.conceptId, source: practiceSource.value, exercise_kind: practiceKind.value });
    if (practiceResult.value?.accepted) {
      const updated = await planningApi.runById(path.run.run_id);
      path.setRun(updated);
      record("review_completed", "实践审核通过", `${props.nodeTitle} 的${practiceKind.value === "project" ? "项目" : "基础"}练习已通过静态检查。`);
      notice.value = "实践审核通过，掌握度和学习路径已同步。";
    }
  } catch (reason) {
    practiceResult.value = { accepted: false, feedback: reason instanceof Error ? reason.message : "实践审核失败" };
  } finally {
    busy.value = false;
  }
}

async function submitQuiz() {
  if (!path.run?.run_id || !quizItems.value.length || busy.value) return;
  busy.value = true;
  quizResult.value = null;
  try {
    const result = await assessmentApi.submit(path.run.run_id, { assessment_id: `resource-quiz-${Date.now()}`, concept_id: props.conceptId, responses: quizResponses.value, score: 0, response_time_ms: 60_000, hint_count: 0, attempt_count: 1 });
    quizResult.value = result;
    if (result?.status) path.setRun(result);
    record("assessment_completed", "完成知识点测评", `${props.nodeTitle} 的小测结果已写回学习路径。`, { assessmentScore: result?.learning_progress?.assessment_passed ? 1 : 0 });
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "小测验提交失败";
  } finally {
    busy.value = false;
  }
}

watch(exercise, (value) => { if (value?.starter_code && !practiceSource.value) practiceSource.value = value.starter_code; }, { immediate: true });
watch(() => props.initialTab, (value) => { if (value) activeTab.value = value; });
</script>

<template>
  <section class="learning-resource-reader">
    <div class="reader-heading"><div><span class="eyebrow">LEARNING WORKBENCH</span><h4>{{ nodeTitle }} · 个性化资源</h4><p>当前上下文：{{ coachContext.depth }} · 掌握度 {{ coachContext.mastery }} · {{ coachContext.evidence }}</p></div><span class="status-pill" :class="{ 'status-pill-success': resourceReady && resources?.formal_package }">{{ !resourceReady ? "正在生成" : resources?.formal_package ? "正式资源" : "候选预览" }}</span></div>
    <div class="reader-tabs"><button v-for="item in ([['lecture', '讲解'], ['example', '示例'], ['practice', '实践'], ['assessment', '测评']] as Array<[ReaderTab, string]>)" :key="item[0]" type="button" :class="{ active: activeTab === item[0] }" @click="activeTab = item[0]">{{ item[1] }}</button></div>
    <article class="reader-content" v-html="renderMarkdown(content)" />

    <div v-if="activeTab === 'lecture'" class="reader-action-row"><button class="button button-secondary" :disabled="busy || progress?.lecture_progress === 1" @click="saveLectureProgress"><BookOpen :size="15" /> {{ progress?.lecture_progress === 1 ? "讲义已完成" : "记录本节进度" }}</button></div>
    <div v-if="activeTab === 'practice'" class="practice-panel"><div class="practice-selector"><span>练习类型</span><select v-model="practiceKind"><option value="basic">基础练习</option><option value="project">项目练习</option></select></div><p class="practice-task">{{ exercise?.task || "当前资源暂未提供练习说明。" }}</p><textarea v-model="practiceSource" rows="10" class="practice-editor" spellcheck="false" placeholder="在这里提交你的实现…" /><div class="practice-actions"><button class="button button-primary" :disabled="busy || !practiceSource.trim()" @click="submitPractice"><Code2 :size="15" /> {{ busy ? "审核中…" : "提交实践审核" }}</button><span class="muted-text">服务端只做静态检查，不执行代码。</span></div><div v-if="practiceResult" class="practice-result" :class="{ 'is-success': practiceResult.accepted, 'is-error': !practiceResult.accepted }"><strong>{{ practiceResult.accepted ? "审核通过" : "需要修改" }}</strong><p>{{ practiceResult.feedback }}</p><ul v-if="practiceResult.issues?.length"><li v-for="issue in practiceResult.issues" :key="issue.code">{{ issue.message }}</li></ul></div></div>
    <form v-if="activeTab === 'assessment'" class="reader-quiz" @submit.prevent="submitQuiz"><fieldset v-for="(item, index) in quizItems" :key="item.question_id" :disabled="busy"><legend>第 {{ index + 1 }} 题</legend><p>{{ item.prompt }}</p><label v-for="(choice, choiceIndex) in item.choices" :key="choiceIndex" class="quiz-option"><input v-model="quizResponses[item.question_id]" type="radio" :name="item.question_id" :value="choiceIndex" /><span>{{ String.fromCharCode(65 + choiceIndex) }}</span>{{ choice }}</label></fieldset><button class="button button-primary" type="submit" :disabled="busy || !quizItems.length"><FileCheck2 :size="15" /> 提交小测</button><p v-if="quizResult" class="learning-notice">测评结果已写入学习路径。</p></form>

    <div class="reader-coach"><div class="reader-coach__title"><Sparkles :size="15" /><strong>当前节点 AI 学习顾问</strong></div><div class="coach-context"><span>{{ coachContext.concept }}</span><span>{{ coachContext.depth }}</span><span>掌握度 {{ coachContext.mastery }}</span><span>{{ coachContext.evidence }}</span></div><div v-if="coachBusy" class="coach-response">正在结合当前学习状态整理提示…</div><div v-else-if="coachAnswer" class="coach-response">{{ coachAnswer }}</div><div class="coach-input"><input v-model="coachQuestion" placeholder="围绕当前知识点提问" @keyup.enter="askCoach" /><button class="icon-button" title="发送问题" @click="askCoach"><Send :size="15" /></button></div></div>
    <p v-if="notice" class="learning-notice">{{ notice }}</p><p v-if="error" class="inline-error">{{ error }}</p>
  </section>
</template>

<style scoped>
.learning-resource-reader { display: grid; gap: 12px; margin-top: 16px; padding: 16px; background: #f8fbff; border: 1px solid #dbe7f6; border-radius: 12px; }
.reader-heading, .reader-action-row, .practice-selector, .practice-actions { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.reader-heading h4 { margin: 4px 0; font-size: 15px; }
.reader-heading p { margin: 0; font-size: 11px; }
.reader-tabs { display: flex; gap: 5px; border-bottom: 1px solid #dfe8f3; }
.reader-tabs button { padding: 7px 10px; color: var(--muted); background: transparent; border: 0; border-radius: 7px; font-size: 11px; font-weight: 800; }
.reader-tabs button.active { color: var(--blue); background: var(--blue-soft); }
.reader-content { min-height: 130px; color: #30445f; font-size: 12px; line-height: 1.8; }
.reader-content :deep(h2) { margin: 0 0 8px; color: var(--text); font-size: 18px; }
.reader-content :deep(h3) { margin: 12px 0 5px; color: var(--text); font-size: 13px; }
.reader-content :deep(pre) { overflow: auto; padding: 10px; color: #e7efff; background: #182b45; border-radius: 8px; }
.practice-panel, .reader-quiz, .reader-coach { display: grid; gap: 10px; padding-top: 10px; border-top: 1px solid #dfe8f3; }
.practice-selector { justify-content: flex-start; color: var(--muted); font-size: 11px; }
.practice-selector select { min-height: 32px; padding: 5px 8px; border: 1px solid var(--line); border-radius: 7px; }
.practice-task { margin: 0; padding: 9px 10px; color: #30445f; background: #fff; border-left: 3px solid var(--purple); border-radius: 7px; font-size: 11px; }
.practice-editor { width: 100%; padding: 10px; color: #e7efff; background: #182b45; border: 1px solid #284568; border-radius: 8px; resize: vertical; font-family: Consolas, monospace; font-size: 12px; line-height: 1.6; }
.practice-actions { justify-content: flex-start; }
.practice-result { padding: 10px; border-radius: 8px; font-size: 11px; }
.practice-result.is-success { color: var(--green); background: var(--green-soft); }
.practice-result.is-error { color: var(--red); background: #fff4f5; }
.practice-result p { margin: 4px 0; color: inherit; }
.practice-result ul { margin: 4px 0 0 16px; }
.reader-quiz fieldset { display: grid; gap: 6px; padding: 9px; border: 1px solid #dfe8f3; border-radius: 8px; }
.reader-quiz legend { color: var(--blue); font-size: 11px; font-weight: 800; }
.reader-quiz p { margin: 0; font-size: 11px; }
.reader-coach__title { display: flex; align-items: center; gap: 6px; color: var(--purple); font-size: 12px; }
@media (max-width: 680px) { .reader-heading, .reader-action-row, .practice-actions { align-items: flex-start; flex-direction: column; } }
</style>
