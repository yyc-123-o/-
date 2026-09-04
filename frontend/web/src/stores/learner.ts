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
      snapshot: normalizeSnapshot(parsed.snapshot),
      previousSnapshot: normalizeSnapshot(parsed.previousSnapshot),
      source: parsed.source ?? "empty",
      baselineProfileId: parsed.baselineProfileId ?? "",
      baselineLearnerId: parsed.baselineLearnerId ?? "",
      outcomeReport: parsed.outcomeReport ?? null,
    };
  } catch {
    return { profile: null, snapshot: null, previousSnapshot: null, source: "empty", baselineProfileId: "", baselineLearnerId: "", outcomeReport: null };
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function normalizeSnapshot(value: unknown): LearnerSnapshot | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const candidate = value as Record<string, unknown>;
  // Older builds persisted the complete adaptation response instead of its
  // snapshot. Unwrap it so the platform API receives the expected schema.
  const snapshot = candidate.snapshot && typeof candidate.snapshot === "object"
    ? candidate.snapshot
    : value;
  const normalized = snapshot as Partial<LearnerSnapshot>;
  return typeof normalized.schema_version === "string"
    && typeof normalized.profile_id === "string"
    && typeof normalized.learner_ref === "string"
    ? normalized as LearnerSnapshot
    : null;
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
      // Imported/demo profiles are local and are not registered in diagnosis.
      // Only refresh profiles created by the diagnosis service.
      if (source.value === "real" && profile.value?.learner_id) {
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

  function setDemoProfile(raw: unknown, nextSnapshot: LearnerSnapshot) {
    const data = asRecord(raw);
    const learnerId = String(data.learner_id || nextSnapshot.learner_ref || "demo-learner");
    const rawMastery = asRecord(data.knowledge_mastery);
    const rawPoints = asRecord(rawMastery.points);
    const pointEntries = Object.entries(rawPoints);
    const points = Object.fromEntries(pointEntries.map(([conceptId, value]) => {
      const item = asRecord(value);
      return [conceptId, {
        name: String(item.name || conceptId),
        domain: "导入画像",
        mastery: typeof item.mastery === "number" ? item.mastery : null,
        status: String(item.status || "unknown"),
        test_count: 0,
        confidence: asNumber(item.confidence, 0.4),
        evidence_level: "stable" as const,
      }];
    }));
    const scores = Object.values(points)
      .map((item) => item.mastery)
      .filter((value): value is number => typeof value === "number");
    const scope = asRecord(data.learning_scope);
    const preferences = asRecord(data.learning_preferences);
    const pace = asRecord(preferences.pace);
    const profile: DiagnosisProfile = {
      profile_id: String(data.profile_id || learnerId),
      profile_version: String(data.profile_version || "2.1"),
      learner_id: learnerId,
      learner: {
        name: String(asRecord(data.learner).name || `导入画像 · ${learnerId}`),
        education: asRecord(asRecord(data.learner).education),
        self_assessment: {
          learning_goal: String(scope.chapter_id || "按导入画像生成个性化学习路径"),
          weekly_hours: asNumber(pace.weekly_hours, 5),
        },
      },
      knowledge_mastery: {
        global_theta: asNumber(rawMastery.global_theta),
        overall_accuracy: asNumber(rawMastery.overall_accuracy),
        overall_mastery: scores.length ? scores.reduce((sum, value) => sum + value, 0) / scores.length : null,
        overall_confidence: scores.length ? 0.8 : 0,
        tested_kps: scores.length,
        total_kps: pointEntries.length,
        coverage_ratio: pointEntries.length ? scores.length / pointEntries.length : 0,
        points,
      },
      ability_level: {
        overall: String(asRecord(data.ability_level).overall || "beginner"),
        global_theta: asNumber(asRecord(data.ability_level).global_theta),
        sub_dimensions: {},
      },
      learning_scope: {
        chapter_id: String(scope.chapter_id || "ch03_cnn"),
        chapter_name: String(scope.chapter_name || "卷积神经网络（CNN）"),
        primary_kp_id: String(scope.primary_kp_id || "kp_012"),
        primary_kp_name: String(
          scope.primary_kp_name
          || asRecord(rawPoints[String(scope.primary_kp_id || "kp_012")]).name
          || "",
        ),
        target_depth: String(scope.target_depth || "入门"),
      },
    };
    setProfile(profile, "demo");
    setSnapshot(nextSnapshot);
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
    learnerName, mastery, weakPoints, loadLearners, selectLearner, adaptProfile, setProfile, setDemoProfile, setSnapshot,
    saveBaseline, verifyOutcome,
  };
});
