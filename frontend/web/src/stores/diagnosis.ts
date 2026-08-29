import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { diagnosisApi } from "@/api/diagnosis";
import type { BasicForm, DomainAssessment, AdaptiveSession } from "@/types/diagnosis";
import type { DiagnosisProfile } from "@/types/learner";
import { useLearnerStore } from "./learner";

const FORM_KEY = "zhijing.diagnosis.form.v1";
const defaultForm: BasicForm = {
  name: "",
  education: { level: "本科", major: "", institution: "", gpa: null },
  learning_goal: "掌握 AI 与机器学习核心课程",
  weekly_hours: 6,
};

function loadForm(): BasicForm {
  try {
    return { ...defaultForm, ...JSON.parse(localStorage.getItem(FORM_KEY) || "") };
  } catch {
    return { ...defaultForm, education: { ...defaultForm.education } };
  }
}

export const useDiagnosisStore = defineStore("diagnosis", () => {
  const form = ref<BasicForm>(loadForm());
  const domains = ref<DomainAssessment[]>([]);
  const learnersLoading = ref(false);
  const submitting = ref(false);
  const error = ref("");
  const status = ref("准备开始");
  const session = ref<AdaptiveSession | null>(null);
  const adaptiveAnswers = ref<Array<{ question: string; correct: boolean; concept: string }>>([]);
  const activeStage = ref(1);
  const learner = useLearnerStore();

  const completedStages = computed(() => {
    const result = [];
    if (form.value.name && form.value.education.major) result.push(1);
    if (session.value?.finished) result.push(2);
    if (learner.profile) result.push(3);
    return result;
  });

  function saveForm() {
    localStorage.setItem(FORM_KEY, JSON.stringify(form.value));
    status.value = "草稿已保存";
  }

  async function loadLearners() {
    learnersLoading.value = true;
    try {
      await learner.loadLearners();
    } finally {
      learnersLoading.value = false;
    }
  }

  async function submitBasic() {
    submitting.value = true;
    error.value = "";
    try {
      const result = await diagnosisApi.upload(form.value, domains.value);
      await learner.loadLearners();
      await learner.selectLearner(result.learner_id);
      activeStage.value = 2;
      status.value = "基础信息已保存";
      saveForm();
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : "保存基础信息失败";
      throw reason;
    } finally {
      submitting.value = false;
    }
  }

  async function runDiagnosis() {
    if (!learner.selectedLearnerId) throw new Error("请先选择学习者");
    submitting.value = true;
    error.value = "";
    try {
      const profile = await diagnosisApi.diagnose(learner.selectedLearnerId);
      learner.setProfile(profile, "real");
      activeStage.value = 3;
      status.value = "学习画像已生成";
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : "诊断失败";
      throw reason;
    } finally {
      submitting.value = false;
    }
  }

  async function startAdaptive() {
    if (!learner.selectedLearnerId) throw new Error("请先选择学习者");
    session.value = await diagnosisApi.startAdaptive(learner.selectedLearnerId);
    activeStage.value = 2;
    status.value = "自适应测试进行中";
  }

  async function answer(questionId: string, selectedAnswer: number) {
    if (!session.value?.session_id) return;
    const answeredName = session.value.next_question?.knowledge_point_name || session.value.next_question?.question_text || "自适应题目";
    // 后端硬编码判分：必须提交 selected_answer（选项下标），禁止提交 is_correct
    session.value = await diagnosisApi.answerAdaptive({
      session_id: session.value.session_id,
      question_id: questionId,
      selected_answer: selectedAnswer,
      time_spent: 30,
    });
    if (typeof session.value.last_correct === "boolean") {
      adaptiveAnswers.value.push({
        question: answeredName,
        correct: session.value.last_correct,
        concept: answeredName,
      });
    }
    if (session.value.finished) status.value = "测试完成，可以生成画像";
  }

  async function finishAdaptive() {
    if (!session.value?.session_id || !learner.selectedLearnerId) throw new Error("没有可提交的测试会话");
    await diagnosisApi.applyAdaptive(learner.selectedLearnerId, session.value.session_id);
    await runDiagnosis();
    status.value = "测试结果已更新到学习画像";
  }

  return {
    form, domains, learnersLoading, submitting, error, status, session, adaptiveAnswers, activeStage,
    completedStages, saveForm, loadLearners, submitBasic, runDiagnosis, startAdaptive, answer, finishAdaptive,
  };
});
