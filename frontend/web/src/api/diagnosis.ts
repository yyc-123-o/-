import { api, withRetry } from "./client";
import type { AdaptiveSession, BasicForm, DomainAssessment } from "@/types/diagnosis";
import type { DiagnosisProfile, LearnerSummary } from "@/types/learner";

export const diagnosisApi = {
  learners: () => withRetry(() => api.get<{ learners: LearnerSummary[] }>("/diagnosis/api/learners").then((r) => r.data)),
  profile: (learnerId: string) =>
    withRetry(() => api.get<DiagnosisProfile>(`/diagnosis/api/learner/${encodeURIComponent(learnerId)}/profile`).then((r) => r.data)),
  upload: (form: BasicForm, domains: DomainAssessment[], projects: unknown[] = []) =>
    api.post<{ learner_id: string }>("/diagnosis/api/learner/upload", {
      name: form.name,
      education: { ...form.education },
      self_assessment: {
        learning_goal: form.learning_goal,
        weekly_hours: form.weekly_hours,
        domain_assessments: domains,
        projects,
      },
      test_records: [],
      interaction_records: [],
    }).then((r) => r.data),
  diagnose: (learnerId: string, chapterId = "ch03_cnn") =>
    api.post<DiagnosisProfile>(`/diagnosis/api/learner/${encodeURIComponent(learnerId)}/diagnose`, null, {
      params: { chapter_id: chapterId },
    }).then((r) => r.data),
  startAdaptive: (learnerId: string) =>
    api.post<AdaptiveSession>(`/diagnosis/api/adaptive-test/start/${encodeURIComponent(learnerId)}`).then((r) => r.data),
  answerAdaptive: (payload: Record<string, unknown>) =>
    api.post<AdaptiveSession>("/diagnosis/api/adaptive-test/answer", payload).then((r) => r.data),
  session: (sessionId: string) =>
    api.get<AdaptiveSession>(`/diagnosis/api/adaptive-test/session/${encodeURIComponent(sessionId)}`).then((r) => r.data),
  applyAdaptive: (learnerId: string, sessionId: string) =>
    api.post(`/diagnosis/api/adaptive-test/apply/${encodeURIComponent(learnerId)}`, null, { params: { session_id: sessionId } }).then((r) => r.data),
  resetDemo: () => api.post("/diagnosis/api/demo/generate").then((r) => r.data),
};
