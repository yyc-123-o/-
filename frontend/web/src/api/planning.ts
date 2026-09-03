import { api, RESOURCE_GENERATION_TIMEOUT_MS } from "./client";
import type { LearnerSnapshot } from "@/types/learner";
import type { PlatformRun } from "@/types/planning";

export const planningApi = {
  run: (profile: LearnerSnapshot, options: Record<string, unknown> = {}) =>
    api.post<PlatformRun>("/api/v1/runs", {
      profile,
      idempotency_key: `web-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      execution_mode: options.execution_mode || "candidate_preview",
      assessment_model: options.assessment_model || "bkt",
      top_k: options.top_k || 5,
      target_concept_id: options.target_concept_id || null,
      start_concept_id: options.start_concept_id || null,
    }, { timeout: RESOURCE_GENERATION_TIMEOUT_MS }).then((r) => r.data),
  startNode: (runId: string, conceptId: string, pathMode: "personalized" | "full" = "personalized") =>
    api.post<PlatformRun>(`/api/v1/runs/${encodeURIComponent(runId)}/start-node`, { concept_id: conceptId, path_mode: pathMode }, { timeout: RESOURCE_GENERATION_TIMEOUT_MS }).then((r) => r.data),
  completeNode: (runId: string, conceptId: string) =>
    api.post<PlatformRun>(`/api/v1/runs/${encodeURIComponent(runId)}/complete-node`, { concept_id: conceptId }, { timeout: RESOURCE_GENERATION_TIMEOUT_MS }).then((r) => r.data),
  runById: (runId: string) => api.get<PlatformRun>(`/api/v1/runs/${encodeURIComponent(runId)}`).then((r) => r.data),
};
