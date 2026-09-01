import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { planningApi } from "@/api/planning";
import type { PlatformRun, PathNode } from "@/types/planning";
import { useLearnerStore } from "./learner";

export const useLearningPathStore = defineStore("learningPath", () => {
  const RUN_KEY = "zhijing.learning-path.run.v1";
  let savedRun: PlatformRun | null = null;
  try { savedRun = JSON.parse(localStorage.getItem(RUN_KEY) || "null") as PlatformRun | null; } catch { savedRun = null; }
  const run = ref<PlatformRun | null>(savedRun);
  const loading = ref(false);
  const error = ref("");
  const learner = useLearnerStore();

  const nodes = computed<PathNode[]>(() => run.value?.planning?.path?.nodes || []);
  const currentNode = computed(() => run.value?.planning?.current_node || nodes.value.find((node) => node.status === "available"));
  function persistRun() { localStorage.setItem(RUN_KEY, JSON.stringify(run.value)); }

  async function generate() {
    loading.value = true;
    error.value = "";
    try {
      const snapshot = learner.snapshot || await learner.adaptProfile();
      if (!snapshot) throw new Error("请先完成学习画像");
      run.value = await planningApi.run(snapshot);
      persistRun();
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : "学习路径生成失败";
    } finally {
      loading.value = false;
    }
  }

  async function startNode(conceptId: string) {
    if (!run.value?.run_id) return;
    run.value = await planningApi.startNode(run.value.run_id, conceptId);
    persistRun();
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

  return { run, loading, error, nodes, currentNode, generate, startNode, completeNode, setRun };
});
