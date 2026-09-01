import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { planningApi } from "@/api/planning";
import type { PlatformRun, PathNode } from "@/types/planning";
import { useLearnerStore } from "./learner";

export const useLearningPathStore = defineStore("learningPath", () => {
  const run = ref<PlatformRun | null>(null);
  const loading = ref(false);
  const error = ref("");
  const learner = useLearnerStore();

  const nodes = computed<PathNode[]>(() => run.value?.planning?.path?.nodes || []);
  const currentNode = computed(() => run.value?.planning?.current_node || nodes.value.find((node) => node.status === "available"));

  async function generate() {
    loading.value = true;
    error.value = "";
    try {
      const snapshot = learner.snapshot || await learner.adaptProfile();
      if (!snapshot) throw new Error("请先完成学习画像");
      run.value = await planningApi.run(snapshot);
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : "学习路径生成失败";
    } finally {
      loading.value = false;
    }
  }

  async function startNode(conceptId: string) {
    if (!run.value?.run_id) return;
    run.value = await planningApi.startNode(run.value.run_id, conceptId);
  }

  async function completeNode() {
    if (!run.value?.run_id || !currentNode.value) return;
    run.value = await planningApi.completeNode(run.value.run_id, currentNode.value.concept_id);
  }

  function setRun(next: PlatformRun) {
    run.value = next;
    if (next.profile) learner.setSnapshot(next.profile);
  }

  return { run, loading, error, nodes, currentNode, generate, startNode, completeNode, setRun };
});
