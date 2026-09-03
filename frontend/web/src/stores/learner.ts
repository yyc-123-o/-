import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { profileApi } from "@/api/profile";
import type {
  DiagnosisProfile,
  LearnerSnapshot,
  LearnerSummary,
  LearningOutcomeReport,
} from "@/types/learner";

const KEY = "zhijing.learner.state.v1";

interface LearnerPersistedState {
  profile: DiagnosisProfile | null;
  snapshot: LearnerSnapshot | null;
  source: "real" | "demo" | "empty";
  baselineProfileId: string;
  baselineLearnerId: string;
  outcomeReport: LearningOutcomeReport | null;
}

function readState(): LearnerPersistedState {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) || "") as Partial<LearnerPersistedState>;
    return {
      profile: parsed.profile?.learner ? parsed.profile : null,
      snapshot: parsed.snapshot ?? null,
      source: parsed.source ?? "empty",
      baselineProfileId: parsed.baselineProfileId ?? "",
      baselineLearnerId: parsed.baselineLearnerId ?? "",
      outcomeReport: parsed.outcomeReport ?? null,
    };
  } catch {
    return {
      profile: null,
      snapshot: null,
      source: "empty",
      baselineProfileId: "",
      baselineLearnerId: "",
      outcomeReport: null,
    };
  }
}

export const useLearnerStore = defineStore("learner", () => {
  const saved = readState();
  const learners = ref<LearnerSummary[]>([]);
  const profile = ref<DiagnosisProfile | null>(saved.profile);
  const snapshot = ref<LearnerSnapshot | null>(saved.snapshot);
  const source = ref<"real" | "demo" | "empty">(saved.source || "empty");
  const baselineProfileId = ref(saved.baselineProfileId);
  const baselineLearnerId = ref(saved.baselineLearnerId);
  const outcomeReport = ref<LearningOutcomeReport | null>(saved.outcomeReport);
  const selectedLearnerId = ref(profile.value?.learner_id || "");
  const loading = ref(false);
  const error = ref("");

  const learnerName = computed(() => profile.value?.learner?.name || "学习者");
  const mastery = computed(() => {
    const value = profile.value?.knowledge_mastery?.overall_mastery;
    return typeof value === "number" ? value : 0;
  });
  const weakPoints = computed(() =>
    Object.values(profile.value?.knowledge_mastery?.points || {}).filter(
      (point) => typeof point.mastery === "number" && point.mastery < 0.6,
    ),
  );

  function persist() {
    localStorage.setItem(KEY, JSON.stringify({
      profile: profile.value,
      snapshot: snapshot.value,
      source: source.value,
      baselineProfileId: baselineProfileId.value,
      baselineLearnerId: baselineLearnerId.value,
      outcomeReport: outcomeReport.value,
    }));
  }

  async function loadLearners() {
    const { diagnosisApi } = await import("@/api/diagnosis");
    loading.value = true;
    error.value = "";
    try {
      learners.value = (await diagnosisApi.learners()).learners;
      if (profile.value?.learner_id) {
        try {
          profile.value = await diagnosisApi.profile(profile.value.learner_id);
          selectedLearnerId.value = profile.value.learner_id;
          source.value = "real";
          persist();
        } catch {
          profile.value = null;
          snapshot.value = null;
          source.value = "empty";
          selectedLearnerId.value = "";
          persist();
        }
      }
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : "学习者列表加载失败";
    } finally {
      loading.value = false;
    }
  }

  async function selectLearner(id: string) {
    if (!id) return;
    loading.value = true;
    error.value = "";
    try {
      const { diagnosisApi } = await import("@/api/diagnosis");
      profile.value = await diagnosisApi.profile(id);
      selectedLearnerId.value = id;
      source.value = "real";
      snapshot.value = null;
      if (profile.value.learner_id !== outcomeReport.value?.learner_id) outcomeReport.value = null;
      if (profile.value.learner_id !== baselineLearnerId.value) baselineProfileId.value = "";
      persist();
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : "画像加载失败";
    } finally {
      loading.value = false;
    }
  }

  async function adaptProfile() {
    if (!profile.value) return null;
    const data = await profileApi.adapt(profile.value);
    snapshot.value = data.snapshot;
    persist();
    return data.snapshot;
  }

  function setProfile(next: DiagnosisProfile, nextSource: "real" | "demo" = "real") {
    profile.value = next;
    selectedLearnerId.value = next.learner_id;
    source.value = nextSource;
    persist();
  }

  function setSnapshot(next: LearnerSnapshot) {
    snapshot.value = next;
    persist();
  }

  // 保存基线，继续学习后再复诊并生成成果对比报告。
  async function saveBaseline() {
    if (!profile.value) return null;
    const { diagnosisApi } = await import("@/api/diagnosis");
    loading.value = true;
    error.value = "";
    try {
      const data = await diagnosisApi.saveBaseline(profile.value.learner_id);
      baselineProfileId.value = data.profile_id;
      baselineLearnerId.value = profile.value.learner_id;
      persist();
      return data;
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : "基线画像保存失败";
      return null;
    } finally {
      loading.value = false;
    }
  }

  async function verifyOutcome() {
    if (!profile.value) return null;
    const { diagnosisApi } = await import("@/api/diagnosis");
    loading.value = true;
    error.value = "";
    try {
      const learnerId = profile.value.learner_id;
      profile.value = await diagnosisApi.reDiagnose(learnerId);
      selectedLearnerId.value = learnerId;
      source.value = "real";
      const report = await diagnosisApi.verifyOutcome(learnerId);
      outcomeReport.value = report;
      baselineProfileId.value = report.baseline_profile_id || baselineProfileId.value;
      baselineLearnerId.value = learnerId;
      persist();
      return report;
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : "学习成果检验失败";
      return null;
    } finally {
      loading.value = false;
    }
  }

  return {
    learners,
    profile,
    snapshot,
    source,
    selectedLearnerId,
    loading,
    error,
    baselineProfileId,
    outcomeReport,
    learnerName,
    mastery,
    weakPoints,
    loadLearners,
    selectLearner,
    adaptProfile,
    setProfile,
    setSnapshot,
    saveBaseline,
    verifyOutcome,
  };
});
