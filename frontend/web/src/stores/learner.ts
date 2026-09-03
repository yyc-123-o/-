import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { profileApi } from "@/api/profile";
import type { DiagnosisProfile, LearnerSnapshot, LearnerSummary, LearningOutcomeReport } from "@/types/learner";

const KEY = "zhijing.learner.state.v1";

interface LearnerPersistedState {
  profile: DiagnosisProfile | null;
  snapshot: LearnerSnapshot | null;
  previousSnapshot: LearnerSnapshot | null;
  source: "real" | "demo" | "empty";
  baselineProfileId: string;
  baselineLearnerId: string;
  outcomeReport: LearningOutcomeReport | null;
}

function readState(): LearnerPersistedState {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) || "") as Partial<LearnerPersistedState>;
    return {
      // A previous frontend version may have persisted a partial profile.
      // Do not treat it as a current learner until its identity is complete.
      profile: parsed.profile?.learner ? parsed.profile : null,
      snapshot: parsed.snapshot ?? null,
      previousSnapshot: parsed.previousSnapshot ?? null,
      source: parsed.source ?? "empty",
      baselineProfileId: parsed.baselineProfileId ?? "",
      baselineLearnerId: parsed.baselineLearnerId ?? "",
      outcomeReport: parsed.outcomeReport ?? null,
    };
  } catch {
    return { profile: null, snapshot: null, previousSnapshot: null, source: "empty", baselineProfileId: "", baselineLearnerId: "", outcomeReport: null };
  }
}

export const useLearnerStore = defineStore("learner", () => {
  const saved = readState();
  const learners = ref<LearnerSummary[]>([]);
  const profile = ref<DiagnosisProfile | null>(saved.profile);
  const snapshot = ref<LearnerSnapshot | null>(saved.snapshot);
  const previousSnapshot = ref<LearnerSnapshot | null>(saved.previousSnapshot);
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
      previousSnapshot: previousSnapshot.value,
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
      // Persisted profiles may use an older diagnostic schema. Refresh the
      // selected learner on app start so legacy local storage cannot keep
      // presenting obsolete, hard-coded-looking results.
      if (profile.value?.learner_id) {
        try {
          profile.value = await diagnosisApi.profile(profile.value.learner_id);
          selectedLearnerId.value = profile.value.learner_id;
          source.value = "real";
          persist();
        } catch {
          // The backend was restarted or the learner was deleted. Do not keep
          // rendering its stale local result as though it were current data.
          profile.value = null;
          snapshot.value = null;
          previousSnapshot.value = null;
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
      previousSnapshot.value = null;
      // 切换学习者时，基线与成果报告属于上一个学习者，一并重置
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
    setSnapshot(data.snapshot);
    return data.snapshot;
  }

  function setProfile(next: DiagnosisProfile, nextSource: "real" | "demo" = "real") {
    profile.value = next;
    selectedLearnerId.value = next.learner_id;
    source.value = nextSource;
    persist();
  }

  function setSnapshot(next: LearnerSnapshot) {
    const currentMastery = snapshot.value?.knowledge_mastery || [];
    const nextMastery = next.knowledge_mastery || [];
    if (
      snapshot.value
      && snapshot.value.profile_id === next.profile_id
      && JSON.stringify(currentMastery) !== JSON.stringify(nextMastery)
    ) {
      previousSnapshot.value = snapshot.value;
    }
    snapshot.value = next;
    persist();
  }

  // ===== 学习成果检验（第二流程）=====
  // 保存当前画像为基线，之后继续学习/测评，再复诊对比生成检验报告
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
      // 复诊会用最新答题记录重建画像，直接把返回的新画像写入看板
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
    learners, profile, snapshot, previousSnapshot, source, selectedLearnerId, loading, error,
    baselineProfileId, outcomeReport,
    learnerName, mastery, weakPoints, loadLearners, selectLearner, adaptProfile, setProfile, setSnapshot,
    saveBaseline, verifyOutcome,
  };
});
