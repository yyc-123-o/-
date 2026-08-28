import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { profileApi } from "@/api/profile";
import type { DiagnosisProfile, LearnerSnapshot, LearnerSummary } from "@/types/learner";

const KEY = "zhijing.learner.state.v1";

function readState(): { profile: DiagnosisProfile | null; snapshot: LearnerSnapshot | null; source: "real" | "demo" | "empty" } {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "") as ReturnType<typeof readState>;
  } catch {
    return { profile: null, snapshot: null, source: "empty" };
  }
}

export const useLearnerStore = defineStore("learner", () => {
  const saved = readState();
  const learners = ref<LearnerSummary[]>([]);
  const profile = ref<DiagnosisProfile | null>(saved.profile);
  const snapshot = ref<LearnerSnapshot | null>(saved.snapshot);
  const source = ref<"real" | "demo" | "empty">(saved.source || "empty");
  const selectedLearnerId = ref(profile.value?.learner_id || "");
  const loading = ref(false);
  const error = ref("");

  const learnerName = computed(() => profile.value?.learner.name || "学习者");
  const mastery = computed(() => {
    const points = profile.value?.knowledge_mastery?.points || {};
    const values = Object.values(points).map((point) => point.mastery).filter((value) => typeof value === "number");
    return values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;
  });
  const weakPoints = computed(() =>
    Object.values(profile.value?.knowledge_mastery?.points || {}).filter((point) => point.mastery < 0.6),
  );

  function persist() {
    localStorage.setItem(KEY, JSON.stringify({
      profile: profile.value,
      snapshot: snapshot.value,
      source: source.value,
    }));
  }

  async function loadLearners() {
    const { diagnosisApi } = await import("@/api/diagnosis");
    loading.value = true;
    error.value = "";
    try {
      learners.value = (await diagnosisApi.learners()).learners;
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

  return {
    learners, profile, snapshot, source, selectedLearnerId, loading, error,
    learnerName, mastery, weakPoints, loadLearners, selectLearner, adaptProfile, setProfile, setSnapshot,
  };
});
