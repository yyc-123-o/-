import { api, RESOURCE_GENERATION_TIMEOUT_MS } from "./client";
import type { DiagnosisProfile, LearnerSnapshot } from "@/types/learner";

export const profileApi = {
  adapt: (profile: DiagnosisProfile) =>
    api.post<{ snapshot: LearnerSnapshot }>("/api/v1/profiles/adapt", profile, {
      timeout: RESOURCE_GENERATION_TIMEOUT_MS,
    }).then((r) => r.data),
  evaluation: (profileId: string) =>
    api.get(`/api/v1/profiles/${encodeURIComponent(profileId)}/knowledge-tracing/evaluation`).then((r) => r.data),
};
