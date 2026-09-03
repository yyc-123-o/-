import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { AxiosError } from "axios";
import { planningApi } from "@/api/planning";
import type { PlatformRun, PathNode } from "@/types/planning";
import { useLearnerStore } from "./learner";

export const useLearningPathStore = defineStore("learningPath", () => {
  const run = ref<PlatformRun | null>(null);
  const loading = ref(false);
  const error = ref("");
  const learner = useLearnerStore();
  const progressChannel = typeof BroadcastChannel !== "undefined"
    ? new BroadcastChannel("learning-progress-events")
    : null;

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

  async function completeLearningContent(conceptId = currentNode.value?.concept_id || "") {
    if (!run.value?.run_id || !conceptId) throw new Error("当前资源尚未关联知识点");
    const updated = await planningApi.recordLectureProgress(run.value.run_id, conceptId, 1);
    setRun(updated);
    progressChannel?.postMessage({
      type: "learning-progress-updated",
      runId: updated.run_id,
      courseId: updated.planning?.current_node?.chapter_id,
      knowledgeNodeId: conceptId,
      learningProgress: updated.learning_progress,
      occurredAt: new Date().toISOString(),
    });
    return updated;
  }

  function friendlyError(reason: unknown, fallback = "操作失败") {
    if (reason instanceof AxiosError) {
      const detail = reason.response?.data?.detail;
      const code = typeof detail?.code === "string" ? detail.code : "";
      const message = typeof detail?.message === "string" ? detail.message : "";
      if (reason.response?.status === 409) {
        if (code === "invalid_lecture_progress") {
          return "当前学习资源状态已变化，请返回学习路径确认下一步后再继续。";
        }
        if (code === "invalid_learning_transition") {
          return "当前知识点还未满足完成条件，请先完成学习内容、练习和测评。";
        }
        return message || "当前学习状态已更新，请稍后重试。";
      }
      if (reason.response?.status && reason.response.status >= 500) {
        return "暂时无法连接平台服务，当前数据将在连接恢复后自动加载。";
      }
      return message || fallback;
    }
    return reason instanceof Error ? reason.message : fallback;
  }

  function setRun(next: PlatformRun) {
    run.value = next;
    if (next.profile) learner.setSnapshot(next.profile);
  }

  progressChannel?.addEventListener("message", (event) => {
    const data = event.data as { type?: string; runId?: string } | null;
    if (data?.type === "learning-progress-updated" && data.runId && data.runId === run.value?.run_id) {
      void planningApi.runById(data.runId).then(setRun).catch(() => undefined);
    }
  });

  return { run, loading, error, nodes, currentNode, generate, startNode, completeNode, completeLearningContent, friendlyError, setRun };
});
