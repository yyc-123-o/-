import { computed, ref, watch } from "vue";
import { defineStore } from "pinia";
import { planningApi } from "@/api/planning";
import type { PlatformRun, PathNode, PathRecommendation } from "@/types/planning";
import { useLearnerStore } from "./learner";

export const useLearningPathStore = defineStore("learningPath", () => {
  const RUN_KEY = "zhijing.learning-path.run.v2";
  const loading = ref(false);
  const error = ref("");
  const pathMode = ref<"personalized" | "full">("personalized");
  const learner = useLearnerStore();

  function profileKey(): string {
    return learner.snapshot?.profile_id || learner.profile?.learner_id || "";
  }

  function storageKey(profileId = profileKey()): string {
    return profileId ? `${RUN_KEY}.${profileId}` : RUN_KEY;
  }

  function currentProfileGeneratedAt(): string {
    return learner.snapshot?.generated_at || learner.profile?.generated_at || "";
  }

  function loadSavedRun(profileId = profileKey()): PlatformRun | null {
    if (!profileId) return null;
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey(profileId)) || "null") as PlatformRun | null;
      if (!saved || saved.profile_id !== profileId) return null;
      // A run is tied to the exact profile snapshot used to create it. Older
      // cached paths must not survive a refreshed diagnosis for the same user.
      const currentGeneratedAt = currentProfileGeneratedAt();
      const savedGeneratedAt = saved.profile?.generated_at || "";
      if (currentGeneratedAt && (!savedGeneratedAt || currentGeneratedAt > savedGeneratedAt)) {
        return null;
      }
      return saved;
    } catch {
      return null;
    }
  }

  const run = ref<PlatformRun | null>(loadSavedRun());

  const personalizedNodes = computed<PathNode[]>(() =>
    (run.value?.planning?.path?.nodes || []).filter((node) => node.status !== "skipped"),
  );
  const fullNodes = computed<PathNode[]>(() =>
    (run.value?.planning?.full_path?.nodes || run.value?.planning?.path?.nodes || []).map((node) => ({
      ...node,
      personalized_skipped: run.value?.planning?.path?.nodes?.some(
        (personalizedNode) => personalizedNode.concept_id === node.concept_id
          && personalizedNode.status === "skipped",
      ) || false,
    })),
  );
  const nodes = computed<PathNode[]>(() =>
    pathMode.value === "full" ? fullNodes.value : personalizedNodes.value,
  );
  const recommendations = computed<PathRecommendation[]>(() => run.value?.planning?.path?.recommendations || []);
  const currentNode = computed(() => run.value?.planning?.current_node || nodes.value.find((node) => node.status === "available"));
  function persistRun() {
    if (run.value?.profile_id) localStorage.setItem(storageKey(run.value.profile_id), JSON.stringify(run.value));
  }

  async function generate() {
    // Importing a profile updates the store before the route mounts. The
    // watcher below and LearningPathView's onMounted hook can otherwise start
    // two identical, LLM-backed resource requests for the same snapshot.
    if (loading.value) return;
    loading.value = true;
    error.value = "";
    try {
      // Always refresh from the current diagnosis profile before planning;
      // persisted snapshots may belong to an older adapter schema.
      let snapshot = learner.snapshot;
      if (learner.profile) {
        try {
          snapshot = await learner.adaptProfile();
        } catch {
          // Keep a previously normalized snapshot usable when a legacy profile
          // cannot be adapted again (for example after a backend restart).
        }
      }
      if (!snapshot) throw new Error("请先完成学习画像");
      // The adapter owns legacy KP -> canonical concept mapping. The returned
      // snapshot is already normalized, so let the planner derive a safe queue
      // instead of sending the legacy `kp_*` identifier to the API.
      run.value = await planningApi.run(snapshot);
      pathMode.value = "personalized";
      persistRun();
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : "学习路径生成失败";
    } finally {
      loading.value = false;
    }
  }

  function setPathMode(mode: "personalized" | "full") {
    pathMode.value = mode;
  }

  async function startNode(conceptId: string, mode: "personalized" | "full" = pathMode.value) {
    if (!run.value?.run_id) return;
    loading.value = true;
    error.value = "";
    try {
      run.value = await planningApi.startNode(run.value.run_id, conceptId, mode);
      pathMode.value = mode;
      persistRun();
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : "知识点启动失败";
    } finally {
      loading.value = false;
    }
  }

  async function completeNode() {
    if (!run.value?.run_id || !currentNode.value) return;
    run.value = await planningApi.completeNode(run.value.run_id, currentNode.value.concept_id);
    persistRun();
  }

  function setRun(next: PlatformRun) {
    run.value = next;
    persistRun();
    if (next.profile) learner.setSnapshot(next.profile);
  }

  watch(
    () => [
      learner.snapshot?.profile_id || learner.profile?.learner_id || "",
      learner.snapshot?.generated_at || learner.profile?.generated_at || "",
    ],
    ([profileId, generatedAt], [previousProfileId, previousGeneratedAt]) => {
      if (!profileId || (profileId === previousProfileId && generatedAt === previousGeneratedAt)) return;
      run.value = loadSavedRun(profileId);
      error.value = "";
      if (!run.value && (learner.snapshot || learner.profile)) void generate();
    },
  );

  return {
    run, loading, error, pathMode, personalizedNodes, fullNodes, nodes, recommendations, currentNode,
    generate, setPathMode, startNode, completeNode, setRun,
  };
});
