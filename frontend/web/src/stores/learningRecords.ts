import { computed, ref } from "vue";
import { defineStore } from "pinia";

export type LearningRecordType =
  | "resource_started"
  | "resource_completed"
  | "knowledge_completed"
  | "assessment_completed"
  | "mastery_updated"
  | "path_replanned"
  | "node_unlocked"
  | "review_completed";

export interface LearningRecord {
  id: string;
  learnerId: string;
  courseId: string;
  courseTitle: string;
  knowledgeNodeId: string | null;
  knowledgeNodeTitle: string | null;
  resourceId: string | null;
  resourceTitle: string | null;
  assessmentId: string | null;
  attemptId: string | null;
  type: LearningRecordType;
  title: string;
  description: string | null;
  durationSeconds: number | null;
  completionRate: number | null;
  previousMastery: number | null;
  currentMastery: number | null;
  assessmentScore: number | null;
  assessmentAccuracy: number | null;
  previousRecommendedNodeId: string | null;
  currentRecommendedNodeId: string | null;
  unlockedNodeIds: string[];
  occurredAt: string;
  createdAt: string;
  source: "platform-run" | "learner-profile" | "local-event";
  metadata?: Record<string, unknown>;
}

const KEY = "zhijing.learning.records.v1";

function readRecords() {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) || "[]") as LearningRecord[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function persist(records: LearningRecord[]) {
  localStorage.setItem(KEY, JSON.stringify(records.slice(0, 500)));
}

export const useLearningRecordsStore = defineStore("learningRecords", () => {
  const localRecords = ref<LearningRecord[]>(readRecords());

  const records = computed(() =>
    localRecords.value
      .slice()
      .sort((a, b) => new Date(b.occurredAt).getTime() - new Date(a.occurredAt).getTime()),
  );

  function upsert(record: LearningRecord) {
    const next = localRecords.value.filter((item) => item.id !== record.id);
    next.unshift(record);
    localRecords.value = next.sort((a, b) => new Date(b.occurredAt).getTime() - new Date(a.occurredAt).getTime());
    persist(localRecords.value);
  }

  function remove(id: string) {
    localRecords.value = localRecords.value.filter((item) => item.id !== id);
    persist(localRecords.value);
  }

  function clear() {
    localRecords.value = [];
    persist(localRecords.value);
  }

  return { localRecords, records, upsert, remove, clear };
});
